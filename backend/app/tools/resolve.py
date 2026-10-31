import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.adapters.transaction import ITransactionAdapter, TransactionRecord, PaymentEventRecord
from app.policy.engine import PolicyEngine
from app.policy.audit import audit_log
from app.schemas.policy import ActionProposal, RiskTier, PolicyDecision
from app.db.models import Task, TaskBucket, ActionApproval, ApprovalDecision, AuditEvent

def generate_idempotency_key(execution_id: str, action_type: str, target_id: str, params: Dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True)
    raw = f"{execution_id}:{action_type}:{target_id}:{canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

class ResolveTools:
    """
    Risk-tiered constrained toolset for the Resolve Specialist Agent.
    Every side-effecting action passes through PolicyEngine, idempotency check, and verification.
    """

    def __init__(self, adapter: ITransactionAdapter, db: Session):
        self.adapter = adapter
        self.db = db

    # TOOL 1: get_transaction_status (R0 Read-Only)
    def get_transaction_status(self, tx_ref: str, execution_id: str, actor_id: str) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="GET_TRANSACTION_STATUS",
            target_id=tx_ref,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_resolve",
            parameters={"tx_ref": tx_ref},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"error": "Policy denied action", "decision": decision.model_dump()}

        tx = self.adapter.get_transaction_by_ref(tx_ref)
        if not tx:
            # Fallback to direct ID lookup
            tx = self.adapter.get_transaction(tx_ref)

        if not tx:
            return {"found": False, "message": f"No transaction record found matching '{tx_ref}'."}

        return {
            "found": True,
            "id": tx.id,
            "merchant_id": tx.merchant_id,
            "amount_paise": tx.amount,
            "amount_inr": f"₹{tx.amount / 100:,.2f}",
            "status": tx.status,
            "bank_response_code": tx.bank_response_code,
            "reversal_status": tx.reversal_status,
            "payment_rail": tx.payment_rail,
            "utr_or_ref": tx.utr_or_ref,
            "customer_name": tx.customer_name,
            "payer_vpa": tx.payer_vpa,
            "created_at": tx.created_at.isoformat(),
        }

    # TOOL 2: get_related_payment_events (R0 Read-Only)
    def get_related_payment_events(self, tx_id: str, execution_id: str, actor_id: str) -> List[Dict[str, Any]]:
        proposal = ActionProposal(
            action_type="GET_PAYMENT_EVENTS",
            target_id=tx_id,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_resolve",
            parameters={"tx_id": tx_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return []

        events = self.adapter.get_related_payment_events(tx_id)
        return [
            {
                "event_id": ev.event_id,
                "event_type": ev.event_type,
                "description": ev.description,
                "timestamp": ev.timestamp.isoformat(),
                "source": ev.source,
            }
            for ev in events
        ]

    # TOOL 3: draft_customer_explanation (R1 Internal/Reversible)
    def draft_customer_explanation(
        self,
        scenario: str,
        tx_data: Dict[str, Any],
        execution_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="DRAFT_CUSTOMER_EXPLANATION",
            target_id=tx_data.get("id", "unknown"),
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="agent_resolve",
            parameters={"scenario": scenario},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"error": "Policy denied action"}

        amount_str = tx_data.get("amount_inr", "amount")
        utr_str = tx_data.get("utr_or_ref", "N/A")

        if scenario == "AUTO_REVERSAL_IN_PROGRESS":
            english = (
                f"Your payment of {amount_str} (Ref: {utr_str}) was interrupted due to a bank switch timeout. "
                f"NPCI auto-reversal is IN PROGRESS. The funds will be automatically returned to the payer's bank account "
                f"within 24 to 48 banking hours. No duplicate payment is required."
            )
            hindi = (
                f"Aapka {amount_str} ka bhugtan bank timeout ke kaaran pura nahi ho saka. "
                f"Auto-reversal shuru ho chuka hai. Paisa 24-48 ghante ke andar customer ke bank khate me wapas aa jayega."
            )
        elif scenario == "PAYMENT_CONFIRMED_SUCCESS":
            english = (
                f"Good news! The transaction of {amount_str} (UTR: {utr_str}) was SUCCESSFUL and credited to your Paytm settlement account. "
                f"The payment is confirmed by your bank."
            )
            hindi = (
                f"Badhai! {amount_str} ka bhugtan (UTR: {utr_str}) safal raha hai aur aapke Paytm khate me jama ho chuka hai."
            )
        elif scenario == "REVERSAL_STUCK_REVIEW_REQUESTED":
            english = (
                f"The transaction of {amount_str} (Ref: {utr_str}) exceeded standard bank auto-reversal limits (>48h). "
                f"A refund review request has been created for human operations review. Refund will NOT be deducted from merchant funds."
            )
            hindi = (
                f"{amount_str} ke bhugtan me 48 ghante se adhik samay lag gaya hai. "
                f"Hamne Paytm support team ke paas refund review request darj kar di hai."
            )
        else:
            english = f"Transaction {utr_str} status is currently under investigation by Paytm Saathi."
            hindi = f"Bhugtan {utr_str} ki jaanch Paytm Saathi dwara ki ja rahi hai."

        return {
            "scenario": scenario,
            "explanation_en": english,
            "explanation_hi": hindi,
            "policy_decision_id": decision.decision_id,
        }

    # TOOL 4: request_refund_review (R1 Internal Review Creation — NOT R3 Refund Execution)
    def request_refund_review(
        self,
        merchant_id: str,
        tx_id: str,
        reason: str,
        execution_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        tx = self.adapter.get_transaction(tx_id)
        if not tx:
            return {"success": False, "error": f"Transaction {tx_id} not found"}

        params = {"merchant_id": merchant_id, "tx_id": tx_id, "amount": tx.amount, "reason": reason}
        idempotency_key = generate_idempotency_key(execution_id, "REQUEST_REFUND_REVIEW", tx_id, params)

        # Idempotency Check: Don't duplicate task if already created
        existing_task = self.db.query(Task).filter(
            (Task.merchant_id == merchant_id) & (Task.title.like(f"%{tx.utr_or_ref or tx_id}%"))
        ).first()

        if existing_task:
            existing_appr = self.db.query(ActionApproval).filter_by(task_id=existing_task.id).first()
            return {
                "success": True,
                "is_duplicate_idempotent": True,
                "task_id": existing_task.id,
                "approval_id": existing_appr.id if existing_appr else f"appr_{existing_task.id}",
                "bucket": existing_task.bucket.value,
                "amount_inr": f"₹{tx.amount / 100:,.2f}",
                "utr": tx.utr_or_ref,
                "message": f"Refund review request already exists (Case {existing_task.id}).",
                "idempotency_key": idempotency_key,
            }

        # Policy Gate: Proposing refund review (R1 internal action)
        proposal = ActionProposal(
            action_type="REQUEST_REFUND_REVIEW",
            target_id=tx_id,
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="agent_resolve",
            parameters=params,
            rationale=reason,
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"success": False, "error": "Policy engine blocked request", "decision": decision.model_dump()}

        # Create Task in awaiting_approval bucket
        task = Task(
            id=f"case_refund_rev_{hashlib.md5(idempotency_key.encode()).hexdigest()[:8]}",
            tenant_id=tx.merchant_id,  # using merchant_id as tenant scope
            merchant_id=merchant_id,
            title=f"Refund Review Request: UTR {tx.utr_or_ref or tx_id} (₹{tx.amount / 100})",
            description=f"Auto-reversal timed out (U69). Merchant requested refund review for customer {tx.customer_name or 'Payer'}. Reason: {reason}",
            bucket=TaskBucket.AWAITING_APPROVAL,
            priority="HIGH",
            assigned_to="Support Review Team",
            is_synthetic=True,
            environment="DEMO",
        )
        self.db.add(task)
        self.db.flush()

        # Create linked ActionApproval gate (R2 risk level for merchant confirmation)
        approval = ActionApproval(
            id=f"appr_{task.id}",
            tenant_id=merchant_id,
            task_id=task.id,
            approver=f"Merchant ({merchant_id})",
            decision=ApprovalDecision.PENDING,
            reason=f"Authorize submission of refund investigation for ₹{tx.amount / 100}",
            risk_tier="R2",
            proposal_hash=idempotency_key,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            is_synthetic=True,
            environment="DEMO",
        )
        self.db.add(approval)
        self.db.commit()

        # Verification step: Re-query from mock source of truth
        verified_task = self.db.query(Task).filter_by(id=task.id).first()
        confirmed = verified_task is not None and verified_task.bucket == TaskBucket.AWAITING_APPROVAL

        # Log audit event
        audit_log(
            db=self.db,
            actor=actor_id,
            action="REQUEST_REFUND_REVIEW",
            target=task.id,
            result="CONFIRMED" if confirmed else "ATTEMPTED_FAILED",
            policy_decision_id=decision.decision_id,
            idempotency_key=idempotency_key,
        )

        return {
            "success": True,
            "is_duplicate_idempotent": False,
            "task_id": task.id,
            "approval_id": approval.id,
            "bucket": "awaiting_approval",
            "amount_inr": f"₹{tx.amount / 100:,.2f}",
            "utr": tx.utr_or_ref,
            "message": "Refund review task created and queued for human operations.",
            "idempotency_key": idempotency_key,
        }

    # TOOL 5: create_support_case (R1 Internal / Escalation)
    def create_support_case(
        self,
        merchant_id: str,
        title: str,
        description: str,
        bucket: str,
        priority: str,
        execution_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        params = {"merchant_id": merchant_id, "title": title, "bucket": bucket}
        idempotency_key = generate_idempotency_key(execution_id, "CREATE_SUPPORT_CASE", merchant_id, params)

        # Idempotency check
        existing = self.db.query(Task).filter(
            (Task.merchant_id == merchant_id) & (Task.title == title)
        ).first()

        if existing:
            return {
                "success": True,
                "is_duplicate_idempotent": True,
                "case_id": existing.id,
                "bucket": existing.bucket.value,
                "idempotency_key": idempotency_key,
            }

        proposal = ActionProposal(
            action_type="CREATE_SUPPORT_CASE",
            target_id=merchant_id,
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="agent_resolve",
            parameters=params,
            rationale=description,
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"success": False, "error": "Policy engine blocked case creation"}

        bucket_enum = TaskBucket.NEEDS_HUMAN if bucket == "needs_human" else TaskBucket.PENDING

        task = Task(
            id=f"case_esc_{hashlib.md5(idempotency_key.encode()).hexdigest()[:8]}",
            tenant_id=merchant_id,
            merchant_id=merchant_id,
            title=title,
            description=description,
            bucket=bucket_enum,
            priority=priority,
            assigned_to="Compliance & Security Officer" if bucket == "needs_human" else "Support Desk",
            is_synthetic=True,
            environment="DEMO",
        )
        self.db.add(task)
        self.db.commit()

        # Audit event
        audit_log(
            db=self.db,
            actor=actor_id,
            action="CREATE_SUPPORT_CASE",
            target=task.id,
            result="CONFIRMED",
            policy_decision_id=decision.decision_id,
            idempotency_key=idempotency_key,
        )

        return {
            "success": True,
            "is_duplicate_idempotent": False,
            "case_id": task.id,
            "bucket": bucket_enum.value,
            "idempotency_key": idempotency_key,
        }

    # TOOL 6: execute_refund (R3 Prohibited / Disabled in prototype)
    def execute_refund(self, tx_id: str, amount_paise: int, actor_id: str) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="EXECUTE_REFUND",
            target_id=tx_id,
            risk_tier=RiskTier.R3,
            actor_id=actor_id,
            actor_role="agent_resolve",
            parameters={"tx_id": tx_id, "amount_paise": amount_paise},
        )
        decision = PolicyEngine.evaluate(proposal)
        # PolicyEngine R3 rule blocks financial execution in this prototype
        audit_log(
            db=self.db,
            actor=actor_id,
            action="EXECUTE_REFUND_BLOCKED",
            target=tx_id,
            result="BLOCKED_BY_POLICY",
            policy_decision_id=decision.decision_id,
        )
        return {
            "allowed": False,
            "executed": False,
            "error": "Direct refund execution is disabled in this prototype (R3 Financial Action). Please create a refund review task instead.",
            "decision": decision.model_dump(),
        }
