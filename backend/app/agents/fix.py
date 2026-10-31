import re
import uuid
from typing import Any, Dict, List, Optional, TypedDict
from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, END
from app.adapters.device import MockDeviceAdapter
from app.adapters.speech import get_speech_adapter
from app.adapters.gemini import gemini_adapter
from app.tools.fix import FixTools
from app.core.clockwork import clockwork
from app.policy.audit import audit_log

class FixAgentState(TypedDict, total=False):
    merchant_id: str
    city: str
    query_text: str
    device_ref: Optional[str]
    execution_id: str
    actor_id: str
    step: str
    device_data: Optional[Dict[str, Any]]
    diagnostics: Optional[Dict[str, Any]]
    remote_restart_attempted: bool
    fresh_status: Optional[str]
    technician_booked: bool
    technician_slot: Optional[str]
    case_id: Optional[str]
    agent_reply: str
    speech_audio_base64: Optional[str]
    chip_status: str
    action_card: Optional[Dict[str, Any]]
    loop_count: int

class FixAgent:
    """
    Specialist Agent 2: Fix (Soundbox Voice & Hardware Support).
    Uses LangGraph for deterministic step-by-step guided troubleshooting,
    authoritative fresh status verification, and automated technician dispatch.
    """

    def __init__(self, db: Session):
        self.db = db
        self.adapter = MockDeviceAdapter(db)
        self.speech_adapter = get_speech_adapter()
        self.tools = FixTools(self.adapter, db)
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(FixAgentState)

        builder.add_node("identify_device", self._node_identify_device)
        builder.add_node("inspect_telemetry", self._node_inspect_telemetry)
        builder.add_node("execute_fix_workflow", self._node_execute_fix_workflow)

        builder.set_entry_point("identify_device")
        builder.add_edge("identify_device", "inspect_telemetry")
        builder.add_edge("inspect_telemetry", "execute_fix_workflow")
        builder.add_edge("execute_fix_workflow", END)

        return builder.compile()

    def _node_identify_device(self, state: FixAgentState) -> Dict[str, Any]:
        query = (state.get("query_text") or "").strip()
        device_ref = state.get("device_ref")
        merchant_id = state.get("merchant_id", "mer_sharma_kirana")

        if not device_ref:
            # Check for patterns like SB-JAI-101 or dev_soundbox_101
            match = re.search(r"(SB-[A-Za-z0-9-]+|dev_[a-zA-Z0-9_]+)", query)
            if match:
                device_ref = match.group(0).upper().strip()
            elif "202" in query or "kanpur" in query.lower() or "verma" in query.lower():
                device_ref = "SB-KNP-202"
            elif "303" in query or "lucknow" in query.lower() or "laxmi" in query.lower():
                device_ref = "SB-LKO-303"
            elif "404" in query or "delhi" in query.lower() or "gupta" in query.lower():
                device_ref = "SB-DEL-404"
            elif "101" in query or "jaipur" in query.lower() or "sharma" in query.lower():
                device_ref = "SB-JAI-101"
            else:
                # Default to merchant's primary device
                dev = self.adapter.get_device_by_merchant(merchant_id)
                if dev:
                    device_ref = dev.serial_number

        return {"device_ref": device_ref}

    def _node_inspect_telemetry(self, state: FixAgentState) -> Dict[str, Any]:
        device_ref = state.get("device_ref")
        execution_id = state.get("execution_id", f"exec_fix_{uuid.uuid4().hex[:8]}")
        actor_id = state.get("actor_id", "merchant_user")

        if not device_ref:
            return {
                "step": "UNKNOWN_DEVICE",
                "chip_status": "pending",
                "agent_reply": "I could not identify your Soundbox serial number. Please tell me your Soundbox ID (e.g., SB-JAI-101 printed behind the device).",
            }

        status_data = self.tools.get_device_status(device_ref, execution_id, actor_id)
        diagnostics = self.tools.get_device_diagnostics(device_ref, execution_id, actor_id)

        return {
            "device_data": status_data,
            "diagnostics": diagnostics,
        }

    def _node_execute_fix_workflow(self, state: FixAgentState) -> Dict[str, Any]:
        query = (state.get("query_text") or "").lower()
        device_data = state.get("device_data") or {}
        diagnostics = state.get("diagnostics") or {}
        execution_id = state.get("execution_id", f"exec_fix_{uuid.uuid4().hex[:8]}")
        actor_id = state.get("actor_id", "merchant_user")
        merchant_id = state.get("merchant_id", "mer_sharma_kirana")
        city = state.get("city", "Jaipur")
        serial = device_data.get("serial_number", state.get("device_ref", "Soundbox"))
        battery = device_data.get("battery_level", 100)
        is_online = device_data.get("is_online", False)

        # SCENARIO 1: Critical Low Battery (<20%)
        if battery < 20 and ("battery" in query or "charge" in query or not is_online):
            reply = (
                f"Soundbox {serial} battery is critically low at {battery}%. "
                f"Voice step: Please connect the original orange Paytm charger. "
                f"Check if the small LED next to the charging port is glowing solid red. "
                f"Allow it to charge for 15 minutes before powering on."
            )
            return {
                "step": "LOW_BATTERY_CHARGING",
                "chip_status": "awaiting_approval",
                "agent_reply": reply,
                "action_card": {
                    "type": "DEVICE_BATTERY_ALERT",
                    "serial_number": serial,
                    "battery_level": battery,
                    "action": "Connect Charger",
                    "status": "awaiting_approval",
                },
            }

        # SCENARIO 2: Remote Restart Requested OR Merchant indicates remote recovery
        # (e.g. "restart", "reboot", "not working", "silent", "red light", "technician", "still red", "failed")
        wants_restart_or_troubleshoot = any(
            w in query
            for w in [
                "restart",
                "reboot",
                "fix",
                "still red",
                "silent",
                "not working",
                "technician",
                "failed",
                "offline",
                "chime not heard",
                "light red",
            ]
        )

        if wants_restart_or_troubleshoot or not is_online:
            # 1. Dispatch Over-the-air reboot signal (R1)
            rst_res = self.tools.request_remote_restart(serial, execution_id, actor_id)

            # 2. Schedule crash-safe Clockwork background recheck
            clockwork.schedule_device_recheck(
                db=self.db,
                merchant_id=merchant_id,
                device_ref=serial,
                delay_seconds=3,
                execution_id=execution_id,
            )

            # 3. Perform immediate authoritative fresh status check (NEVER ASSUME SUCCESS)
            fresh_check = self.tools.get_device_status(serial, execution_id, actor_id)
            fresh_online = fresh_check.get("is_online", False)

            # If device genuinely came online (e.g. demo toggle was flipped)
            if fresh_online:
                reply = (
                    f"Remote reboot packet dispatched (ID: {rst_res.get('command_id')}). "
                    f"Fresh telemetry check confirmed: Soundbox {serial} is now ONLINE and transmitting heartbeats! "
                    f"Battery is healthy ({fresh_check.get('battery_level')}%). Audio announcement channel is active."
                )
                return {
                    "step": "REMOTE_FIX_VERIFIED",
                    "chip_status": "verified",
                    "agent_reply": reply,
                    "remote_restart_attempted": True,
                    "fresh_status": "ONLINE",
                    "action_card": None,
                }

            # Device is STILL offline/degraded -> Book technician visit (R1)
            slots = self.tools.get_technician_slots(city, execution_id, actor_id)
            chosen_slot = slots[0]["slot_time"] if slots else "Tomorrow 10:00 AM - 12:00 PM"
            slot_date = slots[0]["date_str"] if slots else "Tomorrow"
            full_slot_str = f"{slot_date} {chosen_slot}"

            tech_res = self.tools.create_technician_task(
                merchant_id=merchant_id,
                device_ref=serial,
                slot_str=full_slot_str,
                issue_description=f"Soundbox {serial} offline. Cellular ping failed after remote reboot attempt.",
                execution_id=execution_id,
                actor_id=actor_id,
            )

            is_duplicate = tech_res.get("is_duplicate_idempotent", False)
            task_id = tech_res.get("task_id")

            if is_duplicate:
                reply = (
                    f"Soundbox {serial} remains unreachable after remote reboot. "
                    f"Notice: A Paytm technician visit is already confirmed for {full_slot_str} (Case ID: {task_id}). "
                    f"Our field service engineer will arrive with replacement SIM and hardware."
                )
            else:
                reply = (
                    f"Remote reboot attempted (Command ID: {rst_res.get('command_id')}), but Soundbox {serial} remains unreachable on Airtel 4G. "
                    f"As per Paytm SLA, I have booked an authorized Field Service Technician visit for {full_slot_str}. "
                    f"Case ID: {task_id}. The technician will test the SIM and hardware on-site at no charge."
                )

            return {
                "step": "TECHNICIAN_DISPATCHED",
                "chip_status": "needs_human",
                "agent_reply": reply,
                "remote_restart_attempted": True,
                "fresh_status": fresh_check.get("status", "OFFLINE"),
                "technician_booked": True,
                "technician_slot": full_slot_str,
                "case_id": task_id,
                "action_card": {
                    "type": "TECHNICIAN_VISIT_BOOKED",
                    "task_id": task_id,
                    "serial_number": serial,
                    "slot": full_slot_str,
                    "assigned_to": "Paytm Field Service Team",
                    "status": "needs_human",
                },
            }

        # SCENARIO 3: Soundbox is genuinely online & healthy
        reply = (
            f"Soundbox {serial} is verified ONLINE with {battery}% battery. "
            f"Signal strength: {diagnostics.get('signal_quality', 'GOOD')}. "
            f"Voice test: If you missed an announcement, hold the volume up '+' key for 2 seconds to replay the last transaction."
        )
        return {
            "step": "DEVICE_HEALTHY",
            "chip_status": "verified",
            "agent_reply": reply,
            "action_card": None,
        }

    def run(
        self,
        merchant_id: str,
        query_text: str,
        device_ref: Optional[str] = None,
        city: str = "Jaipur",
        actor_id: str = "merchant_user",
    ) -> Dict[str, Any]:
        execution_id = f"exec_fix_{uuid.uuid4().hex[:10]}"
        initial_state: FixAgentState = {
            "merchant_id": merchant_id,
            "city": city,
            "query_text": query_text,
            "device_ref": device_ref,
            "execution_id": execution_id,
            "actor_id": actor_id,
            "loop_count": 0,
        }

        # Run through LangGraph
        final_state = self.graph.invoke(initial_state)

        agent_reply = final_state.get("agent_reply", "")
        if gemini_adapter.is_available() and final_state.get("step") != "IDENTIFY":
            llm_exp = gemini_adapter.generate_explanation(
                agent_name="FixAgent",
                branch=final_state.get("step", ""),
                ground_truth={
                    "device": final_state.get("device_data"),
                    "diagnostics": final_state.get("diagnostics"),
                    "technician_booked": final_state.get("technician_booked"),
                    "technician_slot": final_state.get("technician_slot"),
                    "deterministic_reply": agent_reply,
                },
                user_query=query_text,
            )
            if llm_exp and llm_exp.reply:
                agent_reply = llm_exp.reply

        # Synthesize voice output via swappable SpeechAdapter
        speech_res = self.speech_adapter.synthesize(agent_reply, language="hi-IN")

        # Record top-level audit event
        audit_log(
            db=self.db,
            actor=actor_id,
            action="FIX_INVESTIGATION_COMPLETED",
            target=final_state.get("device_ref") or "unknown_device",
            result=final_state.get("step", "UNKNOWN"),
            policy_decision_id="dec_fix_finish",
            idempotency_key=execution_id,
        )

        return {
            "agent": "FIX",
            "step": final_state.get("step"),
            "agent_reply": agent_reply,
            "chip_status": final_state.get("chip_status"),
            "device_ref": final_state.get("device_ref"),
            "technician_booked": final_state.get("technician_booked", False),
            "technician_slot": final_state.get("technician_slot"),
            "case_id": final_state.get("case_id"),
            "action_card": final_state.get("action_card"),
            "speech_audio_base64": speech_res.audio_base64,
            "speech_duration_seconds": speech_res.duration_seconds,
            "is_synthetic": True,
            "environment": "DEMO",
        }
