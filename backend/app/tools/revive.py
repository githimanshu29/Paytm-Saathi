import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.adapters.revive import IReviveAdapter, MockReviveAdapter
from app.adapters.device import IDeviceAdapter, MockDeviceAdapter
from app.adapters.settlement import ISettlementAdapter, MockSettlementAdapter
from app.policy.engine import PolicyEngine
from app.policy.audit import audit_log
from app.schemas.policy import ActionProposal, RiskTier
from app.db.models import Task, TaskBucket, Merchant, MerchantFollowup


def generate_idempotency_key(execution_id: str, action_type: str, target_id: str, params: Dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True)
    raw = f"{execution_id}:{action_type}:{target_id}:{canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class ReviveTools:
    """
    Constrained, risk-tiered toolset for the Revive Specialist Agent (Dormant Merchant Reactivation).
    Diagnoses real root causes by reusing Device and Settlement adapters.
    Treats 'follow-up sent' and 'merchant actually revived' as two strictly separate outcomes.
    """

    def __init__(
        self,
        db_or_adapter: Optional[Any] = None,
        revive_adapter: Optional[IReviveAdapter] = None,
        device_adapter: Optional[IDeviceAdapter] = None,
        settlement_adapter: Optional[ISettlementAdapter] = None,
        db: Optional[Session] = None,
    ):
        if isinstance(db_or_adapter, Session):
            db = db_or_adapter
        elif db_or_adapter is not None and hasattr(db_or_adapter, "get_merchant_metrics"):
            revive_adapter = db_or_adapter

        self.db = db
        self.revive_adapter = revive_adapter or (MockReviveAdapter(db) if db else None)
        self.device_adapter = device_adapter or (MockDeviceAdapter(db) if db else None)
        self.settlement_adapter = settlement_adapter or (MockSettlementAdapter(db) if db else None)

    # TOOL 1: get_merchant_metrics (R0 Read-Only)
    def get_merchant_metrics(
        self,
        merchant_id: str,
        execution_id: str = "exec_revive_metrics",
        actor_id: str = "agent_revive",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="GET_MERCHANT_METRICS",
            target_id=merchant_id,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_revive",
            parameters={"merchant_id": merchant_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"found": False, "error": "Policy denied metrics lookup"}

        rec = self.revive_adapter.get_merchant_metrics(merchant_id)
        if not rec:
            return {"found": False, "merchant_id": merchant_id}

        return {
            "found": True,
            "merchant_id": rec.merchant_id,
            "store_name": rec.store_name,
            "city": rec.city,
            "baseline_daily_tx_count": rec.baseline_daily_tx_count,
            "baseline_daily_volume_paise": rec.baseline_daily_volume_paise,
            "baseline_daily_volume_inr": rec.baseline_daily_volume_inr,
            "recent_daily_tx_count": rec.recent_daily_tx_count,
            "recent_daily_volume_paise": rec.recent_daily_volume_paise,
            "recent_daily_volume_inr": rec.recent_daily_volume_inr,
            "drop_percentage": rec.drop_percentage,
            "health_status": rec.health_status,
            "diagnosed_cause": rec.diagnosed_cause,
            "revival_stage": rec.revival_stage,
            "last_scanned_at": rec.last_scanned_at,
            "recovered_at": rec.recovered_at,
        }

    # TOOL 2: get_recent_support_cases (R0 Read-Only)
    def get_recent_support_cases(
        self,
        merchant_id: str,
        execution_id: str = "exec_revive_cases",
        actor_id: str = "agent_revive",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="GET_RECENT_SUPPORT_CASES",
            target_id=merchant_id,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_revive",
            parameters={"merchant_id": merchant_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.db:
            return {"cases": []}

        tasks = (
            self.db.query(Task)
            .filter_by(merchant_id=merchant_id)
            .order_by(Task.created_at.desc())
            .limit(5)
            .all()
        )
        cases_list = [
            {
                "id": t.id,
                "title": t.title,
                "bucket": t.bucket.value if hasattr(t.bucket, "value") else str(t.bucket),
                "priority": t.priority,
                "assigned_to": t.assigned_to,
            }
            for t in tasks
        ]
        return {"merchant_id": merchant_id, "cases": cases_list, "open_count": len(cases_list)}

    # TOOL 3: get_device_status (R0 Read-Only, reused from DeviceAdapter)
    def get_device_status(
        self,
        merchant_id: str,
        execution_id: str = "exec_revive_device",
        actor_id: str = "agent_revive",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="GET_DEVICE_STATUS",
            target_id=merchant_id,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_revive",
            parameters={"merchant_id": merchant_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.device_adapter:
            return {"found": False}

        device = self.device_adapter.get_device_by_merchant(merchant_id)
        if not device:
            return {"found": False, "merchant_id": merchant_id}

        is_degraded = (device.status != "ONLINE") or (device.battery_level < 15)
        return {
            "found": True,
            "device_id": device.id,
            "serial_number": device.serial_number,
            "status": device.status,
            "battery_level": device.battery_level,
            "is_degraded": is_degraded,
            "signal_strength_dbm": device.signal_strength_dbm,
            "technician_visit_booked": device.technician_visit_booked,
        }

    # TOOL 4: get_settlement_status (R0 Read-Only, reused from SettlementAdapter)
    def get_settlement_status(
        self,
        merchant_id: str,
        execution_id: str = "exec_revive_settlement",
        actor_id: str = "agent_revive",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="GET_SETTLEMENT_STATUS",
            target_id=merchant_id,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_revive",
            parameters={"merchant_id": merchant_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.settlement_adapter:
            return {"has_discrepancy": False}

        settlements = self.settlement_adapter.list_settlements(merchant_id, limit=5)
        discrepancy_settlement = next((s for s in settlements if s.status == "DISCREPANCY"), None)

        if discrepancy_settlement:
            return {
                "has_discrepancy": True,
                "settlement_date": discrepancy_settlement.settlement_date,
                "discrepancy_paise": discrepancy_settlement.discrepancy,
                "discrepancy_inr": f"₹{abs(discrepancy_settlement.discrepancy) / 100:,.2f}",
                "status": discrepancy_settlement.status,
                "bank_utr": discrepancy_settlement.bank_utr,
                "evidence_attached": discrepancy_settlement.evidence_attached,
            }

        return {"has_discrepancy": False}

    # TOOL 5: create_merchant_followup (R1 Internal Follow-up Notification)
    def create_merchant_followup(
        self,
        merchant_id: str,
        cause_type: str,
        message_title: str,
        message_body: str,
        offer_code: Optional[str] = None,
        offer_details: Optional[str] = None,
        handed_off_to: Optional[str] = None,
        execution_id: str = "exec_fol_create",
        actor_id: str = "agent_revive",
    ) -> Dict[str, Any]:
        # Disallowed action constraint: unapproved discounts or commercial fee waivers
        APPROVED_OFFER_CODES = {"KIRANA_BOOSTER_0MDR", "BOOSTER30", "REBATE100", "STAND_REFRESH", None}
        is_unapproved_offer = offer_code is not None and offer_code not in APPROVED_OFFER_CODES

        proposal = ActionProposal(
            action_type="CREATE_MERCHANT_FOLLOWUP",
            target_id=f"{merchant_id}:{cause_type}",
            risk_tier=RiskTier.R4 if is_unapproved_offer else RiskTier.R1,
            actor_id=actor_id,
            actor_role="agent_revive",
            parameters={
                "merchant_id": merchant_id,
                "cause_type": cause_type,
                "offer_code": offer_code,
                "handed_off_to": handed_off_to,
            },
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {
                "success": False,
                "error": f"Policy denied followup: {decision.reason_codes}",
                "message": "Policy violation: offering unapproved discounts or fee waivers is strictly disallowed.",
            }

        idempotency_key = generate_idempotency_key(
            execution_id=execution_id,
            action_type="CREATE_MERCHANT_FOLLOWUP",
            target_id=merchant_id,
            params={"cause_type": cause_type, "offer_code": offer_code},
        )

        rec = self.revive_adapter.create_followup(
            merchant_id=merchant_id,
            cause_type=cause_type,
            message_title=message_title,
            message_body=message_body,
            offer_code=offer_code,
            offer_details=offer_details,
            handed_off_to=handed_off_to,
        )

        if self.db:
            audit_log(
                db=self.db,
                actor=actor_id,
                action="CREATE_MERCHANT_FOLLOWUP",
                target=rec.id,
                result="CONFIRMED",
                policy_decision_id=decision.decision_id,
                idempotency_key=idempotency_key,
            )

        return {
            "success": True,
            "followup_id": rec.id,
            "merchant_id": rec.merchant_id,
            "cause_type": rec.cause_type,
            "title": rec.message_title,
            "status": rec.status,
            "offer_code": rec.offer_code,
            "handed_off_to": rec.handed_off_to,
            "message": f"Follow-up delivered to merchant app ({rec.id})",
        }

    # TOOL 6: create_retention_review (R1 Warm Lead Creation for Sales Rep)
    def create_retention_review(
        self,
        merchant_id: str,
        followup_id: str,
        notes: str,
        execution_id: str = "exec_warm_lead",
        actor_id: str = "agent_revive",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="CREATE_RETENTION_REVIEW",
            target_id=f"{merchant_id}:{followup_id}",
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="agent_revive",
            parameters={"merchant_id": merchant_id, "followup_id": followup_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"success": False, "error": f"Policy denied retention review: {decision.reason_codes}"}

        idempotency_key = generate_idempotency_key(
            execution_id=execution_id,
            action_type="CREATE_RETENTION_REVIEW",
            target_id=merchant_id,
            params={"followup_id": followup_id},
        )

        # Check existing warm-lead task
        existing_task = None
        if self.db:
            existing_task = (
                self.db.query(Task)
                .filter(
                    (Task.merchant_id == merchant_id)
                    & (Task.title.like("%Warm Lead: Retention Visit%"))
                )
                .first()
            )

        if existing_task:
            return {
                "success": True,
                "is_duplicate_idempotent": True,
                "task_id": existing_task.id,
                "bucket": "needs_human",
                "message": "Warm-lead retention task already assigned to Field Sales Rep.",
            }

        merchant = self.db.query(Merchant).filter_by(id=merchant_id).first() if self.db else None
        store_name = merchant.store_name if merchant else "Kirana Store"
        tenant_id = merchant.tenant_id if merchant else "tenant_paytm_demo"

        task_id = f"task_lead_{idempotency_key[-8:]}"
        task = Task(
            id=task_id,
            tenant_id=tenant_id,
            merchant_id=merchant_id,
            title=f"Warm Lead: Retention Visit for {store_name}",
            description=notes,
            bucket=TaskBucket.NEEDS_HUMAN,
            priority="HIGH",
            assigned_to="Amit V. (Sales Rep)",
            is_synthetic=True,
            environment="DEMO",
        )
        if self.db:
            self.db.add(task)

            # Update followup task_id
            fol = self.db.query(MerchantFollowup).filter_by(id=followup_id).first()
            if fol:
                fol.task_id = task.id
                fol.handed_off_to = "FIELDMATE_SALES_REP"

            self.db.commit()

            audit_log(
                db=self.db,
                actor=actor_id,
                action="CREATE_RETENTION_REVIEW",
                target=task.id,
                result="CONFIRMED",
                policy_decision_id=decision.decision_id,
                idempotency_key=idempotency_key,
            )

        return {
            "success": True,
            "task_id": task_id,
            "bucket": "needs_human",
            "assigned_to": "Amit V. (Sales Rep)",
            "message": f"Warm lead task {task_id} successfully dispatched to Sales Rep with full Kirana context.",
        }

    # TOOL 7: verify_merchant_revival (R0 / R1 Invariant: Only revived after real recovery)
    def verify_merchant_revival(
        self,
        merchant_id: str,
        simulated_daily_volume_paise: int,
        simulated_daily_tx_count: int,
        actor_id: str = "agent_revive",
    ) -> Dict[str, Any]:
        rec = self.revive_adapter.record_merchant_recovery(
            merchant_id=merchant_id,
            new_daily_volume_paise=simulated_daily_volume_paise,
            new_daily_tx_count=simulated_daily_tx_count,
        )
        if not rec:
            return {"success": False, "is_revived": False}

        is_revived = (rec.revival_stage == "REVIVED")

        if self.db and is_revived:
            audit_log(
                db=self.db,
                actor=actor_id,
                action="VERIFY_MERCHANT_REVIVAL",
                target=merchant_id,
                result="CONFIRMED",
                policy_decision_id="dec_revival_confirmed",
            )

        return {
            "success": True,
            "merchant_id": merchant_id,
            "recent_volume_inr": rec.recent_daily_volume_inr,
            "drop_percentage": rec.drop_percentage,
            "health_status": rec.health_status,
            "revival_stage": rec.revival_stage,
            "is_revived": is_revived,
            "message": (
                f"Merchant {rec.store_name} verified as REVIVED! Fresh volume ({rec.recent_daily_volume_inr}) recovered above threshold."
                if is_revived
                else f"Merchant volume ({rec.recent_daily_volume_inr}) still below recovery threshold. Status remains {rec.revival_stage}."
            ),
        }
