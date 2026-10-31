import uuid
from typing import Any, Dict, List, Optional, TypedDict
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.tools.revive import ReviveTools
from app.adapters.speech import MockSpeechAdapter


class ReviveAgentState(TypedDict):
    merchant_id: str
    execution_id: str
    actor_id: str
    metrics: Optional[Dict[str, Any]]
    device_status: Optional[Dict[str, Any]]
    settlement_status: Optional[Dict[str, Any]]
    diagnosed_cause: Optional[str]  # DEVICE_ISSUE | SETTLEMENT_ISSUE | COMPETITOR_OR_DISENGAGEMENT
    branch: str  # INIT | DEVICE_HANDOFF | SETTLEMENT_HANDOFF | RETENTION_OFFER | NO_DROP
    followup_data: Optional[Dict[str, Any]]
    warm_lead_data: Optional[Dict[str, Any]]
    chip_status: str  # verified | executed | pending | awaiting_approval | needs_human
    agent_reply: str
    checkin_card: Optional[Dict[str, Any]]


class ReviveAgent:
    """
    Revive Specialist Agent (Dormant Merchant Recovery Copilot).
    Orchestrates the 3 drop cause branches and hands off to Fix / Reconcile or dispatches sales warm leads.
    """

    def __init__(self, db: Session):
        self.db = db
        self.tools = ReviveTools(db=db)
        self.speech_adapter = MockSpeechAdapter()
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(ReviveAgentState)

        builder.add_node("scan_and_compute_decline", self._node_scan_and_compute_decline)
        builder.add_node("diagnose_root_cause", self._node_diagnose_root_cause)
        builder.add_node("execute_revive_action", self._node_execute_revive_action)

        builder.set_entry_point("scan_and_compute_decline")

        def route_after_scan(state: ReviveAgentState):
            if state.get("branch") == "NO_DROP":
                return END
            return "diagnose_root_cause"

        builder.add_conditional_edges(
            "scan_and_compute_decline",
            route_after_scan,
            {
                "diagnose_root_cause": "diagnose_root_cause",
                END: END,
            },
        )

        builder.add_edge("diagnose_root_cause", "execute_revive_action")
        builder.add_edge("execute_revive_action", END)

        return builder.compile()

    def _node_scan_and_compute_decline(self, state: ReviveAgentState) -> Dict[str, Any]:
        merchant_id = state["merchant_id"]
        execution_id = state.get("execution_id", f"exec_rev_{uuid.uuid4().hex[:8]}")
        actor_id = state.get("actor_id", "system_scanner")

        metrics = self.tools.get_merchant_metrics(merchant_id, execution_id=execution_id, actor_id=actor_id)
        if not metrics.get("found"):
            return {
                "branch": "NO_DROP",
                "chip_status": "verified",
                "agent_reply": f"Merchant {merchant_id} has no metrics history or is newly onboarded.",
                "checkin_card": None,
            }

        drop_pct = metrics.get("drop_percentage", 0)
        if drop_pct < 40:
            return {
                "metrics": metrics,
                "branch": "NO_DROP",
                "chip_status": "verified",
                "agent_reply": f"Merchant {metrics.get('store_name')} is HEALTHY. Volume drop is {drop_pct}% (below 40% threshold).",
                "checkin_card": None,
            }

        return {
            "metrics": metrics,
            "branch": "AT_RISK_DETECTED",
        }

    def _node_diagnose_root_cause(self, state: ReviveAgentState) -> Dict[str, Any]:
        merchant_id = state["merchant_id"]
        execution_id = state.get("execution_id", f"exec_rev_{uuid.uuid4().hex[:8]}")
        actor_id = state.get("actor_id", "system_scanner")

        # 1. Reuse Phase 5's DeviceAdapter to inspect hardware
        dev_res = self.tools.get_device_status(merchant_id, execution_id=execution_id, actor_id=actor_id)

        # If device is degraded or offline, technical cause found!
        if dev_res.get("found") and dev_res.get("is_degraded"):
            return {
                "device_status": dev_res,
                "diagnosed_cause": "DEVICE_ISSUE",
            }

        # 2. Reuse Phase 6's SettlementAdapter to inspect payouts
        sett_res = self.tools.get_settlement_status(merchant_id, execution_id=execution_id, actor_id=actor_id)

        # If payout discrepancy exists, technical cause found!
        if sett_res.get("has_discrepancy"):
            return {
                "device_status": dev_res,
                "settlement_status": sett_res,
                "diagnosed_cause": "SETTLEMENT_ISSUE",
            }

        # 3. No technical cause -> Hardware healthy & settlements balanced -> Competitor or Disengagement!
        return {
            "device_status": dev_res,
            "settlement_status": sett_res,
            "diagnosed_cause": "COMPETITOR_OR_DISENGAGEMENT",
        }

    def _node_execute_revive_action(self, state: ReviveAgentState) -> Dict[str, Any]:
        merchant_id = state["merchant_id"]
        execution_id = state.get("execution_id", f"exec_rev_{uuid.uuid4().hex[:8]}")
        actor_id = state.get("actor_id", "system_scanner")
        metrics = state.get("metrics") or {}
        cause = state.get("diagnosed_cause")
        store_name = metrics.get("store_name", "Kirana Store")
        drop_pct = metrics.get("drop_percentage", 70)

        # -------------------------------------------------------------------------
        # BRANCH 1: DEVICE ISSUE (Hand off evidence to Fix Agent rather than re-diagnosing)
        # -------------------------------------------------------------------------
        if cause == "DEVICE_ISSUE":
            dev = state.get("device_status") or {}
            serial = dev.get("serial_number", "SB-DEV")
            status_desc = dev.get("status", "OFFLINE")
            battery = dev.get("battery_level", 0)

            title = f"Soundbox Telemetry Alert: {serial} is {status_desc}"
            body = (
                f"We noticed Soundbox {serial} has been {status_desc} (battery: {battery}%). "
                f"This technical issue caused your transaction volume to decline by {drop_pct}%. "
                f"Our Fix Agent has queued remote diagnostics and technician dispatch."
            )

            fol_res = self.tools.create_merchant_followup(
                merchant_id=merchant_id,
                cause_type="DEVICE_ISSUE",
                message_title=title,
                message_body=body,
                handed_off_to="FIX",
                execution_id=execution_id,
                actor_id=actor_id,
            )

            reply = (
                f"Dormancy Diagnosis for {store_name}: Genuine {drop_pct}% volume drop detected. "
                f"Root Cause: Soundbox {serial} is {status_desc} (battery {battery}%). "
                f"Action: Evidence handed off to Saathi Fix Agent for priority field engineer dispatch. "
                f"Merchant notification delivered."
            )

            card = {
                "type": "REVIVE_CHECKIN",
                "followup_id": fol_res.get("followup_id"),
                "cause_type": "DEVICE_ISSUE",
                "drop_percentage": drop_pct,
                "title": title,
                "body": body,
                "status": "DELIVERED",
                "handed_off_to": "FIX",
                "offer_details": None,
                "action_prompt": "Technician visit booked via Fix Agent",
            }

            return {
                "branch": "DEVICE_HANDOFF",
                "chip_status": "needs_human",
                "agent_reply": reply,
                "followup_data": fol_res,
                "checkin_card": card,
            }

        # -------------------------------------------------------------------------
        # BRANCH 2: SETTLEMENT ISSUE (Hand off evidence to Reconcile Agent)
        # -------------------------------------------------------------------------
        if cause == "SETTLEMENT_ISSUE":
            sett = state.get("settlement_status") or {}
            diff_inr = sett.get("discrepancy_inr", "₹0.00")
            s_date = sett.get("settlement_date", "recent cycle")

            title = f"Settlement Payout Alert: Shortfall of {diff_inr} Detected"
            body = (
                f"Our audit detected an unresolved settlement discrepancy of {diff_inr} on {s_date}. "
                f"This payout delay caused your shop volume to drop by {drop_pct}%. "
                f"Our Reconcile Desk is expediting nodal bank clearance."
            )

            fol_res = self.tools.create_merchant_followup(
                merchant_id=merchant_id,
                cause_type="SETTLEMENT_ISSUE",
                message_title=title,
                message_body=body,
                handed_off_to="RECONCILE",
                execution_id=execution_id,
                actor_id=actor_id,
            )

            reply = (
                f"Dormancy Diagnosis for {store_name}: Genuine {drop_pct}% volume drop detected. "
                f"Root Cause: Unresolved payout shortfall of {diff_inr} on {s_date}. "
                f"Action: Evidence handed off to Saathi Reconcile Agent and Nodal Settlement Ops. "
                f"Merchant notification delivered."
            )

            card = {
                "type": "REVIVE_CHECKIN",
                "followup_id": fol_res.get("followup_id"),
                "cause_type": "SETTLEMENT_ISSUE",
                "drop_percentage": drop_pct,
                "title": title,
                "body": body,
                "status": "DELIVERED",
                "handed_off_to": "RECONCILE",
                "offer_details": None,
                "action_prompt": "Settlement dispute priority escalated",
            }

            return {
                "branch": "SETTLEMENT_HANDOFF",
                "chip_status": "needs_human",
                "agent_reply": reply,
                "followup_data": fol_res,
                "checkin_card": card,
            }

        # -------------------------------------------------------------------------
        # BRANCH 3: COMPETITOR / DISENGAGEMENT (Gated Policy Retention Offer)
        # -------------------------------------------------------------------------
        offer_code = "BOOSTER30"
        offer_details = "0% MDR on your next 100 UPI transactions + ₹100 Soundbox cash rebate"
        title = "Exclusive Kirana Booster Growth Offer from Paytm Saathi"
        body = (
            f"Namaste {store_name}! We noticed a {drop_pct}% slowdown in your Soundbox announcements this week. "
            f"To boost your counter sales, we've unlocked the Kirana Booster: {offer_details}. "
            f"Tap Accept to activate this offer and request a complimentary QR standee refresh."
        )

        fol_res = self.tools.create_merchant_followup(
            merchant_id=merchant_id,
            cause_type="COMPETITOR_OR_DISENGAGEMENT",
            message_title=title,
            message_body=body,
            offer_code=offer_code,
            offer_details=offer_details,
            handed_off_to=None,
            execution_id=execution_id,
            actor_id=actor_id,
        )

        reply = (
            f"Dormancy Diagnosis for {store_name}: Volume drop of {drop_pct}% detected. "
            f"Root Cause: Hardware & bank payouts verified healthy. Correlates to competitor QR or merchant disengagement. "
            f"Action: Gated Kirana Booster retention offer delivered to merchant app with Accept/Dismiss actions."
        )

        card = {
            "type": "REVIVE_CHECKIN",
            "followup_id": fol_res.get("followup_id"),
            "cause_type": "COMPETITOR_OR_DISENGAGEMENT",
            "drop_percentage": drop_pct,
            "title": title,
            "body": body,
            "status": "DELIVERED",
            "handed_off_to": None,
            "offer_details": offer_details,
            "action_prompt": "Awaiting merchant Accept / Dismiss",
        }

        return {
            "branch": "RETENTION_OFFER",
            "chip_status": "awaiting_approval",
            "agent_reply": reply,
            "followup_data": fol_res,
            "checkin_card": card,
        }

    def run(
        self,
        merchant_id: str,
        actor_id: str = "system_scanner",
    ) -> Dict[str, Any]:
        initial_state: ReviveAgentState = {
            "merchant_id": merchant_id,
            "execution_id": f"exec_rev_{uuid.uuid4().hex[:8]}",
            "actor_id": actor_id,
            "metrics": None,
            "device_status": None,
            "settlement_status": None,
            "diagnosed_cause": None,
            "branch": "INIT",
            "followup_data": None,
            "warm_lead_data": None,
            "chip_status": "pending",
            "agent_reply": "",
            "checkin_card": None,
        }

        final_state = self.graph.invoke(initial_state)
        branch = final_state.get("branch")
        handoff_agent = "FIX" if branch == "DEVICE_HANDOFF" else ("RECONCILE" if branch == "SETTLEMENT_HANDOFF" else None)
        action_taken = (
            "HANDOFF_TO_FIX_AGENT" if branch == "DEVICE_HANDOFF"
            else ("HANDOFF_TO_RECONCILE_AGENT" if branch == "SETTLEMENT_HANDOFF"
            else ("OFFER_RETENTION_BOOSTER" if branch == "RETENTION_OFFER" else branch))
        )
        handoff_evidence = final_state.get("device_status") if branch == "DEVICE_HANDOFF" else (final_state.get("settlement_status") if branch == "SETTLEMENT_HANDOFF" else None)

        fol_data = final_state.get("followup_data") or {}
        card_data = final_state.get("checkin_card") or {}
        followup_summary = {
            "followup_id": fol_data.get("followup_id") or card_data.get("followup_id"),
            "message_title": card_data.get("title") or fol_data.get("title", ""),
            "offer_code": fol_data.get("offer_code") or ("BOOSTER30" if branch == "RETENTION_OFFER" else None),
            "status": card_data.get("status") or fol_data.get("status", "DELIVERED"),
            "handed_off_to": card_data.get("handed_off_to") or fol_data.get("handed_off_to") or handoff_agent,
        }

        return {
            "success": True,
            "agent": "REVIVE",
            "merchant_id": merchant_id,
            "branch": branch,
            "chip_status": final_state.get("chip_status"),
            "diagnosed_cause": final_state.get("diagnosed_cause"),
            "agent_reply": final_state.get("agent_reply"),
            "checkin_card": final_state.get("checkin_card"),
            "followup_data": fol_data,
            "followup": followup_summary,
            "metrics": final_state.get("metrics"),
            "action_taken": action_taken,
            "handoff_agent": handoff_agent,
            "handoff_evidence": handoff_evidence,
            "revival_stage": "FOLLOWUP_SENT" if branch == "RETENTION_OFFER" else "AT_RISK",
        }

    run_revive_workflow = run

    def scan_all_at_risk_merchants(self, threshold: int = 40) -> Dict[str, Any]:
        """
        Executes dormancy scan across all merchants in the tenant database,
        diagnosing root causes and creating targeted follow-ups.
        """
        at_risk = self.tools.revive_adapter.list_at_risk_merchants(threshold_drop_percentage=threshold)
        results = []
        for m in at_risk:
            res = self.run(merchant_id=m.merchant_id, actor_id="scheduled_dormancy_job")
            results.append(res)

        return {
            "total_at_risk_scanned": len(at_risk),
            "results": results,
        }
