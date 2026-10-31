import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.adapters.device import IDeviceAdapter
from app.policy.engine import PolicyEngine
from app.policy.audit import audit_log
from app.schemas.policy import ActionProposal, RiskTier
from app.db.models import Task, TaskBucket, Device

def generate_idempotency_key(execution_id: str, action_type: str, target_id: str, params: Dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True)
    raw = f"{execution_id}:{action_type}:{target_id}:{canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

class FixTools:
    """
    Risk-tiered constrained toolset for the Fix Specialist Agent (Soundbox Voice & Device Support).
    Every side-effecting action is policy-checked, verified against authoritative telemetry, and audited.
    """

    def __init__(self, adapter: IDeviceAdapter, db: Session):
        self.adapter = adapter
        self.db = db

    # TOOL 1: get_device_status (R0 Read-Only)
    def get_device_status(self, device_ref: str, execution_id: str, actor_id: str) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="GET_DEVICE_STATUS",
            target_id=device_ref,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_fix",
            parameters={"device_ref": device_ref},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"found": False, "error": "Policy denied action", "decision": decision.model_dump()}

        dev = self.adapter.get_device_by_serial(device_ref)
        if not dev:
            dev = self.adapter.get_device_by_id(device_ref)
        if not dev:
            dev = self.adapter.get_device_by_merchant(device_ref)

        if not dev:
            return {"found": False, "message": f"No Soundbox device record found matching '{device_ref}'."}

        return {
            "found": True,
            "id": dev.id,
            "merchant_id": dev.merchant_id,
            "device_type": dev.device_type,
            "serial_number": dev.serial_number,
            "battery_level": dev.battery_level,
            "status": dev.status,
            "is_online": dev.status.upper() == "ONLINE",
            "last_heartbeat": dev.last_heartbeat.isoformat() if dev.last_heartbeat else None,
            "signal_strength_dbm": dev.signal_strength_dbm,
            "firmware_version": dev.firmware_version,
            "technician_visit_booked": dev.technician_visit_booked,
            "technician_slot": dev.technician_slot,
        }

    # TOOL 2: get_device_diagnostics (R0 Read-Only)
    def get_device_diagnostics(self, device_ref: str, execution_id: str, actor_id: str) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="GET_DEVICE_DIAGNOSTICS",
            target_id=device_ref,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_fix",
            parameters={"device_ref": device_ref},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"error": "Policy denied diagnostics action"}

        diag = self.adapter.get_device_diagnostics(device_ref)
        if not diag:
            # Fallback to serial lookup via merchant
            dev = self.adapter.get_device_by_merchant(device_ref)
            if dev:
                diag = self.adapter.get_device_diagnostics(dev.serial_number)

        if not diag:
            return {"found": False, "message": f"No telemetry available for '{device_ref}'."}

        return {
            "found": True,
            "device_id": diag.device_id,
            "serial_number": diag.serial_number,
            "status": diag.status,
            "battery_level": diag.battery_level,
            "battery_healthy": diag.battery_healthy,
            "signal_strength_dbm": diag.signal_strength_dbm,
            "signal_quality": diag.signal_quality,
            "firmware_version": diag.firmware_version,
            "firmware_up_to_date": diag.firmware_up_to_date,
            "last_heartbeat_ago_seconds": diag.last_heartbeat_ago_seconds,
            "last_heartbeat_str": diag.last_heartbeat_str,
            "is_online": diag.is_online,
            "speaker_status": diag.speaker_status,
            "sim_status": diag.sim_status,
        }

    # TOOL 3: request_remote_restart (R1 Simulated/Reversible)
    def request_remote_restart(self, device_ref: str, execution_id: str, actor_id: str) -> Dict[str, Any]:
        params = {"device_ref": device_ref, "command": "OTA_REBOOT"}
        idempotency_key = generate_idempotency_key(execution_id, "REQUEST_REMOTE_RESTART", device_ref, params)

        proposal = ActionProposal(
            action_type="REQUEST_REMOTE_RESTART",
            target_id=device_ref,
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="agent_fix",
            parameters=params,
            rationale="Attempt OTA reboot packet to restore Soundbox cellular registration",
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"success": False, "error": "Policy engine blocked remote restart", "decision": decision.model_dump()}

        result = self.adapter.request_remote_restart(device_ref)

        # Audit event
        audit_log(
            db=self.db,
            actor=actor_id,
            action="REQUEST_REMOTE_RESTART",
            target=result.serial_number or device_ref,
            result=result.status,
            policy_decision_id=decision.decision_id,
            idempotency_key=idempotency_key,
        )

        return {
            "success": result.success,
            "command_id": result.command_id,
            "serial_number": result.serial_number,
            "status": result.status,
            "message": result.message,
            "idempotency_key": idempotency_key,
        }

    # TOOL 4: get_technician_slots (R0 Read-Only)
    def get_technician_slots(self, city: str, execution_id: str, actor_id: str) -> List[Dict[str, Any]]:
        proposal = ActionProposal(
            action_type="GET_TECHNICIAN_SLOTS",
            target_id=city,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="agent_fix",
            parameters={"city": city},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return []

        slots = self.adapter.get_technician_slots(city)
        return [slot.model_dump() for slot in slots]

    # TOOL 5: create_technician_task (R1 Internal / Field Dispatch)
    def create_technician_task(
        self,
        merchant_id: str,
        device_ref: str,
        slot_str: str,
        issue_description: str,
        execution_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        dev = self.adapter.get_device_by_serial(device_ref)
        if not dev:
            dev = self.adapter.get_device_by_id(device_ref)
        if not dev:
            dev = self.adapter.get_device_by_merchant(merchant_id)

        device_id = dev.id if dev else None
        serial_str = dev.serial_number if dev else device_ref

        params = {"merchant_id": merchant_id, "device_ref": serial_str, "slot": slot_str}
        idempotency_key = generate_idempotency_key(execution_id, "CREATE_TECHNICIAN_TASK", serial_str, params)

        # Idempotency check: don't double book if visit is already booked for this device
        existing_task = (
            self.db.query(Task)
            .filter(
                (Task.merchant_id == merchant_id)
                & (Task.title.like(f"%Technician Visit%{serial_str}%"))
            )
            .first()
        )

        if existing_task:
            return {
                "success": True,
                "is_duplicate_idempotent": True,
                "task_id": existing_task.id,
                "bucket": existing_task.bucket.value if hasattr(existing_task.bucket, "value") else str(existing_task.bucket),
                "slot": slot_str,
                "serial_number": serial_str,
                "message": f"Technician visit is already booked for Soundbox {serial_str} (Case {existing_task.id}).",
                "idempotency_key": idempotency_key,
            }

        proposal = ActionProposal(
            action_type="CREATE_TECHNICIAN_TASK",
            target_id=serial_str,
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="agent_fix",
            parameters=params,
            rationale=issue_description,
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"success": False, "error": "Policy engine denied technician dispatch", "decision": decision.model_dump()}

        # Create Task in needs_human bucket
        task = Task(
            id=f"case_tech_{hashlib.md5(idempotency_key.encode()).hexdigest()[:8]}",
            tenant_id=merchant_id,
            merchant_id=merchant_id,
            device_id=device_id,
            title=f"Technician Visit: Soundbox {serial_str} ({slot_str})",
            description=(
                f"Soundbox {serial_str} offline. Remote reboot attempted and failed re-check. "
                f"Technician visit assigned for {slot_str}. Issue: {issue_description}"
            ),
            bucket=TaskBucket.NEEDS_HUMAN,
            priority="HIGH",
            assigned_to="Paytm Field Service Team (FSE)",
            is_synthetic=True,
            environment="DEMO",
        )
        self.db.add(task)

        # Update device booking flag
        if device_id:
            self.adapter.update_technician_booking(device_id, slot_str)

        self.db.commit()

        # Audit event
        audit_log(
            db=self.db,
            actor=actor_id,
            action="CREATE_TECHNICIAN_TASK",
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
            "slot": slot_str,
            "serial_number": serial_str,
            "message": f"Technician visit successfully scheduled for {slot_str}.",
            "idempotency_key": idempotency_key,
        }
