import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.db.models import (
    Merchant,
    Device,
    MerchantActivityMetric,
    MerchantVisit,
    Task,
    TaskBucket,
    AuditEvent,
)
from app.adapters.device import MockDeviceAdapter
from app.tools.fix import FixTools
from app.tools.revive import ReviveTools
from app.tools.fieldmate import FieldMateTools
from app.policy.audit import audit_log
from app.policy.engine import PolicyEngine
from app.schemas.policy import ActionProposal, RiskTier
from app.schemas.orchestrator import HandoffStepResponse, HandoffChainStatusResponse


class HandoffDemoService:
    """
    Scripted Multi-Agent Cross-Handoff Demo.
    Reuses Phase 4-10 code directly without duplicating logic:
    - Step 1: Revive detects merchant volume drop (ReviveTools.get_merchant_metrics)
    - Step 2: Revive diagnoses Soundbox offline (reusing Fix's DeviceAdapter)
    - Step 3: Fix's remote-fix flow runs and fails (recheck confirms still offline)
    - Step 4: Fix books technician visit (FixTools.create_technician_task)
    - Step 5: FieldMate route generation adds visit to rep's list with combined brief
    - Step 6: Demo-triggered visit complete event -> Revive rechecks metrics & marks recovering
    """

    def __init__(self, db: Session):
        self.db = db
        self.device_adapter = MockDeviceAdapter(db)
        self.fix_tools = FixTools(self.device_adapter, db)
        self.revive_tools = ReviveTools(db)
        self.fieldmate_tools = FieldMateTools(db=db)

    def reset_demo(self, merchant_id: str = "mer_singh_automobiles") -> Dict[str, Any]:
        """Resets the merchant, device, metric, and visit states to pre-handoff baseline."""
        now = datetime.now(timezone.utc)
        merchant = self.db.query(Merchant).filter_by(id=merchant_id).first()
        tenant_id = merchant.tenant_id if merchant and merchant.tenant_id else "tenant_paytm_demo"

        # 1. Reset Device to OFFLINE
        device = (
            self.db.query(Device)
            .filter_by(merchant_id=merchant_id)
            .first()
        )
        if device:
            device.status = "OFFLINE"
            device.battery_level = 12
            device.reboot_in_progress = False
            device.technician_visit_booked = False
            device.last_heartbeat = now - timedelta(days=3)

        # 2. Reset Activity Metric to AT_RISK with 86% drop
        metric = (
            self.db.query(MerchantActivityMetric)
            .filter_by(merchant_id=merchant_id)
            .first()
        )
        if not metric:
            metric = MerchantActivityMetric(
                id=f"metric_{merchant_id}_handoff",
                tenant_id=tenant_id,
                merchant_id=merchant_id,
                baseline_daily_tx_count=45,
                baseline_daily_volume_paise=1800000,
                recent_daily_tx_count=6,
                recent_daily_volume_paise=240000,
                drop_percentage=86,
                health_status="AT_RISK",
                diagnosed_cause="DEVICE_ISSUE",
                revival_stage="AT_RISK",
                last_scanned_at=now,
                is_synthetic=True,
                environment="DEMO",
            )
            self.db.add(metric)
        else:
            metric.drop_percentage = 86
            metric.recent_daily_tx_count = 6
            metric.recent_daily_volume_paise = 240000
            metric.health_status = "AT_RISK"
            metric.diagnosed_cause = "DEVICE_ISSUE"
            metric.revival_stage = "AT_RISK"
            metric.last_scanned_at = now

        # 3. Reset MerchantVisit to SCHEDULED and unconfirmed
        visit = (
            self.db.query(MerchantVisit)
            .filter_by(merchant_id=merchant_id)
            .first()
        )
        if visit:
            visit.visit_status = "SCHEDULED"
            visit.is_confirmed_by_rep = False
            visit.confirmed_notes = None
            visit.evidence_backed_brief = "Soundbox offline 3 days & bank proof missing — replace battery/adapter, collect physical cheque"
        elif merchant:
            visit = MerchantVisit(
                id=f"visit_{merchant_id}_handoff",
                tenant_id=tenant_id,
                merchant_id=merchant_id,
                sales_rep_id=merchant.assigned_sales_rep_id or "emp_sales_01",
                visit_status="SCHEDULED",
                planned_order=1,
                priority="HIGH",
                distance_km=3.3,
                evidence_backed_brief="Soundbox offline 3 days & bank proof missing — replace battery/adapter, collect physical cheque",
                brief_cause_type="HARDWARE_AND_KYC",
                is_confirmed_by_rep=False,
                version=1,
                is_synthetic=True,
                environment="DEMO",
            )
            self.db.add(visit)

        self.db.commit()

        audit_log(
            db=self.db,
            actor="demo_narrator",
            action="HANDOFF_DEMO_RESET",
            target=merchant_id,
            result="RESET_TO_BASELINE",
            policy_decision_id="dec_handoff_reset",
        )

        return {"status": "SUCCESS", "merchant_id": merchant_id, "message": "Demo state reset to baseline."}

    def get_status(self, merchant_id: str = "mer_singh_automobiles") -> HandoffChainStatusResponse:
        """Returns the current state of merchant, device, visit, and metrics."""
        device = self.db.query(Device).filter_by(merchant_id=merchant_id).first()
        metric = self.db.query(MerchantActivityMetric).filter_by(merchant_id=merchant_id).first()
        visit = self.db.query(MerchantVisit).filter_by(merchant_id=merchant_id).first()

        device_status = device.status if device else "UNKNOWN"
        merchant_health = metric.health_status if metric else "UNKNOWN"
        revival_stage = metric.revival_stage if metric else "UNKNOWN"
        visit_status = visit.visit_status if visit else "NOT_SCHEDULED"

        # Determine current step based on authoritative DB signals
        if visit and visit.visit_status == "COMPLETED" and revival_stage == "RECOVERING":
            current_step = 6
        elif visit and "Volume dropped 86%" in (visit.evidence_backed_brief or ""):
            current_step = 5
        elif device and device.technician_visit_booked:
            current_step = 4
        elif metric and metric.diagnosed_cause == "DEVICE_ISSUE" and device and device.status == "OFFLINE":
            current_step = 2
        elif metric and metric.health_status == "AT_RISK":
            current_step = 1
        else:
            current_step = 0

        return HandoffChainStatusResponse(
            merchant_id=merchant_id,
            current_step=current_step,
            is_running=False,
            merchant_health=merchant_health,
            device_status=device_status,
            visit_status=visit_status,
            revival_stage=revival_stage,
        )

    def execute_step(
        self,
        step: int,
        merchant_id: str = "mer_singh_automobiles",
        actor_id: str = "demo_narrator",
    ) -> HandoffStepResponse:
        """
        Executes a single step in the cross-agent chain and commits an authoritative audit event.
        """
        execution_id = f"exec_handoff_{uuid.uuid4().hex[:8]}"

        # -------------------------------------------------------------
        # STEP 1: Revive detects volume dropped
        # -------------------------------------------------------------
        if step == 1:
            metrics = self.revive_tools.get_merchant_metrics(merchant_id, execution_id=execution_id, actor_id="agent_revive")
            drop_pct = metrics.get("drop_percentage", 86)
            store_name = metrics.get("store_name", "Singh Automobiles")

            ev = audit_log(
                db=self.db,
                actor="agent_revive",
                action="Saathi routed to: REVIVE",
                target=f"Dormancy scan: {store_name} volume dropped {drop_pct}%",
                result="AT_RISK_DETECTED",
                policy_decision_id="dec_revive_scan_p11",
                idempotency_key=f"handoff_s1_{merchant_id}",
            )

            return HandoffStepResponse(
                step=1,
                step_name="Revive Detects Dormancy Drop",
                active_agent="REVIVE",
                summary=f"Revive Agent completed periodic scan. Detected genuine {drop_pct}% volume drop for {store_name} (Status: AT_RISK).",
                details={
                    "merchant_id": merchant_id,
                    "store_name": store_name,
                    "drop_percentage": drop_pct,
                    "health_status": "AT_RISK",
                    "baseline_volume_paise": metrics.get("baseline_daily_volume_paise"),
                    "recent_volume_paise": metrics.get("recent_daily_volume_paise"),
                },
                next_step=2,
                audit_event_id=ev.id,
            )

        # -------------------------------------------------------------
        # STEP 2: Diagnosis finds Soundbox offline (reusing Fix's DeviceAdapter)
        # -------------------------------------------------------------
        elif step == 2:
            dev_status = self.revive_tools.get_device_status(merchant_id, execution_id=execution_id, actor_id="agent_revive")
            serial = dev_status.get("serial_number", "SB-JAI-505")
            status_desc = dev_status.get("status", "OFFLINE")
            battery = dev_status.get("battery_level", 12)

            # Update metric diagnosed cause
            metric = self.db.query(MerchantActivityMetric).filter_by(merchant_id=merchant_id).first()
            if metric:
                metric.diagnosed_cause = "DEVICE_ISSUE"
                self.db.commit()

            ev = audit_log(
                db=self.db,
                actor="agent_revive",
                action="REVIVE_CAUSE_DIAGNOSED",
                target=f"Device telemetry: {serial} is {status_desc} (battery: {battery}%)",
                result="HANDOFF_TO_FIX",
                policy_decision_id="dec_revive_diag_p11",
                idempotency_key=f"handoff_s2_{merchant_id}",
            )

            return HandoffStepResponse(
                step=2,
                step_name="Diagnosis Finds Soundbox Offline",
                active_agent="REVIVE",
                summary=f"Revive diagnosed root cause using Fix's DeviceAdapter: Soundbox {serial} is {status_desc} (Battery: {battery}%). Handing off to Fix Agent.",
                details={
                    "merchant_id": merchant_id,
                    "diagnosed_cause": "DEVICE_ISSUE",
                    "device_serial": serial,
                    "device_status": status_desc,
                    "battery_level": battery,
                    "target_agent": "FIX",
                },
                next_step=3,
                audit_event_id=ev.id,
            )

        # -------------------------------------------------------------
        # STEP 3: Fix's remote-fix flow runs and fails
        # -------------------------------------------------------------
        elif step == 3:
            device = self.db.query(Device).filter_by(merchant_id=merchant_id).first()
            serial = device.serial_number if device else "SB-JAI-505"

            # 1. Dispatch Over-the-air reboot signal (R1 internal action)
            rst_res = self.fix_tools.request_remote_restart(serial, execution_id=execution_id, actor_id="agent_fix")

            # 2. Authoritative fresh check (never assume success)
            fresh_status = self.fix_tools.get_device_status(serial, execution_id=execution_id, actor_id="agent_fix")
            is_online = fresh_status.get("is_online", False)

            ev = audit_log(
                db=self.db,
                actor="agent_fix",
                action="Saathi routed to: FIX",
                target=f"Remote reboot cmd {rst_res.get('command_id')} for {serial}",
                result="REBOOT_FAILED_STILL_OFFLINE",
                policy_decision_id="dec_fix_reboot_p11",
                idempotency_key=f"handoff_s3_{merchant_id}",
            )

            return HandoffStepResponse(
                step=3,
                step_name="Fix Agent Remote Troubleshooting Fails",
                active_agent="FIX",
                summary=f"Fix Agent dispatched remote reboot command ({rst_res.get('command_id')}). Fresh telemetry check verified Soundbox {serial} remains OFFLINE (battery 12%).",
                details={
                    "merchant_id": merchant_id,
                    "device_serial": serial,
                    "remote_command_id": rst_res.get("command_id"),
                    "fresh_online_check": is_online,
                    "conclusion": "Hardware requires physical on-site intervention.",
                },
                next_step=4,
                audit_event_id=ev.id,
            )

        # -------------------------------------------------------------
        # STEP 4: Technician visit is booked
        # -------------------------------------------------------------
        elif step == 4:
            device = self.db.query(Device).filter_by(merchant_id=merchant_id).first()
            serial = device.serial_number if device else "SB-JAI-505"
            slot_str = "Tomorrow 10:00 AM - 12:00 PM"

            tech_res = self.fix_tools.create_technician_task(
                merchant_id=merchant_id,
                device_ref=serial,
                slot_str=slot_str,
                issue_description=f"Soundbox {serial} offline. Unreachable after remote reboot attempt. Hardware/battery replacement needed.",
                execution_id=execution_id,
                actor_id="agent_fix",
            )

            ev = audit_log(
                db=self.db,
                actor="agent_fix",
                action="TECHNICIAN_VISIT_BOOKED",
                target=f"Field task {tech_res.get('task_id')} for {serial}",
                result="SLOT_CONFIRMED",
                policy_decision_id="dec_fix_tech_p11",
                idempotency_key=f"handoff_s4_{merchant_id}",
            )

            return HandoffStepResponse(
                step=4,
                step_name="Fix Agent Books Technician Visit",
                active_agent="FIX",
                summary=f"Fix Agent booked authorized technician visit for {slot_str} (Task ID: {tech_res.get('task_id')}). Handoff queued to FieldMate Sales Beat.",
                details={
                    "merchant_id": merchant_id,
                    "task_id": tech_res.get("task_id"),
                    "slot_time": slot_str,
                    "device_serial": serial,
                    "target_agent": "FIELDMATE",
                },
                next_step=5,
                audit_event_id=ev.id,
            )

        # -------------------------------------------------------------
        # STEP 5: FieldMate adds visit to nearest rep's list with combined brief
        # -------------------------------------------------------------
        elif step == 5:
            sales_rep_id = "emp_sales_01"  # Amit Verma
            visit = (
                self.db.query(MerchantVisit)
                .filter_by(merchant_id=merchant_id)
                .first()
            )
            combined_brief = (
                "Soundbox offline (12% battery) & hardware check required — replace adapter/battery; "
                "Sales dropped 86% — pitch Kirana Booster & Merchant Loan"
            )

            if not visit:
                m_obj = self.db.query(Merchant).filter_by(id=merchant_id).first()
                t_id = m_obj.tenant_id if m_obj and m_obj.tenant_id else "tenant_paytm_demo"
                visit = MerchantVisit(
                    id=f"visit_{merchant_id}_handoff",
                    tenant_id=t_id,
                    merchant_id=merchant_id,
                    sales_rep_id=sales_rep_id,
                    visit_status="SCHEDULED",
                    planned_order=1,
                    priority="HIGH",
                    distance_km=3.3,
                    evidence_backed_brief=combined_brief,
                    brief_cause_type="HARDWARE_AND_DORMANCY",
                    is_confirmed_by_rep=False,
                    version=1,
                    is_synthetic=True,
                    environment="DEMO",
                )
                self.db.add(visit)
            else:
                visit.evidence_backed_brief = combined_brief
                visit.priority = "HIGH"
                visit.visit_status = "SCHEDULED"

            self.db.commit()

            ev = audit_log(
                db=self.db,
                actor="agent_fieldmate",
                action="Saathi routed to: FIELDMATE",
                target=f"Route updated for {sales_rep_id}: {merchant_id}",
                result="COMBINED_BRIEF_GENERATED",
                policy_decision_id="dec_fm_route_p11",
                idempotency_key=f"handoff_s5_{merchant_id}",
            )

            return HandoffStepResponse(
                step=5,
                step_name="FieldMate Combines Hardware & Loan Brief",
                active_agent="FIELDMATE",
                summary=f"FieldMate generated prioritized stop for rep {sales_rep_id} (Amit Verma). Evidence-backed brief combines hardware fix with Kirana Booster loan pitch.",
                details={
                    "merchant_id": merchant_id,
                    "sales_rep_id": sales_rep_id,
                    "rep_name": "Amit Verma",
                    "priority": "HIGH",
                    "distance_km": 3.3,
                    "brief": combined_brief,
                },
                next_step=6,
                audit_event_id=ev.id,
            )

        # -------------------------------------------------------------
        # STEP 6: Visit Complete Event -> Revive rechecks metrics & marks recovering
        # -------------------------------------------------------------
        elif step == 6:
            now = datetime.now(timezone.utc)

            # 1. Physical visit completion (Simulated Rep Visit Confirmation)
            device = self.db.query(Device).filter_by(merchant_id=merchant_id).first()
            if device:
                device.status = "ONLINE"
                device.battery_level = 95
                device.last_heartbeat = now
                device.technician_visit_booked = False

            visit = self.db.query(MerchantVisit).filter_by(merchant_id=merchant_id).first()
            if visit:
                visit.visit_status = "COMPLETED"
                visit.is_confirmed_by_rep = True
                visit.confirmed_notes = (
                    "Visited shop on beat. Replaced power adapter. Soundbox online and voice chime verified. "
                    "Pitched ₹50,000 Merchant Loan to Rajesh ji — merchant expressed interest."
                )

            # 2. Activity metrics recover
            metric = self.db.query(MerchantActivityMetric).filter_by(merchant_id=merchant_id).first()
            if metric:
                metric.recent_daily_volume_paise = 1750000  # ₹17,500 (recovered)
                metric.recent_daily_tx_count = 42
                metric.drop_percentage = 3
                metric.health_status = "HEALTHY"
                metric.revival_stage = "RECOVERING"
                metric.last_scanned_at = now

            self.db.commit()

            # 3. Revive Agent performs authoritative recheck
            rechecked = self.revive_tools.get_merchant_metrics(merchant_id, execution_id=execution_id, actor_id="agent_revive")

            ev = audit_log(
                db=self.db,
                actor="agent_revive",
                action="REVIVE_METRIC_RECHECKED",
                target=f"Authoritative telemetry: volume recovered to ₹17,500/day",
                result="RECOVERING_CONFIRMED",
                policy_decision_id="dec_revive_recovery_p11",
                idempotency_key=f"handoff_s6_{merchant_id}",
            )

            return HandoffStepResponse(
                step=6,
                step_name="Revive Verifies Recovery After Visit",
                active_agent="REVIVE",
                summary=f"Sales rep confirmed visit note. Soundbox is ONLINE (95% battery). Revive re-checked authoritative metrics: volume recovered (drop reduced from 86% to 3%). Status: RECOVERING.",
                details={
                    "merchant_id": merchant_id,
                    "device_status": "ONLINE",
                    "battery_level": 95,
                    "recovered_volume_paise": rechecked.get("recent_daily_volume_paise"),
                    "drop_percentage": rechecked.get("drop_percentage"),
                    "health_status": "HEALTHY",
                    "revival_stage": "RECOVERING",
                    "cross_agent_chain": "Revive -> Fix -> FieldMate -> Revive",
                },
                next_step=None,
                is_complete=True,
                audit_event_id=ev.id,
            )

        raise ValueError(f"Invalid handoff step: {step}. Must be between 1 and 6.")

    def run_all(
        self,
        merchant_id: str = "mer_singh_automobiles",
        actor_id: str = "demo_narrator",
        pause_between_steps: float = 0.2,
    ) -> List[HandoffStepResponse]:
        """Runs the entire 6-step cross-agent chain sequentially."""
        results = []
        for step_idx in range(1, 7):
            res = self.execute_step(step=step_idx, merchant_id=merchant_id, actor_id=actor_id)
            results.append(res)
            if pause_between_steps > 0 and step_idx < 6:
                time.sleep(pause_between_steps)
        return results
