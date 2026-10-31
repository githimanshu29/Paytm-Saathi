import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.adapters.settlement import ISettlementAdapter
from app.policy.engine import PolicyEngine
from app.policy.audit import audit_log
from app.schemas.policy import ActionProposal, RiskTier
from app.db.models import Task, TaskBucket, ActionApproval, ApprovalDecision, Settlement


def generate_idempotency_key(execution_id: str, action_type: str, target_id: str, params: Dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True)
    raw = f"{execution_id}:{action_type}:{target_id}:{canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class ReconcileTools:
    """
    Constrained, risk-tiered toolset for the Reconcile Specialist Agent (Settlement Copilot).
    Arithmetic is 100% deterministic code in integer minor units (paise) — NEVER float, NEVER LLM.
    """

    def __init__(self, adapter: Optional[ISettlementAdapter] = None, db: Optional[Session] = None):
        self.db = db
        if adapter is not None:
            self.adapter = adapter
        elif db is not None:
            from app.adapters.settlement import MockSettlementAdapter
            self.adapter = MockSettlementAdapter(db)
        else:
            self.adapter = None

    # TOOL 1: get_settlement_summary (R0 Read-Only)
    def get_settlement_summary(
        self,
        merchant_id: str,
        settlement_date: str,
        execution_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="GET_SETTLEMENT_SUMMARY",
            target_id=f"{merchant_id}:{settlement_date}",
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_reconcile",
            parameters={"merchant_id": merchant_id, "settlement_date": settlement_date},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"found": False, "error": "Policy denied settlement summary lookup"}

        record = self.adapter.get_settlement(merchant_id, settlement_date)
        if not record:
            return {
                "found": False,
                "message": f"No settlement batch found for merchant '{merchant_id}' on date '{settlement_date}'.",
            }

        return {
            "found": True,
            "id": record.id,
            "merchant_id": record.merchant_id,
            "settlement_date": record.settlement_date,
            "gross_sales": record.gross_sales,
            "refunds": record.refunds,
            "fees": record.fees,
            "chargebacks": record.chargebacks,
            "net_expected": record.net_expected,
            "net_settled": record.net_settled,
            "discrepancy": record.discrepancy,
            "gross_sales_inr": record.gross_sales_inr,
            "refunds_inr": record.refunds_inr,
            "fees_inr": record.fees_inr,
            "chargebacks_inr": record.chargebacks_inr,
            "net_expected_inr": record.net_expected_inr,
            "net_settled_inr": record.net_settled_inr,
            "discrepancy_inr": record.discrepancy_inr,
            "status": record.status,
            "bank_utr": record.bank_utr,
            "nodal_account": record.nodal_account,
            "dispute_case_id": record.dispute_case_id,
        }

    # TOOL 2: get_settlement_line_items (R0 Read-Only)
    def get_settlement_line_items(
        self,
        merchant_id: str,
        settlement_date: str,
        execution_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="GET_SETTLEMENT_LINE_ITEMS",
            target_id=f"{merchant_id}:{settlement_date}",
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_reconcile",
            parameters={"merchant_id": merchant_id, "settlement_date": settlement_date},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"found": False, "error": "Policy denied line items lookup"}

        items = self.adapter.get_settlement_line_items(merchant_id, settlement_date)
        return {
            "settlement_date": items.settlement_date,
            "merchant_id": items.merchant_id,
            "sales_count": len(items.sales_transactions),
            "refunds_count": len(items.refund_transactions),
            "fees_count": len(items.fee_items),
            "chargebacks_count": len(items.chargeback_items),
            "sales_transactions": [t.model_dump() for t in items.sales_transactions],
            "refund_transactions": [r.model_dump() for r in items.refund_transactions],
            "fee_items": [f.model_dump() for f in items.fee_items],
            "chargeback_items": [c.model_dump() for c in items.chargeback_items],
            "total_sales_paise": items.total_sales_paise,
            "total_refunds_paise": items.total_refunds_paise,
            "total_fees_paise": items.total_fees_paise,
            "total_chargebacks_paise": items.total_chargebacks_paise,
        }

    # TOOL 3: calculate_settlement_difference (R0 Deterministic Integer Code — NEVER Float, NEVER LLM)
    @staticmethod
    def calculate_settlement_difference(
        gross_sales_paise: int,
        refunds_paise: int,
        fees_paise: int,
        chargebacks_paise: int,
        net_settled_paise: int,
    ) -> Dict[str, Any]:
        """
        Pure deterministic code using integer minor units (paise).
        The LLM is completely forbidden from doing arithmetic.
        """
        # Strict integer type enforcement
        gross = int(gross_sales_paise)
        refunds = int(refunds_paise)
        fees = int(fees_paise)
        chargebacks = int(chargebacks_paise)
        settled = int(net_settled_paise)

        # Exact formula: net_expected = gross - refunds - fees - chargebacks
        net_expected = gross - refunds - fees - chargebacks
        difference = settled - net_expected
        is_reconciled = (difference == 0)

        direction = "BALANCED"
        if difference < 0:
            direction = "SHORTFALL"
        elif difference > 0:
            direction = "SURPLUS"

        return {
            "gross_sales_paise": gross,
            "refunds_paise": refunds,
            "fees_paise": fees,
            "chargebacks_paise": chargebacks,
            "net_expected_paise": net_expected,
            "net_settled_paise": settled,
            "difference_paise": difference,
            "discrepancy_abs_paise": abs(difference),
            "is_reconciled": is_reconciled,
            "direction": direction,
            "gross_sales_inr": f"₹{gross / 100:,.2f}",
            "refunds_inr": f"₹{refunds / 100:,.2f}",
            "fees_inr": f"₹{fees / 100:,.2f}",
            "chargebacks_inr": f"₹{chargebacks / 100:,.2f}",
            "net_expected_inr": f"₹{net_expected / 100:,.2f}",
            "net_settled_inr": f"₹{settled / 100:,.2f}",
            "difference_inr": f"₹{abs(difference) / 100:,.2f}",
        }

    # TOOL 4: create_settlement_dispute (R1 Internal Review Case Creation)
    def create_settlement_dispute(
        self,
        merchant_id: str,
        settlement_date: str,
        difference_paise: int,
        reason: str,
        execution_id: str,
        actor_id: str,
        evidence_notes: Optional[str] = None,
        evidence_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Files an internal dispute review case when a genuine mismatch remains after all deductions.
        Guarded against double-dispute creation via idempotency checks.
        """
        diff_int = int(difference_paise)
        diff_inr = f"₹{abs(diff_int) / 100:,.2f}"
        params = {
            "merchant_id": merchant_id,
            "settlement_date": settlement_date,
            "difference_paise": diff_int,
        }
        idempotency_key = generate_idempotency_key(
            execution_id, "CREATE_SETTLEMENT_DISPUTE", f"{merchant_id}:{settlement_date}", params
        )

        # Idempotency check: don't create duplicate case for same merchant & date
        case_title_search = f"%Settlement Dispute%{settlement_date}%"
        existing = (
            self.db.query(Task)
            .filter((Task.merchant_id == merchant_id) & (Task.title.like(case_title_search)))
            .first()
        )
        if existing:
            return {
                "success": True,
                "is_duplicate_idempotent": True,
                "task_id": existing.id,
                "bucket": existing.bucket.value if hasattr(existing.bucket, "value") else str(existing.bucket),
                "dispute_amount_inr": diff_inr,
                "message": f"Settlement dispute review case already exists ({existing.id}).",
                "idempotency_key": idempotency_key,
            }

        # Policy Gate: Proposing dispute review case (R1 internal action)
        proposal = ActionProposal(
            action_type="CREATE_SETTLEMENT_DISPUTE",
            target_id=f"{merchant_id}:{settlement_date}",
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="agent_reconcile",
            parameters=params,
            rationale=f"Unreconciled settlement shortfall of {diff_inr} on {settlement_date}",
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {
                "success": False,
                "error": "Policy engine blocked dispute case creation",
                "decision": decision.model_dump(),
            }

        # Create Task
        task_id = f"case_disp_{idempotency_key[-8:]}"
        desc = (
            f"Settlement discrepancy detected for date {settlement_date}. "
            f"Calculated shortfall: {diff_inr}. "
            f"Reason: {reason}. "
            f"Supporting Evidence: {evidence_notes or 'Bank statement batch extract attached'}"
        )
        task = Task(
            id=task_id,
            tenant_id="tenant_paytm_demo",
            merchant_id=merchant_id,
            title=f"Settlement Dispute {settlement_date} — {diff_inr} Shortfall",
            description=desc,
            bucket=TaskBucket.NEEDS_HUMAN,
            priority="HIGH",
            assigned_to="Paytm Nodal Settlement Ops",
            evidence_notes=evidence_notes or f"Nodal reconciliation statement extract for {settlement_date}",
            evidence_url=evidence_url or f"https://paytm.demo/evidence/nodal_{settlement_date}.pdf",
            dispute_amount=abs(diff_int),
            is_synthetic=True,
            environment="DEMO",
        )
        self.db.add(task)

        # Update settlement record if present
        settlement = (
            self.db.query(Settlement)
            .filter((Settlement.merchant_id == merchant_id) & (Settlement.settlement_date == settlement_date))
            .first()
        )
        if settlement:
            settlement.dispute_case_id = task.id
            settlement.status = "DISPUTED"
            settlement.evidence_attached = desc

        self.db.commit()

        # Audit event
        audit_log(
            db=self.db,
            actor=actor_id,
            action="CREATE_SETTLEMENT_DISPUTE",
            target=task.id,
            result="CONFIRMED",
            policy_decision_id=decision.decision_id,
            idempotency_key=idempotency_key,
        )

        return {
            "success": True,
            "is_duplicate_idempotent": False,
            "task_id": task.id,
            "bucket": "needs_human",
            "dispute_amount_inr": diff_inr,
            "dispute_amount_paise": abs(diff_int),
            "settlement_date": settlement_date,
            "message": f"Settlement dispute case successfully opened ({task.id}) for human review.",
            "idempotency_key": idempotency_key,
        }
