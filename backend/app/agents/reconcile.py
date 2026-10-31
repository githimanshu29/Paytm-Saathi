import re
import uuid
from typing import Any, Dict, Optional, TypedDict
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from app.adapters.settlement import MockSettlementAdapter
from app.tools.reconcile import ReconcileTools


class ReconcileAgentState(TypedDict):
    merchant_id: str
    query_text: str
    settlement_date: Optional[str]
    execution_id: Optional[str]
    actor_id: Optional[str]
    settlement_summary: Optional[Dict[str, Any]]
    line_items: Optional[Dict[str, Any]]
    calc_result: Optional[Dict[str, Any]]
    dispute_data: Optional[Dict[str, Any]]
    chip_status: str
    branch: str
    agent_reply: str
    breakdown_card: Optional[Dict[str, Any]]


class ReconcileAgent:
    """
    The Reconcile Specialist Agent (Settlement Copilot).
    Uses deterministic code-based integer arithmetic for reconciliation.
    Files an evidence-backed dispute review case only when a genuine mismatch remains.
    """

    def __init__(self, db: Session):
        self.db = db
        self.adapter = MockSettlementAdapter(db)
        self.tools = ReconcileTools(self.adapter, db)
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(ReconcileAgentState)

        builder.add_node("parse_date", self._node_parse_date)
        builder.add_node("fetch_and_calculate", self._node_fetch_and_calculate)
        builder.add_node("generate_explanation_and_action", self._node_generate_explanation_and_action)

        builder.set_entry_point("parse_date")
        builder.add_edge("parse_date", "fetch_and_calculate")
        builder.add_edge("fetch_and_calculate", "generate_explanation_and_action")
        builder.add_edge("generate_explanation_and_action", END)

        return builder.compile()

    def _node_parse_date(self, state: ReconcileAgentState) -> Dict[str, Any]:
        query = (state.get("query_text") or "").lower()
        settlement_date = state.get("settlement_date")

        if not settlement_date:
            # Check for specific dates in query
            if "27" in query:
                settlement_date = "2026-10-27"
            elif "28" in query or "yesterday" in query or "kal" in query:
                settlement_date = "2026-10-28"
            elif "today" in query or "aaj" in query or "29" in query:
                settlement_date = "2026-10-28"  # Settle against last closed cycle
            else:
                # Default to yesterday's settlement cycle
                settlement_date = "2026-10-28"

        return {"settlement_date": settlement_date}

    def _node_fetch_and_calculate(self, state: ReconcileAgentState) -> Dict[str, Any]:
        merchant_id = state.get("merchant_id", "mer_sharma_kirana")
        settlement_date = state.get("settlement_date", "2026-10-28")
        execution_id = state.get("execution_id", f"exec_rec_{uuid.uuid4().hex[:8]}")
        actor_id = state.get("actor_id", "merchant_user")

        summary = self.tools.get_settlement_summary(
            merchant_id=merchant_id,
            settlement_date=settlement_date,
            execution_id=execution_id,
            actor_id=actor_id,
        )

        line_items = self.tools.get_settlement_line_items(
            merchant_id=merchant_id,
            settlement_date=settlement_date,
            execution_id=execution_id,
            actor_id=actor_id,
        )

        # Code-based deterministic integer calculation (NEVER float, NEVER LLM)
        if summary.get("found"):
            calc_result = self.tools.calculate_settlement_difference(
                gross_sales_paise=summary["gross_sales"],
                refunds_paise=summary["refunds"],
                fees_paise=summary["fees"],
                chargebacks_paise=summary["chargebacks"],
                net_settled_paise=summary["net_settled"],
            )
        else:
            calc_result = {
                "is_reconciled": False,
                "difference_paise": 0,
                "net_expected_inr": "₹0.00",
                "net_settled_inr": "₹0.00",
                "difference_inr": "₹0.00",
                "direction": "UNKNOWN",
            }

        return {
            "settlement_summary": summary,
            "line_items": line_items,
            "calc_result": calc_result,
        }

    def _node_generate_explanation_and_action(self, state: ReconcileAgentState) -> Dict[str, Any]:
        merchant_id = state.get("merchant_id", "mer_sharma_kirana")
        settlement_date = state.get("settlement_date", "2026-10-28")
        execution_id = state.get("execution_id", f"exec_rec_{uuid.uuid4().hex[:8]}")
        actor_id = state.get("actor_id", "merchant_user")
        summary = state.get("settlement_summary") or {}
        calc = state.get("calc_result") or {}

        if not summary.get("found"):
            return {
                "branch": "NO_DATA",
                "chip_status": "pending",
                "agent_reply": f"No settlement batch was found for {settlement_date}. Please check if transactions were processed on that date.",
                "breakdown_card": None,
                "dispute_data": None,
            }

        is_reconciled = calc.get("is_reconciled", False)
        gross_inr = summary.get("gross_sales_inr", "₹0.00")
        refunds_inr = summary.get("refunds_inr", "₹0.00")
        fees_inr = summary.get("fees_inr", "₹0.00")
        cbs_inr = summary.get("chargebacks_inr", "₹0.00")
        expected_inr = calc.get("net_expected_inr", summary.get("net_expected_inr", "₹0.00"))
        settled_inr = calc.get("net_settled_inr", summary.get("net_settled_inr", "₹0.00"))
        diff_inr = calc.get("difference_inr", "₹0.00")
        diff_paise = calc.get("difference_paise", 0)

        # SCENARIO 1: Fully Reconciled (No dispute needed)
        if is_reconciled:
            reply = (
                f"Settlement for {settlement_date} reconciles completely to your bank account:\n"
                f"• Gross Sales: {gross_inr}\n"
                f"• Customer Refunds: -{refunds_inr}\n"
                f"• MDR & Soundbox Fees: -{fees_inr}\n"
                f"• Chargebacks: {cbs_inr}\n"
                f"→ Net Amount to You: {settled_inr} (Transferred via UTR: {summary.get('bank_utr', 'N/A')})\n\n"
                f"All deductions match your ledger exactly. No discrepancy detected."
            )
            card = {
                "type": "SETTLEMENT_BREAKDOWN",
                "settlement_date": settlement_date,
                "gross_sales": gross_inr,
                "refunds": refunds_inr,
                "fees": fees_inr,
                "chargebacks": cbs_inr,
                "net_expected": expected_inr,
                "net_settled": settled_inr,
                "discrepancy": "₹0.00",
                "is_reconciled": True,
                "status": "verified",
                "bank_utr": summary.get("bank_utr"),
                "dispute_case_id": None,
                "evidence_status": "NONE_REQUIRED",
            }
            return {
                "branch": "FULLY_RECONCILED",
                "chip_status": "verified",
                "agent_reply": reply,
                "breakdown_card": card,
                "dispute_data": None,
            }

        # SCENARIO 2: Genuine Discrepancy Found (Create evidence-backed dispute review)
        evidence_note = (
            f"Settlement audit mismatch on {settlement_date}: Bank payout credited {settled_inr} "
            f"vs calculated net {expected_inr}. Unexplained shortfall of {diff_inr}. "
            f"Bank UTR: {summary.get('bank_utr')}. Sponsor account: {summary.get('nodal_account')}."
        )

        dispute_res = self.tools.create_settlement_dispute(
            merchant_id=merchant_id,
            settlement_date=settlement_date,
            difference_paise=diff_paise,
            reason=f"Unexplained settlement shortfall of {diff_inr} against nodal payout",
            execution_id=execution_id,
            actor_id=actor_id,
            evidence_notes=evidence_note,
        )
        task_id = dispute_res.get("task_id", "case_disp_auto")

        reply = (
            f"Discrepancy detected in your {settlement_date} settlement breakdown:\n"
            f"• Gross Sales: {gross_inr}\n"
            f"• Customer Refunds: -{refunds_inr}\n"
            f"• MDR Processing Fees: -{fees_inr}\n"
            f"• Chargebacks Deducted: -{cbs_inr}\n"
            f"→ Calculated Net: {expected_inr}\n"
            f"→ Actual Bank Deposit: {settled_inr}\n"
            f"⚠️ Unexplained Shortfall: {diff_inr}\n\n"
            f"I have opened a priority settlement review case (Case ID: {task_id}) for our Nodal Settlement Operations team. "
            f"Please tap below to attach your bank passbook/statement proof to expedite resolution."
        )

        card = {
            "type": "SETTLEMENT_BREAKDOWN",
            "settlement_date": settlement_date,
            "gross_sales": gross_inr,
            "refunds": refunds_inr,
            "fees": fees_inr,
            "chargebacks": cbs_inr,
            "net_expected": expected_inr,
            "net_settled": settled_inr,
            "discrepancy": f"-{diff_inr}",
            "is_reconciled": False,
            "status": "needs_human",
            "bank_utr": summary.get("bank_utr"),
            "dispute_case_id": task_id,
            "evidence_status": "PROOF_ATTACHED_AND_REVIEW_QUEUED",
        }

        return {
            "branch": "ANOMALY_DISPUTE_FILED",
            "chip_status": "needs_human",
            "agent_reply": reply,
            "breakdown_card": card,
            "dispute_data": dispute_res,
        }

    def run(
        self,
        merchant_id: str,
        query_text: str,
        settlement_date: Optional[str] = None,
        actor_id: str = "merchant_user",
    ) -> Dict[str, Any]:
        initial_state: ReconcileAgentState = {
            "merchant_id": merchant_id,
            "query_text": query_text,
            "settlement_date": settlement_date,
            "execution_id": f"exec_rec_{uuid.uuid4().hex[:8]}",
            "actor_id": actor_id,
            "settlement_summary": None,
            "line_items": None,
            "calc_result": None,
            "dispute_data": None,
            "chip_status": "pending",
            "branch": "INIT",
            "agent_reply": "",
            "breakdown_card": None,
        }

        final_state = self.graph.invoke(initial_state)

        return {
            "agent": "RECONCILE",
            "branch": final_state.get("branch"),
            "chip_status": final_state.get("chip_status"),
            "agent_reply": final_state.get("agent_reply"),
            "settlement_date": final_state.get("settlement_date"),
            "breakdown_card": final_state.get("breakdown_card"),
            "dispute_data": final_state.get("dispute_data"),
            "settlement_summary": final_state.get("settlement_summary"),
        }
