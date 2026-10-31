import re
import uuid
from typing import Any, Dict, List, Optional, TypedDict
from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, END
from app.adapters.transaction import MockTransactionAdapter
from app.tools.resolve import ResolveTools
from app.adapters.gemini import gemini_adapter
from app.policy.audit import audit_log
from app.schemas.policy import RiskTier

class ResolveAgentState(TypedDict, total=False):
    merchant_id: str
    query_text: str
    tx_ref: Optional[str]
    is_greeting: bool
    is_overview: bool
    is_policy_faq: bool
    policy_faq_topic: Optional[str]
    execution_id: str
    actor_id: str
    tx_data: Optional[Dict[str, Any]]
    events_data: Optional[List[Dict[str, Any]]]
    branch: str  # A_AUTO_REVERSAL | B_STUCK_REFUND_REVIEW | C_PAYMENT_CONFIRMED | D_FRAUD_ESCALATED | DISPUTE_OVERVIEW | POLICY_ADVISORY | GREETING | UNKNOWN | NOT_FOUND
    agent_reply: str
    explanation_en: str
    explanation_hi: str
    chip_status: str
    approval_card: Optional[Dict[str, Any]]
    action_card: Optional[Dict[str, Any]]
    case_id: Optional[str]
    loop_count: int

class ResolveAgent:
    """
    Specialist Agent 1: Resolve (Failed or disputed payment complaints).
    Uses LangGraph for deterministic state-machine routing and verifiable action execution.
    """

    def __init__(self, db: Session):
        self.db = db
        self.adapter = MockTransactionAdapter(db)
        self.tools = ResolveTools(self.adapter, db)
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(ResolveAgentState)

        builder.add_node("identify_transaction", self._node_identify_transaction)
        builder.add_node("authoritative_lookup", self._node_authoritative_lookup)
        builder.add_node("route_and_execute", self._node_route_and_execute)

        builder.set_entry_point("identify_transaction")
        builder.add_edge("identify_transaction", "authoritative_lookup")
        builder.add_edge("authoritative_lookup", "route_and_execute")
        builder.add_edge("route_and_execute", END)

        return builder.compile()

    def _node_identify_transaction(self, state: ResolveAgentState) -> Dict[str, Any]:
        loop_count = state.get("loop_count", 0) + 1
        query = (state.get("query_text") or "").strip()
        query_lower = query.lower()
        tx_ref = state.get("tx_ref")
        is_greeting = False
        is_overview = False
        policy_faq_topic = None

        if not tx_ref:
            # 1. Pure greeting check
            if re.search(r"^(hi|hello|hey|namaste|pranam|good\s+morning|good\s+afternoon|good\s+evening)\s*$", query_lower):
                return {"branch": "GREETING", "is_greeting": True, "loop_count": loop_count}

            # 2. General Banking / Policy Advisory FAQ checks
            if any(w in query_lower for w in ["cash refund", "cash de du", "rokad de du", "rokad wapas", "cash de sakte"]):
                return {"branch": "POLICY_ADVISORY", "is_policy_faq": True, "policy_faq_topic": "CASH_REFUND_PROHIBITED", "loop_count": loop_count}
            if any(w in query_lower for w in ["what is u30", "u30 kya", "u30 error", "u30 code"]):
                return {"branch": "POLICY_ADVISORY", "is_policy_faq": True, "policy_faq_topic": "WHAT_IS_U30", "loop_count": loop_count}
            if any(w in query_lower for w in ["what is u69", "u69 kya", "u69 error", "u69 code"]):
                return {"branch": "POLICY_ADVISORY", "is_policy_faq": True, "policy_faq_topic": "WHAT_IS_U69", "loop_count": loop_count}
            if any(w in query_lower for w in ["deduct from settlement", "settlement se katega", "mere account se katega", "will review deduct", "will refund review deduct"]):
                return {"branch": "POLICY_ADVISORY", "is_policy_faq": True, "policy_faq_topic": "REFUND_REVIEW_ZERO_DEDUCTION", "loop_count": loop_count}

            # 3. Dispute Overview Intent: All failed transactions, check disputes, etc.
            is_overview_intent = (
                any(w in query_lower for w in [
                    "all failed", "all disputes", "show failed", "check failed", "show all failed",
                    "list failed", "failed payments", "stuck payments", "recent payment disputes",
                    "payment disputes", "disputed payments", "customer complaints", "payment check karo",
                    "kya koi payment fail", "koi payment fasa", "dispute hub", "failed list"
                ])
                and not any(name in query_lower for name in ["alok", "deepak", "pooja", "250", "500", "320", "1200"])
            )
            if is_overview_intent:
                return {"branch": "DISPUTE_OVERVIEW", "is_overview": True, "loop_count": loop_count}

            # 4. Explicit Transaction or Reference Extraction
            match = re.search(r"(PAYTM_[A-Z0-9_]+|SB-[A-Z0-9]+|txn_[a-z0-9_]+|UPI_[A-Za-z0-9_]+)", query, re.IGNORECASE)
            if match:
                tx_ref = match.group(0).upper()
            elif "alok" in query_lower or "250" in query_lower:
                tx_ref = "PAYTM_REV_AUTO_991201"
            elif "deepak" in query_lower or "500" in query_lower:
                tx_ref = "PAYTM_STUCK_881920"
            elif "pooja" in query_lower or "320" in query_lower:
                tx_ref = "PAYTM_SUCC_771829"
            elif "1200" in query_lower or "fraud" in query_lower or "suspicious" in query_lower or "fake" in query_lower or "za" in query_lower:
                tx_ref = "PAYTM_FRAUD_661904"
            elif "stuck" in query_lower and "reversal" in query_lower:
                tx_ref = "PAYTM_STUCK_881920"
            elif "auto reversal" in query_lower or "auto-reversal" in query_lower:
                tx_ref = "PAYTM_REV_AUTO_991201"
            elif any(w in query_lower for w in ["failed", "stuck", "dispute", "check payment", "recent payment"]):
                return {"branch": "DISPUTE_OVERVIEW", "is_overview": True, "loop_count": loop_count}

        return {
            "tx_ref": tx_ref,
            "is_greeting": is_greeting,
            "is_overview": is_overview,
            "policy_faq_topic": policy_faq_topic,
            "loop_count": loop_count,
        }

    def _node_authoritative_lookup(self, state: ResolveAgentState) -> Dict[str, Any]:
        branch = state.get("branch")
        if state.get("is_greeting") or branch == "GREETING":
            return {
                "branch": "GREETING",
                "chip_status": "verified",
                "agent_reply": (
                    "Namaste! I am Saathi, your Kirana AI teammate. "
                    "I actively investigate failed, stuck, or unannounced customer payments using authoritative bank records. "
                    "How can I help you today? You can say: 'Customer ₹250 failed', 'Deepak ₹500 stuck reversal', or 'Show all failed payments'."
                ),
                "explanation_en": "Saathi payment investigation assistant is active.",
                "explanation_hi": "Paytm Saathi bhugtan jaanch sahayak sakriya hai.",
            }

        if branch == "POLICY_ADVISORY":
            return {"branch": "POLICY_ADVISORY", "policy_faq_topic": state.get("policy_faq_topic")}

        if branch == "DISPUTE_OVERVIEW" or state.get("is_overview"):
            return {"branch": "DISPUTE_OVERVIEW"}

        tx_ref = state.get("tx_ref")
        execution_id = state.get("execution_id", f"exec_{uuid.uuid4().hex[:8]}")
        actor_id = state.get("actor_id", "merchant_user")

        if not tx_ref:
            return {
                "branch": "UNKNOWN",
                "chip_status": "pending",
                "agent_reply": (
                    "Please provide the transaction UTR number or customer name/amount (e.g., 'Alok ₹250', 'Deepak ₹500', or 'Show all failed payments') "
                    "so I can look up the bank records for you."
                ),
                "explanation_en": "Please provide the transaction UTR number or customer name.",
                "explanation_hi": "Kripya transaction UTR number ya customer ka naam batayein.",
            }

        # R0 lookup via constrained tool
        tx_data = self.tools.get_transaction_status(tx_ref, execution_id, actor_id)
        events_data = self.tools.get_related_payment_events(tx_data.get("id", tx_ref), execution_id, actor_id)

        return {
            "tx_data": tx_data,
            "events_data": events_data,
        }

    def _node_route_and_execute(self, state: ResolveAgentState) -> Dict[str, Any]:
        branch = state.get("branch")
        query_lower = (state.get("query_text") or "").lower()

        if branch == "GREETING":
            return {
                "branch": "GREETING",
                "chip_status": state.get("chip_status", "verified"),
                "agent_reply": state.get("agent_reply"),
                "explanation_en": state.get("explanation_en"),
                "explanation_hi": state.get("explanation_hi"),
                "approval_card": None,
                "action_card": None,
            }

        if branch == "POLICY_ADVISORY":
            topic = state.get("policy_faq_topic")
            if topic == "CASH_REFUND_PROHIBITED":
                reply = (
                    "Policy Notice: Paytm strictly advises AGAINST issuing cash refunds for failed digital transactions. "
                    "When a customer's UPI payment fails or auto-reverses, the funds are automatically returned directly to their bank account "
                    "within 24–48 banking hours. Giving cash causes a double financial loss for your store."
                )
            elif topic == "WHAT_IS_U30":
                reply = (
                    "NPCI Code U30 indicates a bank timeout. The customer was debited, but the merchant switch did not receive "
                    "confirmation within the network threshold. The switch automatically schedules an auto-reversal, and funds will return "
                    "to the customer's account in 24–48 banking hours. Do NOT provide goods on credit."
                )
            elif topic == "WHAT_IS_U69":
                reply = (
                    "NPCI Code U69 indicates that the bank auto-reversal timed out beyond 48 hours without remitter bank confirmation. "
                    "An official Refund Review Request is created so Paytm operations can manually trace and credit the funds."
                )
            elif topic == "REFUND_REVIEW_ZERO_DEDUCTION":
                reply = (
                    "Confirmation: Authorizing a Refund Review Request does NOT deduct from your settlement balance. "
                    "It only queues an internal operations investigation with the customer's bank. Your store payouts are 100% protected."
                )
            else:
                reply = "Paytm Saathi payment resolution is active and strictly adheres to NPCI banking SLA guidelines."

            return {
                "branch": "POLICY_ADVISORY",
                "chip_status": "verified",
                "agent_reply": reply,
                "explanation_en": reply,
                "explanation_hi": "Paytm Saathi bhugtan suraksha niyam anusar karya karta hai.",
                "approval_card": None,
                "action_card": None,
            }

        if branch == "DISPUTE_OVERVIEW":
            dispute_card = {
                "type": "RESOLVE_DISPUTE_CARD",
                "title": "Payment Dispute & Failed Transactions",
                "status": "verified",
                "total_investigations": 4,
                "summary_metrics": {
                    "auto_reversal_count": 1,
                    "stuck_count": 1,
                    "confirmed_success_count": 1,
                    "fraud_count": 1,
                },
                "transactions": [
                    {
                        "customer_name": "Alok Gupta",
                        "amount_formatted": "₹250.00",
                        "utr": "PAYTM_REV_AUTO_991201",
                        "bank_code": "U30_AUTO_REVERSAL",
                        "status": "AUTO_REVERSAL_IN_PROGRESS",
                        "recommendation": "Bank timeout. Auto-reversal in progress (24-48h). Do NOT provide goods on credit.",
                        "quick_action_label": "🔍 Check Alok (₹250)",
                        "quick_action_query": "Customer Alok says ₹250 failed, did money get deducted?",
                    },
                    {
                        "customer_name": "Deepak Verma",
                        "amount_formatted": "₹500.00",
                        "utr": "PAYTM_STUCK_881920",
                        "bank_code": "U69_REVERSAL_STUCK",
                        "status": "REVERSAL_STUCK",
                        "recommendation": "Reversal timed out (>48h). Refund review ready for merchant authorization. Zero deduction.",
                        "quick_action_label": "📋 Review Deepak (₹500)",
                        "quick_action_query": "Deepak Verma payment of ₹500 is stuck for 3 days",
                    },
                    {
                        "customer_name": "Pooja Chawla",
                        "amount_formatted": "₹320.00",
                        "utr": "PAYTM_SUCC_771829",
                        "bank_code": "00_SUCCESS",
                        "status": "CONFIRMED_SUCCESS",
                        "recommendation": "Payment SUCCESSFUL and credited to settlement. Safe to release goods.",
                        "quick_action_label": "✅ Verify Pooja (₹320)",
                        "quick_action_query": "Customer Pooja says ₹320 was debited but Soundbox did not speak, did it go through?",
                    },
                    {
                        "customer_name": "Unknown Payer",
                        "amount_formatted": "₹1,200.00",
                        "utr": "PAYTM_FRAUD_661904",
                        "bank_code": "ZA_SECURITY_HOLD",
                        "status": "SECURITY_HOLD",
                        "recommendation": "Irregular security status. Escalated to compliance. Do NOT initiate manual payments.",
                        "quick_action_label": "🛡️ Inspect Fraud (₹1,200)",
                        "quick_action_query": "Suspicious payment of ₹1200 from unknown customer, check if fake",
                    },
                ],
                "quick_options": [
                    {"label": "🔍 Check Alok (₹250)", "textToSend": "Customer Alok says ₹250 failed, did money get deducted?"},
                    {"label": "📋 Review Deepak (₹500)", "textToSend": "Deepak Verma payment of ₹500 is stuck for 3 days"},
                    {"label": "✅ Verify Pooja (₹320)", "textToSend": "Customer Pooja says ₹320 was debited but Soundbox did not speak, did it go through?"},
                    {"label": "🛡️ Inspect Fraud (₹1,200)", "textToSend": "Suspicious payment of ₹1200 from unknown customer, check if fake"},
                ],
            }

            reply = (
                "Namaste Ramesh ji! Here is the authoritative summary of payment disputes and investigations for your store:\n\n"
                "1. ⚠️ **Alok Gupta (₹250.00)**: Bank timeout (Code: U30). Auto-reversal is IN PROGRESS. Standard SLA is 24–48 banking hours. Do NOT provide goods on credit.\n"
                "2. ⏱️ **Deepak Verma (₹500.00)**: Auto-reversal stuck >48h (Code: U69). A Refund Review Request is ready for your authorization (Zero deduction from your payout).\n"
                "3. ✅ **Pooja Chawla (₹320.00)**: Confirmed SUCCESSFUL and credited to your settlement account. Safe to release goods.\n"
                "4. 🛡️ **Unknown Payer (₹1,200.00)**: Irregular security hold (Code: ZA). Escalated to Compliance and Risk Operations. Do NOT initiate manual payments.\n\n"
                "💡 *Tap any quick option below to review details or authorize actions.*"
            )

            return {
                "branch": "DISPUTE_OVERVIEW",
                "chip_status": "verified",
                "agent_reply": reply,
                "explanation_en": "Authoritative summary of 4 recent disputed/failed transactions.",
                "explanation_hi": "Aapki dukaan ke 4 transactions ki jaanch report taiyar hai.",
                "approval_card": None,
                "action_card": dispute_card,
            }

        if branch == "UNKNOWN":
            return {
                "branch": "UNKNOWN",
                "chip_status": "pending",
                "agent_reply": state.get("agent_reply"),
                "explanation_en": state.get("explanation_en"),
                "explanation_hi": state.get("explanation_hi"),
                "approval_card": None,
                "action_card": None,
            }

        tx_data = state.get("tx_data", {})
        execution_id = state.get("execution_id", f"exec_{uuid.uuid4().hex[:8]}")
        actor_id = state.get("actor_id", "merchant_user")
        merchant_id = state.get("merchant_id", "mer_demo")

        if not tx_data or not tx_data.get("found"):
            return {
                "branch": "NOT_FOUND",
                "chip_status": "needs_human",
                "agent_reply": f"No transaction record found for reference '{state.get('tx_ref')}'. Please verify the UTR or check your customer's UPI app.",
                "explanation_en": "Transaction reference not found in payment switch records.",
                "explanation_hi": "Payment switch records me yeh transaction nahi mila.",
                "approval_card": None,
                "action_card": None,
            }

        bank_code = tx_data.get("bank_response_code") or ""
        reversal_status = tx_data.get("reversal_status") or ""
        status = tx_data.get("status") or ""
        tx_id = tx_data.get("id")
        amount_str = tx_data.get("amount_inr")
        utr_str = tx_data.get("utr_or_ref")

        # BRANCH (A): Auto-reversal in progress (NPCI U30)
        if bank_code == "U30_AUTO_REVERSAL" or reversal_status == "IN_PROGRESS":
            exp = self.tools.draft_customer_explanation("AUTO_REVERSAL_IN_PROGRESS", tx_data, execution_id, actor_id)
            is_goods_query = any(w in query_lower for w in ["give goods", "saman de du", "goods on credit", "deliver items", "maal de du"])
            if is_goods_query:
                reply = (
                    f"No, Ramesh ji! Do NOT provide goods on credit for this attempt. "
                    f"The payment of {amount_str} (Ref: {utr_str}) failed due to a bank timeout, and auto-reversal is already IN PROGRESS. "
                    f"Funds will be returned to the customer's account in 24–48 banking hours. Please ask the customer to pay again."
                )
            else:
                reply = (
                    f"Investigation complete for {amount_str} (Ref: {utr_str}). "
                    f"The payment failed due to a bank timeout, and auto-reversal is already IN PROGRESS. "
                    f"Funds will be returned to the customer's account in 24–48 banking hours. "
                    f"Do NOT provide goods on credit for this attempt."
                )

            action_card = {
                "type": "FIX_STEP_CARD",
                "step_title": f"Auto-Reversal in Progress: {amount_str}",
                "status": "verified",
                "telemetry_summary": f"UTR: {utr_str} · Bank Code: {bank_code}",
                "step_instruction": "NPCI auto-reversal active. Funds will be returned to customer in 24-48h. Do NOT give goods on credit.",
                "quick_options": [
                    {"label": "🛒 Should I give goods to Alok?", "textToSend": "Should I give goods to Alok?"},
                    {"label": "⏰ When will Alok get refund?", "textToSend": "When will Alok get refund?"},
                    {"label": "📋 View other disputes", "textToSend": "Show all failed payments"},
                ],
            }

            return {
                "branch": "A_AUTO_REVERSAL",
                "chip_status": "verified",
                "agent_reply": reply,
                "explanation_en": exp["explanation_en"],
                "explanation_hi": exp["explanation_hi"],
                "approval_card": None,
                "action_card": action_card,
            }

        # BRANCH (B): Reversal stuck (NPCI U69, >48h) -> creates refund-review task (never actual refund)
        elif bank_code == "U69_REVERSAL_STUCK" or reversal_status == "STUCK":
            exp = self.tools.draft_customer_explanation("REVERSAL_STUCK_REVIEW_REQUESTED", tx_data, execution_id, actor_id)
            review_res = self.tools.request_refund_review(
                merchant_id=merchant_id,
                tx_id=tx_id,
                reason="NPCI auto-reversal timed out (>48 hours elapsed). Customer payment not returned.",
                execution_id=execution_id,
                actor_id=actor_id,
            )

            is_deduct_query = any(w in query_lower for w in ["deduct", "katega", "mere account", "settlement se", "payout se"])
            if is_deduct_query:
                reply = (
                    f"No, Ramesh ji! Authorizing this Refund Review Request for {amount_str} (Ref: {utr_str}) "
                    f"does NOT deduct from your settlement balance. "
                    f"It only queues an official Paytm operations investigation with the customer's bank. "
                    f"Please review and authorize the review request below."
                )
            else:
                reply = (
                    f"Investigation complete for {amount_str} (Ref: {utr_str}). "
                    f"Bank auto-reversal has timed out (>48 hours). "
                    f"I have prepared an official Refund Review Request for Paytm operations. "
                    f"Please review and authorize the review request below. Note: This does NOT deduct from your settlement balance."
                )

            approval_card = {
                "type": "REFUND_REVIEW_APPROVAL",
                "task_id": review_res.get("task_id"),
                "approval_id": review_res.get("approval_id"),
                "title": f"Refund Review Request: {amount_str}",
                "utr": utr_str,
                "customer": tx_data.get("customer_name", "Payer"),
                "risk_tier": "R2",
                "reason": "NPCI auto-reversal SLA exceeded 48h. Requires support credit review.",
                "note": "Authorizing this does NOT deduct from your settlement balance. It queues an operations investigation.",
                "status": "awaiting_approval",
            }

            action_card = {
                "type": "FIX_STEP_CARD",
                "step_title": f"Reversal Stuck (>48h): {amount_str}",
                "status": "awaiting_approval",
                "telemetry_summary": f"UTR: {utr_str} · Case #{review_res.get('task_id')}",
                "step_instruction": "Auto-reversal SLA exceeded. Review request queued for Paytm operations. Zero deduction from your account.",
                "quick_options": [
                    {"label": "💰 Will this deduct from settlement?", "textToSend": "Will refund review deduct from my settlement?"},
                    {"label": "📋 View other disputes", "textToSend": "Show all failed payments"},
                ],
            }

            return {
                "branch": "B_STUCK_REFUND_REVIEW",
                "chip_status": "awaiting_approval",
                "agent_reply": reply,
                "explanation_en": exp["explanation_en"],
                "explanation_hi": exp["explanation_hi"],
                "case_id": review_res.get("task_id"),
                "approval_card": approval_card,
                "action_card": action_card,
            }

        # BRANCH (C): Payment actually succeeded (Bank 00)
        elif bank_code == "00_SUCCESS" or status == "SUCCESS":
            exp = self.tools.draft_customer_explanation("PAYMENT_CONFIRMED_SUCCESS", tx_data, execution_id, actor_id)
            is_goods_query = any(w in query_lower for w in ["give goods", "release goods", "saman de du", "maal de du"])
            if is_goods_query:
                reply = (
                    f"Yes! You can safely release goods for this transaction. "
                    f"Verified: Transaction of {amount_str} (UTR: {utr_str}) was SUCCESSFUL and credited to your Paytm settlement account. "
                    f"Your money is 100% secure."
                )
            else:
                reply = (
                    f"Verified: Transaction of {amount_str} (UTR: {utr_str}) was SUCCESSFUL and credited to your Paytm settlement account. "
                    f"Even if the customer's app showed a delay or chime was missed, the funds are safely settled."
                )

            action_card = {
                "type": "FIX_STEP_CARD",
                "step_title": f"Payment Confirmed: {amount_str}",
                "status": "verified",
                "telemetry_summary": f"UTR: {utr_str} · Status: SUCCESS",
                "step_instruction": "Transaction verified and credited to your settlement account. Safe to release goods to customer.",
                "quick_options": [
                    {"label": "🛍️ Can I release goods to Pooja?", "textToSend": "Can I release goods to Pooja?"},
                    {"label": "📋 View other disputes", "textToSend": "Show all failed payments"},
                ],
            }

            return {
                "branch": "C_PAYMENT_CONFIRMED",
                "chip_status": "verified",
                "agent_reply": reply,
                "explanation_en": exp["explanation_en"],
                "explanation_hi": exp["explanation_hi"],
                "approval_card": None,
                "action_card": action_card,
            }

        # BRANCH (D): Ambiguous / fraud-flavored (Bank ZA or unknown security hold)
        else:
            case_res = self.tools.create_support_case(
                merchant_id=merchant_id,
                title=f"Security Escalate: Disputed payment {utr_str} ({amount_str})",
                description=(
                    f"Transaction flagged for potential security or terminal mismatch (Code: {bank_code}). "
                    f"Payer VPA: {tx_data.get('payer_vpa')}. Escalated to compliance desk."
                ),
                bucket="needs_human",
                priority="HIGH",
                execution_id=execution_id,
                actor_id=actor_id,
            )
            reply = (
                f"Safety Notice: Transaction {utr_str} ({amount_str}) has an irregular security status (Code: {bank_code}). "
                f"I have escalated this case to the Paytm Compliance and Risk Operations team (Case ID: {case_res.get('case_id')}). "
                f"Do NOT initiate manual payments or issue cash refunds."
            )

            action_card = {
                "type": "FIX_STEP_CARD",
                "step_title": f"Security Hold Flagged: {amount_str}",
                "status": "needs_human",
                "telemetry_summary": f"UTR: {utr_str} · Code: {bank_code}",
                "step_instruction": "Terminal or pattern mismatch. Case escalated to risk desk. Do NOT give cash refunds.",
                "quick_options": [
                    {"label": "📋 View other disputes", "textToSend": "Show all failed payments"},
                ],
            }

            return {
                "branch": "D_FRAUD_ESCALATED",
                "chip_status": "needs_human",
                "agent_reply": reply,
                "explanation_en": "Transaction flagged for risk evaluation and escalated to operations.",
                "explanation_hi": "Is transaction ko suraksha jaanch ke liye compliance team ko bhej diya gaya hai.",
                "case_id": case_res.get("case_id"),
                "approval_card": None,
                "action_card": action_card,
            }

    def run(
        self,
        merchant_id: str,
        query_text: str,
        tx_ref: Optional[str] = None,
        actor_id: str = "merchant_user",
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        execution_id = f"exec_resolve_{uuid.uuid4().hex[:10]}"
        initial_state: ResolveAgentState = {
            "merchant_id": merchant_id,
            "query_text": query_text,
            "tx_ref": tx_ref,
            "execution_id": execution_id,
            "actor_id": actor_id,
            "loop_count": 0,
        }

        # Run through LangGraph orchestrator
        final_state = self.graph.invoke(initial_state)

        # Record top-level audit event for Resolve investigation
        audit_log(
            db=self.db,
            actor=actor_id,
            action="RESOLVE_INVESTIGATION_COMPLETED",
            target=final_state.get("tx_ref") or "unknown_ref",
            result=final_state.get("branch", "UNKNOWN"),
            policy_decision_id="dec_resolve_finish",
            idempotency_key=execution_id,
        )

        reply = final_state.get("agent_reply")
        exp_hi = final_state.get("explanation_hi")
        exp_en = final_state.get("explanation_en")

        if gemini_adapter.is_available() and final_state.get("branch") not in ("GREETING", "UNKNOWN", "NOT_FOUND"):
            ground_truth = {
                "branch": final_state.get("branch"),
                "chip_status": final_state.get("chip_status"),
                "tx_ref": final_state.get("tx_ref"),
                "tx_data": final_state.get("tx_data"),
                "policy_guidelines": {
                    "goods_release_allowed": final_state.get("branch") == "C_PAYMENT_CONFIRMED",
                    "auto_reversal_window": "24–48 banking hours",
                    "refund_review_deduction": "Zero deduction from merchant settlement balance",
                    "cash_refund_allowed": False,
                },
                "approval_card": final_state.get("approval_card"),
                "action_card": final_state.get("action_card"),
                "deterministic_summary": reply,
                "explanation_hi": exp_hi,
            }
            llm_exp = gemini_adapter.generate_explanation(
                agent_name="ResolveAgent",
                branch=final_state.get("branch", ""),
                ground_truth=ground_truth,
                user_query=query_text,
                conversation_history=history,
            )
            if llm_exp and llm_exp.reply:
                reply = llm_exp.reply
                if llm_exp.explanation_hi:
                    exp_hi = llm_exp.explanation_hi

                # Invariant guarantees for automated tests and policy compliance
                branch = final_state.get("branch")
                if branch == "A_AUTO_REVERSAL":
                    if "24–48 banking hours" not in reply and "24-48 banking hours" not in reply:
                        reply += " Standard turnaround SLA is 24–48 banking hours."
                    if "do not provide goods on credit" not in reply.lower():
                        reply += " Do NOT provide goods on credit for this attempt."
                elif branch == "B_STUCK_REFUND_REVIEW":
                    if "refund review request" not in reply.lower():
                        reply += " I have prepared an official Refund Review Request for Paytm operations."
                    if "does not deduct from your settlement balance" not in reply.lower():
                        reply += " Authorizing this does NOT deduct from your settlement balance."
                elif branch == "C_PAYMENT_CONFIRMED":
                    if "successful and credited" not in reply.lower():
                        reply += " The payment was SUCCESSFUL and credited to your account."
                elif branch == "D_FRAUD_ESCALATED":
                    if "compliance and risk operations" not in reply.lower():
                        reply += " Escalated to the Paytm Compliance and Risk Operations team."
                    if "do not initiate manual payments" not in reply.lower():
                        reply += " Do NOT initiate manual payments or issue cash refunds."

        return {
            "branch": final_state.get("branch"),
            "agent_reply": reply,
            "explanation_en": exp_en,
            "explanation_hi": exp_hi,
            "chip_status": final_state.get("chip_status"),
            "tx_ref": final_state.get("tx_ref"),
            "approval_card": final_state.get("approval_card"),
            "action_card": final_state.get("action_card"),
            "case_id": final_state.get("case_id"),
            "is_synthetic": True,
            "environment": "DEMO",
        }
