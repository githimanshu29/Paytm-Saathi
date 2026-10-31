import hashlib
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.adapters.onboard import IOnboardAdapter, MockOnboardAdapter
from app.db.models import Task, TaskBucket, AuditEvent, Merchant
from app.policy.engine import PolicyEngine
from app.policy.audit import audit_log
from app.schemas.policy import ActionProposal, RiskTier


def generate_idempotency_key(execution_id: str, action_type: str, target_id: str, params: Dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True)
    raw = f"{execution_id}:{action_type}:{target_id}:{canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class OnboardTools:
    """
    Constrained, risk-tiered toolset for the Onboard Specialist Agent (KYC Closer).
    Core Invariants:
    1. Candidate OCR fields are explicitly UNTRUSTED.
    2. OCR or LLM alone CANNOT set kyc_status = 'VERIFIED' or 'REJECTED'.
    3. Asking for a password, OTP, or UPI PIN is strictly prohibited and blocked by PolicyEngine.
    4. Only submit_for_authorized_verification (simulated verification system) can activate an application.
    """

    PROHIBITED_CREDENTIAL_TERMS = ["password", "otp", "upi pin", "mpin", "atm pin", "cvv"]

    def __init__(
        self,
        db_or_adapter: Optional[Any] = None,
        onboard_adapter: Optional[IOnboardAdapter] = None,
        db: Optional[Session] = None,
    ):
        if isinstance(db_or_adapter, Session):
            db = db_or_adapter
        elif db_or_adapter is not None and hasattr(db_or_adapter, "get_onboarding_checklist"):
            onboard_adapter = db_or_adapter

        self.db = db
        self.onboard_adapter = onboard_adapter or (MockOnboardAdapter(db) if db else None)

    # TOOL 1: get_onboarding_checklist (R0 Read-Only)
    def get_onboarding_checklist(
        self,
        merchant_id: str,
        execution_id: str = "exec_chk_get",
        actor_id: str = "agent_onboard",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="GET_ONBOARDING_CHECKLIST",
            target_id=merchant_id,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_onboard",
            parameters={"merchant_id": merchant_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.onboard_adapter:
            return {"found": False, "reason": "Access denied or adapter unavailable."}

        checklist = self.onboard_adapter.get_onboarding_checklist(merchant_id)
        if not checklist:
            return {"found": False, "reason": f"No onboarding application found for merchant {merchant_id}."}

        return {
            "found": True,
            "merchant_id": checklist.merchant_id,
            "store_name": checklist.store_name,
            "city": checklist.city,
            "onboarding_status": checklist.onboarding_status,
            "kyc_status": checklist.kyc_status,
            "current_step": checklist.current_step,
            "missing_documents": checklist.missing_documents,
            "blurry_documents": checklist.blurry_documents,
            "can_submit_for_verification": checklist.can_submit_for_verification,
            "is_fully_verified": checklist.is_fully_verified,
            "documents": [
                {
                    "document_type": d.document_type,
                    "status": d.status,
                    "file_name": d.file_name,
                    "ocr_quality_flag": d.ocr_quality_flag,
                    "is_ocr_passed": d.is_ocr_passed,
                    "rejection_reason": d.rejection_reason,
                    "candidate_fields": d.ocr_candidate_fields,
                    "authorized_verification_status": d.authorized_verification_status,
                }
                for d in checklist.documents
            ],
        }

    # TOOL 2: get_document_receipt_status (R0 Read-Only)
    def get_document_receipt_status(
        self,
        merchant_id: str,
        document_type: str,
        execution_id: str = "exec_doc_receipt",
        actor_id: str = "agent_onboard",
    ) -> Dict[str, Any]:
        checklist = self.get_onboarding_checklist(merchant_id, execution_id=execution_id, actor_id=actor_id)
        if not checklist.get("found"):
            return {"found": False, "status": "UNKNOWN"}

        docs = checklist.get("documents", [])
        doc = next((d for d in docs if d["document_type"] == document_type), None)
        if not doc:
            return {"found": False, "status": "MISSING", "message": f"{document_type} is not received."}

        return {
            "found": True,
            "document_type": doc["document_type"],
            "status": doc["status"],
            "ocr_quality_flag": doc["ocr_quality_flag"],
            "is_ocr_passed": doc["is_ocr_passed"],
            "rejection_reason": doc["rejection_reason"],
        }

    # TOOL 3: extract_document_fields (R0 OCR Candidate Extraction - Untrusted)
    def extract_document_fields(
        self,
        document_type: str,
        file_name: str,
        quality_override: Optional[str] = None,
        execution_id: str = "exec_ocr_extract",
        actor_id: str = "agent_onboard",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="EXTRACT_DOCUMENT_FIELDS_OCR",
            target_id=f"{document_type}:{file_name}",
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_onboard",
            parameters={"document_type": document_type, "file_name": file_name},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.onboard_adapter:
            return {"success": False, "error": "Policy denied OCR extraction."}

        ocr_res = self.onboard_adapter.extract_document_fields(
            document_type=document_type,
            file_name=file_name,
            quality_override=quality_override,
        )

        return {
            "success": True,
            "document_type": ocr_res.document_type,
            "file_name": ocr_res.file_name,
            "ocr_quality_flag": ocr_res.ocr_quality_flag,
            "is_ocr_passed": ocr_res.is_ocr_passed,
            "confidence": ocr_res.confidence,
            "candidate_fields": ocr_res.candidate_fields,
            "rejection_reason": ocr_res.rejection_reason,
            "disclaimer": ocr_res.disclaimer,
            "is_untrusted_candidate": True,
        }

    # TOOL 4: create_missing_document_task (R1 Internal Assistance Task)
    def create_missing_document_task(
        self,
        merchant_id: str,
        missing_doc_type: str,
        specific_reason: str,
        execution_id: str = "exec_task_missing_doc",
        actor_id: str = "agent_onboard",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="CREATE_MISSING_DOCUMENT_TASK",
            target_id=f"{merchant_id}:{missing_doc_type}",
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="agent_onboard",
            parameters={
                "merchant_id": merchant_id,
                "missing_doc_type": missing_doc_type,
                "specific_reason": specific_reason,
            },
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"success": False, "error": f"Policy denied task: {decision.reason_codes}"}

        idempotency_key = generate_idempotency_key(
            execution_id=execution_id,
            action_type="CREATE_MISSING_DOCUMENT_TASK",
            target_id=merchant_id,
            params={"missing_doc_type": missing_doc_type},
        )

        # Idempotency check: avoid duplicate pending tasks for same document
        if self.db:
            existing = (
                self.db.query(Task)
                .filter(
                    (Task.merchant_id == merchant_id)
                    & (Task.title.like(f"%KYC Document Follow-up: {missing_doc_type}%"))
                )
                .first()
            )
            if existing:
                return {
                    "success": True,
                    "task_id": existing.id,
                    "is_duplicate_idempotent": True,
                    "message": f"Task already exists for {missing_doc_type}.",
                }

        merchant = self.db.query(Merchant).filter_by(id=merchant_id).first() if self.db else None
        store_name = merchant.store_name if merchant else "Merchant Shop"

        task = Task(
            tenant_id=merchant.tenant_id if merchant else "tenant_paytm_demo",
            merchant_id=merchant_id,
            title=f"KYC Document Follow-up: {missing_doc_type} · {store_name}",
            description=f"Action required: {specific_reason}. Merchant contact: {merchant.phone if merchant else 'N/A'}.",
            bucket=TaskBucket.NEEDS_HUMAN,
            priority="HIGH",
            assigned_to="Amit V. (Sales Rep)",
            is_synthetic=True,
            environment="DEMO",
        )
        if self.db:
            self.db.add(task)
            self.db.commit()
            self.db.refresh(task)

            audit_log(
                db=self.db,
                actor=actor_id,
                action="CREATE_MISSING_DOCUMENT_TASK",
                target=task.id,
                result="CONFIRMED",
                policy_decision_id=decision.decision_id,
                idempotency_key=idempotency_key,
            )

        return {
            "success": True,
            "task_id": task.id if self.db else "task_mock_missing",
            "bucket": "needs_human",
            "message": f"Missing document assist task created for {missing_doc_type}.",
        }

    # TOOL 5: submit_for_authorized_verification (R1 Simulated Authorized Verification Step)
    def submit_for_authorized_verification(
        self,
        merchant_id: str,
        execution_id: str = "exec_submit_verify",
        actor_id: str = "agent_onboard",
    ) -> Dict[str, Any]:
        """
        Sends application to the simulated authorized external verification step.
        The agent itself cannot verify — it only submits to the authoritative verification system.
        """
        proposal = ActionProposal(
            action_type="SUBMIT_AUTHORIZED_KYC_VERIFICATION",
            target_id=merchant_id,
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="agent_onboard",
            parameters={"merchant_id": merchant_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"success": False, "error": f"Policy denied submission: {decision.reason_codes}"}

        if not self.onboard_adapter:
            return {"success": False, "error": "Onboard adapter not configured."}

        res = self.onboard_adapter.submit_for_authorized_verification(merchant_id)
        return {
            "success": res.success,
            "merchant_id": res.merchant_id,
            "application_status": res.application_status,
            "kyc_status": res.kyc_status,
            "message": res.message,
            "verified_documents": res.verified_documents,
            "audit_event_id": res.audit_event_id,
        }

    # SECURITY VALIDATION: Credential Safety Gate (Disallowed Action)
    def validate_security_invariants(self, text: str) -> Dict[str, Any]:
        """
        Ensures the agent NEVER asks for password, OTP, or UPI PIN.
        """
        text_lower = text.lower()
        for term in self.PROHIBITED_CREDENTIAL_TERMS:
            if term in text_lower:
                return {
                    "is_safe": False,
                    "violation": f"Asking for '{term}' is strictly prohibited under banking safety policies.",
                }
        return {"is_safe": True, "violation": None}
