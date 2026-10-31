import re
import uuid
from typing import Any, Dict, List, Optional, TypedDict
from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, END
from app.adapters.transaction import MockTransactionAdapter
from app.tools.resolve import ResolveTools
from app.policy.audit import audit_log
from app.schemas.policy import RiskTier

class ResolveAgentState(TypedDict, total=False):
    merchant_id: str
    query_text: str
    tx_ref: Optional[str]
    is_greeting: bool
    execution_id: str
    actor_id: str
    tx_data: Optional[Dict[str, Any]]
    events_data: Optional[List[Dict[str, Any]]]
    branch: str  # A_AUTO_REVERSAL | B_STUCK_REFUND_REVIEW | C_PAYMENT_CONFIRMED | D_FRAUD_ESCALATED | GREETING | UNKNOWN
    agent_reply: str
    explanation_en: str
    explanation_hi: str
    chip_status: str
    approval_card: Optional[Dict[str, Any]]
    case_id: Optional[str]
    loop_count: int

class ResolveAgent:
    """
    Specialist Agent 1: Resolve (Failed or disputed payment complaints).
    Uses LangGraph for deterministic state-machine routing and verifiable action execution.
    """

    def __init__(self, db: Session):
        self.db = db
        self.adapter = MockTransactionAdapter(db)
        self.tools = ResolveTools(self.adapter, db)
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(ResolveAgentState)

        builder.add_node("identify_transaction", self._node_identify_transaction)
        builder.add_node("authoritative_lookup", self._node_authoritative_lookup)
        builder.add_node("route_and_execute", self._node_route_and_execute)

        builder.set_entry_point("identify_transaction")
        builder.add_edge("identify_transaction", "authoritative_lookup")
        builder.add_edge("authoritative_lookup", "route_and_execute")
        builder.add_edge("route_and_execute", END)

        return builder.compile()

    def _node_identify_transaction(self, state: ResolveAgentState) -> Dict[str, Any]:
        loop_count = state.get("loop_count", 0) + 1
        query = (state.get("query_text") or "").strip()
        tx_ref = state.get("tx_ref")
        is_greeting = False

        # Extract UTR or ID patterns from text if not explicitly provided
        if not tx_ref:
            match = re.search(r"(PAYTM_[A-Z0-9_]+|SB-[A-Z0-9]+|txn_[a-z0-9_]+)", query, re.IGNORECASE)
            if match:
                tx_ref = match.group(0).upper()
            elif "250" in query or "alok" in query.lower() or "auto" in query.lower():
                tx_ref = "PAYTM_REV_AUTO_991201"
            elif "500" in query or "deepak" in query.lower() or "stuck" in query.lower() or "refund" in query.lower():
                tx_ref = "PAYTM_STUCK_881920"
            elif "320" in query or "pooja" in query.lower() or "success" in query.lower() or "chime" in query.lower():
                tx_ref = "PAYTM_SUCC_771829"
            elif "1200" in query or "fraud" in query.lower() or "suspicious" in query.lower() or "fake" in query.lower():
                tx_ref = "PAYTM_FRAUD_661904"
            elif re.search(r"\b(failed|stuck|dispute|check payment|transaction|last payment|recent payment)\b", query, re.IGNORECASE):
                # Merchant is asking to check payments but didn't specify amount -> fallback to recent
                recent = self.adapter.get_merchant_recent_transactions(state.get("merchant_id", "mer_sharma_kirana"), limit=1)
                if recent:
                    tx_ref = recent[0].utr_or_ref or recent[0].id
            elif re.search(r"^(hi|hello|hey|namaste|pranam|good\s+morning|good\s+afternoon|good\s+evening)\b", query, re.IGNORECASE):
                is_greeting = True

        return {"tx_ref": tx_ref, "is_greeting": is_greeting, "loop_count": loop_count}

    def _node_authoritative_lookup(self, state: ResolveAgentState) -> Dict[str, Any]:
        if state.get("is_greeting"):
            return {
                "branch": "GREETING",
                "chip_status": "verified",
                "agent_reply": (
                    "Namaste! I am Saathi, your Kirana AI teammate. "
                    "I actively investigate failed, stuck, or unannounced customer payments using authoritative bank records. "
                    "How can I help you today? You can say: 'Customer ₹250 failed', 'Deepak ₹500 stuck reversal', or provide any UTR."
                ),
                "explanation_en": "Saathi payment investigation assistant is active.",
                "explanation_hi": "Paytm Saathi bhugtan jaanch sahayak sakriya hai.",
            }

        tx_ref = state.get("tx_ref")
        execution_id = state.get("execution_id", f"exec_{uuid.uuid4().hex[:8]}")
        actor_id = state.get("actor_id", "merchant_user")

        if not tx_ref:
            return {
                "branch": "UNKNOWN",
                "chip_status": "pending",
                "agent_reply": "Please provide the transaction UTR number or customer name/amount so I can look up the bank records for you.",
                "explanation_en": "Please provide the transaction UTR number or customer name.",
                "explanation_hi": "Kripya transaction UTR number ya customer ka naam batayein.",
            }

        # R0 lookup via constrained tool
        tx_data = self.tools.get_transaction_status(tx_ref, execution_id, actor_id)
        events_data = self.tools.get_related_payment_events(tx_data.get("id", tx_ref), execution_id, actor_id)

        return {
            "tx_data": tx_data,
            "events_data": events_data,
        }

    def _node_route_and_execute(self, state: ResolveAgentState) -> Dict[str, Any]:
        branch = state.get("branch")
        if branch == "GREETING":
            return {
                "branch": "GREETING",
                "chip_status": state.get("chip_status", "verified"),
                "agent_reply": state.get("agent_reply"),
                "explanation_en": state.get("explanation_en"),
                "explanation_hi": state.get("explanation_hi"),
                "approval_card": None,
            }

        if branch == "UNKNOWN":
            return {
                "branch": "UNKNOWN",
                "chip_status": "pending",
                "agent_reply": state.get("agent_reply"),
                "explanation_en": state.get("explanation_en"),
                "explanation_hi": state.get("explanation_hi"),
                "approval_card": None,
            }

        tx_data = state.get("tx_data", {})
        execution_id = state.get("execution_id", f"exec_{uuid.uuid4().hex[:8]}")
        actor_id = state.get("actor_id", "merchant_user")
        merchant_id = state.get("merchant_id", "mer_demo")

        if not tx_data or not tx_data.get("found"):
            return {
                "branch": "NOT_FOUND",
                "chip_status": "needs_human",
                "agent_reply": f"No transaction record found for reference '{state.get('tx_ref')}'. Please verify the UTR or check your customer's UPI app.",
                "explanation_en": "Transaction reference not found in payment switch records.",
                "explanation_hi": "Payment switch records me yeh transaction nahi mila.",
            }

        bank_code = tx_data.get("bank_response_code") or ""
        reversal_status = tx_data.get("reversal_status") or ""
        status = tx_data.get("status") or ""
        tx_id = tx_data.get("id")
        amount_str = tx_data.get("amount_inr")
        utr_str = tx_data.get("utr_or_ref")

        # BRANCH (A): Auto-reversal in progress (NPCI U30)
        if bank_code == "U30_AUTO_REVERSAL" or reversal_status == "IN_PROGRESS":
            exp = self.tools.draft_customer_explanation("AUTO_REVERSAL_IN_PROGRESS", tx_data, execution_id, actor_id)
            reply = (
                f"Investigation complete for {amount_str} (Ref: {utr_str}). "
                f"The payment failed due to a bank timeout, and auto-reversal is already IN PROGRESS. "
                f"Funds will be returned to the customer's account in 24–48 banking hours. "
                f"Do NOT provide goods on credit for this attempt."
            )
            return {
                "branch": "A_AUTO_REVERSAL",
                "chip_status": "verified",
                "agent_reply": reply,
                "explanation_en": exp["explanation_en"],
                "explanation_hi": exp["explanation_hi"],
                "approval_card": None,
            }

        # BRANCH (B): Reversal stuck (NPCI U69, >48h) -> creates refund-review task (never actual refund)
        elif bank_code == "U69_REVERSAL_STUCK" or reversal_status == "STUCK":
            exp = self.tools.draft_customer_explanation("REVERSAL_STUCK_REVIEW_REQUESTED", tx_data, execution_id, actor_id)
            # Create refund review task (R1 internal action)
            review_res = self.tools.request_refund_review(
                merchant_id=merchant_id,
                tx_id=tx_id,
                reason="NPCI auto-reversal timed out (>48 hours elapsed). Customer payment not returned.",
                execution_id=execution_id,
                actor_id=actor_id,
            )

            reply = (
                f"Investigation complete for {amount_str} (Ref: {utr_str}). "
                f"Bank auto-reversal has timed out (>48 hours). "
                f"I have prepared an official Refund Review Request for Paytm operations. "
                f"Please review and authorize the review request below."
            )

            approval_card = {
                "type": "REFUND_REVIEW_APPROVAL",
                "task_id": review_res.get("task_id"),
                "approval_id": review_res.get("approval_id"),
                "title": f"Refund Review Request: {amount_str}",
                "utr": utr_str,
                "customer": tx_data.get("customer_name", "Payer"),
                "risk_tier": "R2",
                "reason": "NPCI auto-reversal SLA exceeded 48h. Requires support credit review.",
                "note": "Authorizing this does NOT deduct from your settlement balance. It queues an operations investigation.",
                "status": "awaiting_approval",
            }

            return {
                "branch": "B_STUCK_REFUND_REVIEW",
                "chip_status": "awaiting_approval",
                "agent_reply": reply,
                "explanation_en": exp["explanation_en"],
                "explanation_hi": exp["explanation_hi"],
                "case_id": review_res.get("task_id"),
                "approval_card": approval_card,
            }

        # BRANCH (C): Payment actually succeeded (Bank 00)
        elif bank_code == "00_SUCCESS" or status == "SUCCESS":
            exp = self.tools.draft_customer_explanation("PAYMENT_CONFIRMED_SUCCESS", tx_data, execution_id, actor_id)
            reply = (
                f"Verified: Transaction of {amount_str} (UTR: {utr_str}) was SUCCESSFUL and credited to your Paytm settlement account. "
                f"Even if the customer's app showed a delay or chime was missed, the funds are safely settled."
            )
            return {
                "branch": "C_PAYMENT_CONFIRMED",
                "chip_status": "verified",
                "agent_reply": reply,
                "explanation_en": exp["explanation_en"],
                "explanation_hi": exp["explanation_hi"],
                "approval_card": None,
            }

        # BRANCH (D): Ambiguous / fraud-flavored (Bank ZA or unknown security hold)
        else:
            case_res = self.tools.create_support_case(
                merchant_id=merchant_id,
                title=f"Security Escalate: Disputed payment {utr_str} ({amount_str})",
                description=(
                    f"Transaction flagged for potential security or terminal mismatch (Code: {bank_code}). "
                    f"Payer VPA: {tx_data.get('payer_vpa')}. Escalated to compliance desk."
                ),
                bucket="needs_human",
                priority="HIGH",
                execution_id=execution_id,
                actor_id=actor_id,
            )
            reply = (
                f"Safety Notice: Transaction {utr_str} ({amount_str}) has an irregular security status (Code: {bank_code}). "
                f"I have escalated this case to the Paytm Compliance and Risk Operations team (Case ID: {case_res.get('case_id')}). "
                f"Do NOT initiate manual payments or issue cash refunds."
            )
            return {
                "branch": "D_FRAUD_ESCALATED",
                "chip_status": "needs_human",
                "agent_reply": reply,
                "explanation_en": "Transaction flagged for risk evaluation and escalated to operations.",
                "explanation_hi": "Is transaction ko suraksha jaanch ke liye compliance team ko bhej diya gaya hai.",
                "case_id": case_res.get("case_id"),
                "approval_card": None,
            }

    def run(self, merchant_id: str, query_text: str, tx_ref: Optional[str] = None, actor_id: str = "merchant_user") -> Dict[str, Any]:
        execution_id = f"exec_resolve_{uuid.uuid4().hex[:10]}"
        initial_state: ResolveAgentState = {
            "merchant_id": merchant_id,
            "query_text": query_text,
            "tx_ref": tx_ref,
            "execution_id": execution_id,
            "actor_id": actor_id,
            "loop_count": 0,
        }

        # Run through LangGraph orchestrator
        final_state = self.graph.invoke(initial_state)

        # Record top-level audit event for Resolve investigation
        audit_log(
            db=self.db,
            actor=actor_id,
            action="RESOLVE_INVESTIGATION_COMPLETED",
            target=final_state.get("tx_ref") or "unknown_ref",
            result=final_state.get("branch", "UNKNOWN"),
            policy_decision_id="dec_resolve_finish",
            idempotency_key=execution_id,
        )

        return {
            "branch": final_state.get("branch"),
            "agent_reply": final_state.get("agent_reply"),
            "explanation_en": final_state.get("explanation_en"),
            "explanation_hi": final_state.get("explanation_hi"),
            "chip_status": final_state.get("chip_status"),
            "tx_ref": final_state.get("tx_ref"),
            "approval_card": final_state.get("approval_card"),
            "case_id": final_state.get("case_id"),
            "is_synthetic": True,
            "environment": "DEMO",
        }
