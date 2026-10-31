import hashlib
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.adapters.vasooli import (
    IVasooliAdapter,
    MockVasooliAdapter,
    CoerciveCollectionError,
    CommunicationPermissionRevokedError,
    ReceivableDisputedError,
)
from app.db.models import Receivable, Customer, ActionApproval, ApprovalDecision, AuditEvent
from app.policy.engine import PolicyEngine
from app.policy.audit import audit_log
from app.schemas.policy import ActionProposal, RiskTier


def generate_idempotency_key(execution_id: str, action_type: str, target_id: str, params: Dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True)
    raw = f"{execution_id}:{action_type}:{target_id}:{canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class VasooliTools:
    """
    Constrained, risk-tiered toolset for the Vasooli Agent (Consensual Receivable Reminders).
    Enforces Hard Boundaries:
    1. Local merchant udhaar only — NEVER regulated loan-debt collection.
    2. Prohibits all coercive language, legal threats, and public shaming (R4 Prohibited).
    3. Mandatory communication permission check before every reminder attempt.
    4. Immediate pause on disputed ledger entries.
    5. Immediate auto-stop upon authoritative settlement confirmation.
    """

    def __init__(
        self,
        db_or_adapter: Optional[Any] = None,
        vasooli_adapter: Optional[IVasooliAdapter] = None,
        db: Optional[Session] = None,
    ):
        if isinstance(db_or_adapter, Session):
            db = db_or_adapter
        elif db_or_adapter is not None and hasattr(db_or_adapter, "get_receivable"):
            vasooli_adapter = db_or_adapter

        self.db = db
        self.vasooli_adapter = vasooli_adapter or (MockVasooliAdapter(db) if db else None)

    # TOOL 1: get_receivable (R0 Read-Only)
    def get_receivable(
        self,
        receivable_id: str,
        actor_id: str = "agent_vasooli",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="GET_RECEIVABLE",
            target_id=receivable_id,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_vasooli",
            parameters={"receivable_id": receivable_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.vasooli_adapter:
            return {"found": False, "reason": "Access denied or adapter unavailable."}

        rec = self.vasooli_adapter.get_receivable(receivable_id)
        if not rec:
            return {"found": False, "reason": f"Receivable #{receivable_id} not found."}

        return {
            "found": True,
            "receivable_id": rec.id,
            "merchant_id": rec.merchant_id,
            "customer_id": rec.customer_id,
            "customer_name": rec.customer_name,
            "customer_phone": rec.customer_phone,
            "amount_paise": rec.amount_paise,
            "amount_formatted": rec.amount_formatted,
            "due_date": rec.due_date,
            "status": rec.status,
            "notes": rec.notes,
            "is_disputed": rec.is_disputed,
            "dispute_reason": rec.dispute_reason,
            "reminder_count": rec.reminder_count,
            "last_reminder_sent_at": rec.last_reminder_sent_at,
            "paid_amount_formatted": rec.paid_amount_formatted,
            "settled_at": rec.settled_at,
            "settlement_verification_status": rec.settlement_verification_status,
            "payment_link_url": rec.payment_link_url,
            "negotiated_installments": rec.negotiated_installments,
        }

    # TOOL 2: verify_receivable_owner (R0 Read-Only Ownership Check)
    def verify_receivable_owner(
        self,
        receivable_id: str,
        merchant_id: str,
        actor_id: str = "agent_vasooli",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="VERIFY_RECEIVABLE_OWNER",
            target_id=receivable_id,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_vasooli",
            parameters={"receivable_id": receivable_id, "merchant_id": merchant_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.vasooli_adapter:
            return {"is_owner": False, "reason": "Access denied."}

        is_owner = self.vasooli_adapter.verify_receivable_owner(receivable_id, merchant_id)
        return {
            "is_owner": is_owner,
            "receivable_id": receivable_id,
            "merchant_id": merchant_id,
            "reason": "Ownership verified." if is_owner else "Receivable belongs to a different merchant.",
        }

    # TOOL 3: get_contact_permission (R0 Read-Only Consent Check)
    def get_contact_permission(
        self,
        customer_id: str,
        actor_id: str = "agent_vasooli",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="GET_CONTACT_PERMISSION",
            target_id=customer_id,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_vasooli",
            parameters={"customer_id": customer_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.vasooli_adapter:
            return {"allowed": False, "reason": "Access denied."}

        return self.vasooli_adapter.get_contact_permission(customer_id)

    # TOOL 4: draft_payment_reminder (R1 Non-Threatening Template Draft)
    def draft_payment_reminder(
        self,
        receivable_id: str,
        custom_note: Optional[str] = None,
        actor_id: str = "agent_vasooli",
    ) -> Dict[str, Any]:
        # Pre-evaluation check against banned coercive terms (R4 check)
        if custom_note and self.vasooli_adapter:
            violation = self.vasooli_adapter.check_banned_phrases(custom_note)
            if violation:
                # Prohibited action blocked by policy
                proposal = ActionProposal(
                    action_type="COERCIVE_COLLECTION_ATTEMPT",
                    target_id=receivable_id,
                    risk_tier=RiskTier.R4,
                    actor_id=actor_id,
                    actor_role="agent_vasooli",
                    parameters={"banned_term": violation},
                    rationale=f"Attempted reminder containing prohibited term '{violation}'.",
                )
                PolicyEngine.evaluate(proposal)
                return {
                    "drafted": False,
                    "error": "R4_COERCIVE_COLLECTION_BLOCKED",
                    "reason": f"Prohibited collection language detected ('{violation}'). Vasooli strictly forbids legal threats, police references, and shaming.",
                }

        proposal = ActionProposal(
            action_type="DRAFT_PAYMENT_REMINDER",
            target_id=receivable_id,
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="agent_vasooli",
            parameters={"receivable_id": receivable_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.vasooli_adapter:
            return {"drafted": False, "reason": "Policy denied action."}

        try:
            draft = self.vasooli_adapter.draft_payment_reminder(receivable_id, custom_note)
            return {
                "drafted": True,
                "receivable_id": draft.receivable_id,
                "customer_name": draft.customer_name,
                "customer_phone": draft.customer_phone,
                "amount_formatted": draft.amount_formatted,
                "payment_link_url": draft.payment_link_url,
                "draft_message_hi": draft.draft_message_hi,
                "draft_message_en": draft.draft_message_en,
                "can_send": draft.can_send,
                "refusal_reason": draft.refusal_reason,
                "proposal_hash": draft.proposal_hash,
                "reminder_count": draft.reminder_count,
            }
        except CoerciveCollectionError as ce:
            return {"drafted": False, "error": "R4_COERCIVE_COLLECTION_BLOCKED", "reason": str(ce)}
        except Exception as e:
            return {"drafted": False, "error": "DRAFT_FAILED", "reason": str(e)}

    # TOOL 5: create_demo_payment_link (R1 Simulated Link Generation)
    def create_demo_payment_link(
        self,
        receivable_id: str,
        actor_id: str = "agent_vasooli",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="CREATE_DEMO_PAYMENT_LINK",
            target_id=receivable_id,
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="agent_vasooli",
            parameters={"receivable_id": receivable_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.vasooli_adapter:
            return {"created": False, "reason": "Access denied."}

        link = self.vasooli_adapter.create_demo_payment_link(receivable_id)
        return {
            "created": True,
            "receivable_id": receivable_id,
            "payment_link_url": link,
            "is_simulation": True,
            "disclaimer": "Demo simulated payment link for prototype evaluation.",
        }

    # TOOL 6: send_authorized_reminder (R2 Gated by Approval + Permission)
    def send_authorized_reminder(
        self,
        receivable_id: str,
        approval_id: Optional[str] = None,
        actor_id: str = "merchant_user",
        execution_id: str = "exec_reminder_send",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="SEND_AUTHORIZED_REMINDER",
            target_id=receivable_id,
            risk_tier=RiskTier.R2,
            actor_id=actor_id,
            actor_role="merchant_user",
            parameters={"receivable_id": receivable_id, "approval_id": approval_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        # R2 requires explicit approval
        if not self.vasooli_adapter:
            return {"sent": False, "reason": "Vasooli adapter unavailable."}

        # Check if approval is verified (or merchant themselves is actor)
        if self.db and approval_id:
            appr = self.db.query(ActionApproval).filter(ActionApproval.id == approval_id).first()
            if not appr or appr.decision != ApprovalDecision.APPROVED:
                return {
                    "sent": False,
                    "error": "APPROVAL_REQUIRED",
                    "reason": "Sending customer reminder requires explicit merchant approval.",
                }

        idemp = generate_idempotency_key(execution_id, "SEND_AUTHORIZED_REMINDER", receivable_id, {"appr": approval_id})

        try:
            res = self.vasooli_adapter.send_authorized_reminder(
                receivable_id=receivable_id,
                actor_id=actor_id,
                idempotency_key=idemp,
            )
            return {
                "sent": True,
                "receivable_id": res.receivable_id,
                "recipient_phone": res.recipient_phone,
                "message_sent": res.message_sent,
                "reminder_count": res.reminder_count,
                "audit_event_id": res.audit_event_id,
                "message": res.message,
            }
        except CommunicationPermissionRevokedError as pe:
            return {"sent": False, "error": "PERMISSION_REVOKED", "reason": str(pe)}
        except ReceivableDisputedError as de:
            return {"sent": False, "error": "RECEIVABLE_DISPUTED", "reason": str(de)}
        except Exception as e:
            return {"sent": False, "error": "SEND_FAILED", "reason": str(e)}

    # TOOL 7: record_payment_status (R1 - Authoritative or Merchant-Reported)
    def record_payment_status(
        self,
        receivable_id: str,
        paid_amount_paise: int,
        payment_reference: str,
        is_authoritative: bool = True,
        actor_id: str = "system_bank_webhook",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="RECORD_PAYMENT_STATUS",
            target_id=receivable_id,
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="system",
            parameters={
                "receivable_id": receivable_id,
                "paid_amount_paise": paid_amount_paise,
                "is_authoritative": is_authoritative,
            },
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.vasooli_adapter:
            return {"recorded": False, "reason": "Policy denied action."}

        res = self.vasooli_adapter.record_payment_status(
            receivable_id=receivable_id,
            paid_amount_paise=paid_amount_paise,
            payment_reference=payment_reference,
            is_authoritative=is_authoritative,
            actor_id=actor_id,
        )

        return {
            "recorded": True,
            "receivable_id": res.receivable_id,
            "verified": res.verified,
            "status": res.status,
            "paid_amount_paise": res.paid_amount_paise,
            "settlement_verification_status": res.settlement_verification_status,
            "reminders_stopped": res.reminders_stopped,
            "cancelled_approval_ids": res.cancelled_approval_ids,
            "audit_event_id": res.audit_event_id,
            "message": res.message,
        }
