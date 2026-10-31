import uuid
from typing import Any, Dict, List, Optional, TypedDict
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.tools.onboard import OnboardTools
from app.adapters.speech import MockSpeechAdapter


class OnboardAgentState(TypedDict):
    merchant_id: str
    query_text: str
    execution_id: str
    actor_id: str
    checklist: Optional[Dict[str, Any]]
    missing_documents: List[str]
    blurry_documents: List[str]
    current_step: str
    action_taken: str
    agent_reply: str
    chip_status: str  # verified | executed | pending | awaiting_approval | needs_human
    missing_item_card: Optional[Dict[str, Any]]
    is_security_violation: bool
    verification_result: Optional[Dict[str, Any]]


class OnboardAgent:
    """
    Onboard Specialist Agent (KYC Closer).
    Helps merchants complete onboarding by chasing exact missing items with specific reasons,
    treating OCR outputs as untrusted candidate data, and gating activation behind simulated
    authorized verification.
    """

    def __init__(self, db: Session):
        self.db = db
        self.tools = OnboardTools(db=db)
        self.speech_adapter = MockSpeechAdapter()
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(OnboardAgentState)

        builder.add_node("inspect_checklist", self._node_inspect_checklist)
        builder.add_node("chase_specific_missing_item", self._node_chase_specific_missing_item)
        builder.add_node("submit_verification", self._node_submit_verification)

        builder.set_entry_point("inspect_checklist")

        def route_next(state: OnboardAgentState):
            if state.get("is_security_violation"):
                return END
            if state.get("action_taken") == "ALREADY_VERIFIED":
                return END
            if state.get("action_taken") == "READY_FOR_VERIFICATION":
                return "submit_verification"
            return "chase_specific_missing_item"

        builder.add_conditional_edges(
            "inspect_checklist",
            route_next,
            {
                "chase_specific_missing_item": "chase_specific_missing_item",
                "submit_verification": "submit_verification",
                END: END,
            },
        )

        builder.add_edge("chase_specific_missing_item", END)
        builder.add_edge("submit_verification", END)

        return builder.compile()

    def _node_inspect_checklist(self, state: OnboardAgentState) -> Dict[str, Any]:
        merchant_id = state["merchant_id"]
        query_text = state.get("query_text", "")
        execution_id = state.get("execution_id", f"exec_onb_{uuid.uuid4().hex[:8]}")
        actor_id = state.get("actor_id", "merchant_user")

        # Security Invariant Check: Block any query asking for password, OTP, or UPI PIN
        sec_check = self.tools.validate_security_invariants(query_text)
        if not sec_check["is_safe"]:
            return {
                "is_security_violation": True,
                "chip_status": "needs_human",
                "action_taken": "SECURITY_VIOLATION_BLOCKED",
                "agent_reply": f"Security Alert: {sec_check['violation']} Paytm Saathi never asks for credentials.",
                "missing_item_card": None,
            }

        checklist = self.tools.get_onboarding_checklist(merchant_id, execution_id=execution_id, actor_id=actor_id)
        if not checklist.get("found"):
            return {
                "checklist": None,
                "action_taken": "APPLICATION_NOT_FOUND",
                "chip_status": "needs_human",
                "agent_reply": f"Could not find an active onboarding application for merchant {merchant_id}.",
                "missing_item_card": None,
            }

        if checklist.get("is_fully_verified"):
            return {
                "checklist": checklist,
                "action_taken": "ALREADY_VERIFIED",
                "chip_status": "verified",
                "agent_reply": f"Namaste! Your shop {checklist.get('store_name')} is already fully KYC VERIFIED and ACTIVE.",
                "missing_item_card": None,
            }

        missing = checklist.get("missing_documents", [])
        blurry = checklist.get("blurry_documents", [])
        can_submit = checklist.get("can_submit_for_verification", False)

        if can_submit:
            return {
                "checklist": checklist,
                "missing_documents": missing,
                "blurry_documents": blurry,
                "current_step": checklist.get("current_step", "READY_FOR_AUTHORIZED_VERIFICATION"),
                "action_taken": "READY_FOR_VERIFICATION",
            }

        return {
            "checklist": checklist,
            "missing_documents": missing,
            "blurry_documents": blurry,
            "current_step": checklist.get("current_step", "DOCUMENTS_REQUIRED"),
            "action_taken": "CHASE_MISSING_DOCUMENT",
        }

    def _node_chase_specific_missing_item(self, state: OnboardAgentState) -> Dict[str, Any]:
        merchant_id = state["merchant_id"]
        checklist = state.get("checklist") or {}
        store_name = checklist.get("store_name", "your shop")
        blurry = state.get("blurry_documents", [])
        missing = state.get("missing_documents", [])
        docs = checklist.get("documents", [])

        # Prioritize blurry documents needing resubmission first
        if blurry:
            doc_type = blurry[0]
            matched_doc = next((d for d in docs if d["document_type"] == doc_type), None)
            specific_reason = (
                matched_doc.get("rejection_reason")
                if matched_doc and matched_doc.get("rejection_reason")
                else f"Your {doc_type.replace('_', ' ').title()} photo is blurry. Please resend a sharp, legible photo."
            )
            title = f"{doc_type.replace('_', ' ').title()} Resubmission Required"
            action_code = "RESUBMIT_BLURRY_DOCUMENT"
        elif missing:
            doc_type = missing[0]
            matched_doc = next((d for d in docs if d["document_type"] == doc_type), None)
            specific_reason = (
                matched_doc.get("rejection_reason")
                if matched_doc and matched_doc.get("rejection_reason")
                else f"Your {doc_type.replace('_', ' ').title()} is missing. Please upload it to proceed."
            )
            title = f"Upload {doc_type.replace('_', ' ').title()}"
            action_code = "UPLOAD_MISSING_DOCUMENT"
        else:
            doc_type = "GENERAL_DOCUMENT"
            specific_reason = "Additional documentation is required to complete KYC."
            title = "Document Review Required"
            action_code = "GENERAL_REVIEW"

        # Create missing document assistance task
        task_res = self.tools.create_missing_document_task(
            merchant_id=merchant_id,
            missing_doc_type=doc_type,
            specific_reason=specific_reason,
        )

        reply = (
            f"KYC Status for {store_name}: Application is incomplete. "
            f"Action needed: {specific_reason} "
            f"You can upload a replacement photo directly through the app."
        )

        card = {
            "type": "ONBOARDING_CHASE_CARD",
            "document_type": doc_type,
            "doc_type": doc_type,
            "is_blurry": bool(blurry),
            "action_code": action_code,
            "title": title,
            "specific_reason": specific_reason,
            "task_id": task_res.get("task_id"),
            "chip_status": "needs_human",
            "retry_allowed": True,
        }

        return {
            "chip_status": "needs_human",
            "agent_reply": reply,
            "missing_item_card": card,
            "action_taken": action_code,
        }

    def _node_submit_verification(self, state: OnboardAgentState) -> Dict[str, Any]:
        merchant_id = state["merchant_id"]
        checklist = state.get("checklist") or {}
        store_name = checklist.get("store_name", "your shop")

        # Invoke simulated authorized verification step
        ver_res = self.tools.submit_for_authorized_verification(merchant_id)

        if ver_res.get("success"):
            reply = (
                f"Congratulations {store_name}! All 3 documents (PAN Card, Bank Proof, Shop Photo) "
                f"passed OCR checks and simulated NSDL & Bank Penny-Drop verification. "
                f"Your Paytm Merchant Account is now ACTIVE and ready to accept payments!"
            )
            chip_status = "verified"
            card = {
                "type": "ONBOARDING_COMPLETED_CARD",
                "title": "KYC Verified & Soundbox Activated",
                "application_status": "ACTIVE",
                "kyc_status": "VERIFIED",
                "verified_documents": ver_res.get("verified_documents", []),
                "chip_status": "verified",
            }
        else:
            reply = (
                f"Verification halted for {store_name}: {ver_res.get('message', 'Requirements pending.')}"
            )
            chip_status = "needs_human"
            card = {
                "type": "ONBOARDING_VERIFICATION_FAILED_CARD",
                "title": "Verification Pending",
                "message": ver_res.get("message"),
                "chip_status": "needs_human",
            }

        return {
            "chip_status": chip_status,
            "agent_reply": reply,
            "missing_item_card": card,
            "action_taken": "AUTHORIZED_VERIFICATION_EXECUTED",
            "verification_result": ver_res,
        }

    def run(
        self,
        merchant_id: str,
        query_text: str = "",
        actor_id: str = "merchant_user",
    ) -> Dict[str, Any]:
        initial_state: OnboardAgentState = {
            "merchant_id": merchant_id,
            "query_text": query_text,
            "execution_id": f"exec_onb_{uuid.uuid4().hex[:8]}",
            "actor_id": actor_id,
            "checklist": None,
            "missing_documents": [],
            "blurry_documents": [],
            "current_step": "INIT",
            "action_taken": "INIT",
            "agent_reply": "",
            "chip_status": "pending",
            "missing_item_card": None,
            "is_security_violation": False,
            "verification_result": None,
        }

        final_state = self.graph.invoke(initial_state)

        return {
            "success": True,
            "agent": "ONBOARD",
            "merchant_id": merchant_id,
            "action_taken": final_state.get("action_taken"),
            "chip_status": final_state.get("chip_status"),
            "agent_reply": final_state.get("agent_reply"),
            "missing_item_card": final_state.get("missing_item_card"),
            "checklist": final_state.get("checklist"),
            "verification_result": final_state.get("verification_result"),
            "is_security_violation": final_state.get("is_security_violation", False),
        }
