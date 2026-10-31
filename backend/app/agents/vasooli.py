from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any, Dict, List, Optional, TypedDict
import uuid
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.db.models import Customer, Receivable, ActionApproval, ApprovalDecision, Task, TaskBucket
from app.tools.vasooli import VasooliTools
from app.adapters.speech import get_speech_adapter
from app.adapters.gemini import gemini_adapter


class VasooliAgentState(TypedDict):
    merchant_id: str
    query_text: str
    actor_id: str
    execution_id: str
    action_type: str  # RECORD_UDHAAR | DRAFT_REMINDER | APPROVE_AND_SEND | NEGOTIATE_SPLIT | RECORD_PAYMENT | PARSE_QUERY | CUSTOMER_INQUIRY
    receivable_id: Optional[str]
    customer_id: Optional[str]
    customer_name: Optional[str]
    customer_phone: Optional[str]
    amount_paise: Optional[int]
    notes: Optional[str]
    custom_message: Optional[str]
    split_amounts: Optional[List[int]]
    approval_id: Optional[str]
    is_authoritative_payment: Optional[bool]
    payment_reference: Optional[str]
    # Agent Output
    agent_reply: str
    explanation_hi: Optional[str]
    chip_status: str  # verified | executed | pending | awaiting_approval | needs_human
    approval_card: Optional[Dict[str, Any]]
    action_card: Optional[Dict[str, Any]]
    vasooli_card: Optional[Dict[str, Any]]
    refusal_reason: Optional[str]
    error: Optional[str]


class VasooliAgent:
    """
    Consensual Receivable Reminders Agent (Vasooli).
    Hard Boundaries:
    1. Local merchant udhaar only — NEVER coercive loan-debt collection.
    2. Zero harassment: Banned-phrases enforcement blocks threats and shaming.
    3. Mandatory communication permission check before outreach.
    4. Immediate pause on disputed ledger entries.
    5. Immediate auto-stop upon authoritative settlement confirmation.
    """

    def __init__(self, db: Session):
        self.db = db
        self.tools = VasooliTools(db=db)
        self.speech_adapter = get_speech_adapter()
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(VasooliAgentState)

        builder.add_node("entry_analyzer", self._node_entry_analyzer)
        builder.add_node("udhaar_recorder", self._node_udhaar_recorder)
        builder.add_node("reminder_drafter", self._node_reminder_drafter)
        builder.add_node("reminder_sender", self._node_reminder_sender)
        builder.add_node("split_negotiator", self._node_split_negotiator)
        builder.add_node("payment_recorder", self._node_payment_recorder)

        def route_dispatcher(state: VasooliAgentState):
            act = state.get("action_type", "PARSE_QUERY")
            if act == "RECORD_UDHAAR":
                return "udhaar_recorder"
            if act == "DRAFT_REMINDER":
                return "reminder_drafter"
            if act == "APPROVE_AND_SEND":
                return "reminder_sender"
            if act == "NEGOTIATE_SPLIT":
                return "split_negotiator"
            if act == "RECORD_PAYMENT":
                return "payment_recorder"
            return "entry_analyzer"

        builder.set_conditional_entry_point(
            route_dispatcher,
            {
                "entry_analyzer": "entry_analyzer",
                "udhaar_recorder": "udhaar_recorder",
                "reminder_drafter": "reminder_drafter",
                "reminder_sender": "reminder_sender",
                "split_negotiator": "split_negotiator",
                "payment_recorder": "payment_recorder",
            },
        )

        builder.add_edge("entry_analyzer", END)
        builder.add_edge("udhaar_recorder", END)
        builder.add_edge("reminder_drafter", END)
        builder.add_edge("reminder_sender", END)
        builder.add_edge("split_negotiator", END)
        builder.add_edge("payment_recorder", END)

        return builder.compile()

    @staticmethod
    def _extract_amount(text: str) -> Optional[int]:
        """Extracts monetary amount from natural utterance in paise, guarding against quantities like '5kg'."""
        t = text.lower()
        # 1. Preceded by currency symbol or word: rs 300, ₹500, inr 200, rupees 100
        m = re.search(r"(?:₹|rs\.?|inr|rupees)\s*(\d+)", t)
        if m:
            val = int(m.group(1))
            return val * 100 if val < 100000 else val
        # 2. Followed by currency word: 300 rs, 300 rupees, 500 inr, 300 paise
        m = re.search(r"(\d+)\s*(?:rs\.?|rupees|inr|paise)", t)
        if m:
            val = int(m.group(1))
            return val * 100 if val < 100000 else val
        # 3. Preceded by udhaar/of/worth/for: udhaar of 250, credit 500, worth 400
        m = re.search(r"(?:udhaar|udhar|credit|worth|for)\s+(?:of\s+)?(?:rs\.?|₹)?\s*(\d+)", t)
        if m:
            val = int(m.group(1))
            return val * 100 if val < 100000 else val
        return None

    @staticmethod
    def _match_customer(customers: List[Customer], query: str) -> Optional[Customer]:
        """Matches customer by exact name or first/last name tokens."""
        q = query.lower()
        # 1. Exact full name match
        for c in customers:
            if c.name and c.name.lower() in q:
                return c

        # 2. Token match for first/last name with word boundaries & Hindi suffixes
        for c in customers:
            if not c.name:
                continue
            tokens = [t.lower() for t in re.split(r"[\s_]+", c.name.strip()) if len(t) >= 3]
            for token in tokens:
                pattern = rf"\b{re.escape(token)}(?:ji|bhai|saheb|ko|ka|ki|ke)?\b"
                if re.search(pattern, q):
                    return c
        return None

    def _node_entry_analyzer(self, state: VasooliAgentState) -> Dict[str, Any]:
        """Parses plain language merchant udhaar recording, inquiry, or reminder requests."""
        query = state.get("query_text", "").strip()
        merchant_id = state.get("merchant_id", "mer_sharma_kirana")
        q_lower = query.lower()

        # 1. Check for prohibited coercive language in merchant input
        banned = self.tools.vasooli_adapter.check_banned_phrases(query) if self.tools.vasooli_adapter else None
        if banned:
            return {
                "chip_status": "needs_human",
                "action_type": "NEEDS_HUMAN",
                "agent_reply": (
                    f"Action Blocked by Policy: Prohibited coercive term '{banned}' detected. "
                    "Vasooli is a respectful store credit helper and strictly prohibits legal threats, police action, or public shaming."
                ),
                "error": "R4_COERCIVE_LANGUAGE_BLOCKED",
            }

        # Detect customer name from existing customers
        customers = self.db.query(Customer).filter(Customer.merchant_id == merchant_id).all()
        matched_cust = self._match_customer(customers, query)

        # 2. Check for Split Installment Negotiation Intent
        is_split_intent = any(w in q_lower for w in ["split", "installment", "kist", "kiston", "banto", "baanto", "hisson"])
        if is_split_intent and matched_cust:
            rec = (
                self.db.query(Receivable)
                .filter(
                    Receivable.customer_id == matched_cust.id,
                    Receivable.merchant_id == merchant_id,
                    Receivable.status.in_(["PENDING", "PARTIALLY_PAID"]),
                )
                .order_by(Receivable.created_at.desc())
                .first()
            )
            if rec:
                num_splits = 3 if rec.amount >= 100000 else 2
                per_split = rec.amount // num_splits
                remainder = rec.amount - (per_split * num_splits)
                splits = [per_split] * num_splits
                splits[0] += remainder
                prop = self.tools.vasooli_adapter.negotiate_installment_split(
                    receivable_id=rec.id,
                    split_amounts_paise=splits,
                    actor_id=state.get("actor_id", "merchant_user"),
                )
                split_card = {
                    "type": "VASOOLI_SPLIT_CARD",
                    "approval_id": prop.approval_id,
                    "receivable_id": rec.id,
                    "customer_name": matched_cust.name,
                    "total_amount_formatted": f"₹{prop.total_amount_paise / 100:,.2f}",
                    "splits": prop.splits,
                    "proposal_summary": prop.proposal_summary,
                    "status": "AWAITING_APPROVAL",
                }
                reply = (
                    f"I have prepared a {len(splits)}-part installment proposal for {matched_cust.name} "
                    f"totaling ₹{prop.total_amount_paise / 100:,.2f} ({prop.proposal_summary}). "
                    f"Please review the approval card below to confirm."
                )
                return {
                    "chip_status": "awaiting_approval",
                    "action_type": "NEGOTIATE_SPLIT",
                    "agent_reply": reply,
                    "approval_card": split_card,
                    "action_card": split_card,
                    "vasooli_card": split_card,
                    "receivable_id": rec.id,
                    "customer_name": matched_cust.name,
                }

        # 3. Check for Payment / Settlement Intent
        is_payment_intent = any(w in q_lower for w in ["paid", "chukaya", "de diya", "de diye", "settle", "settled", "bhugtan ho gaya", "mil gaya"])
        if is_payment_intent and matched_cust:
            rec = (
                self.db.query(Receivable)
                .filter(
                    Receivable.customer_id == matched_cust.id,
                    Receivable.merchant_id == merchant_id,
                )
                .order_by(Receivable.created_at.desc())
                .first()
            )
            if rec and rec.status != "PAID":
                pay_res = self.tools.record_payment_status(
                    receivable_id=rec.id,
                    paid_amount_paise=rec.amount,
                    is_authoritative=True,
                    actor_id=state.get("actor_id", "merchant_user"),
                )
                return {
                    "chip_status": "verified",
                    "action_type": "RECORD_PAYMENT",
                    "agent_reply": f"Payment of ₹{rec.amount / 100:,.2f} from {matched_cust.name} verified and recorded. Dues cleared, reminders auto-stopped.",
                    "action_card": pay_res,
                    "approval_card": None,
                    "vasooli_card": None,
                    "receivable_id": rec.id,
                    "customer_name": matched_cust.name,
                }

        # 4. Check for Free-text Udhaar Recording with amount: "Vikram Singh bought 5kg aata for 250 rs on udhaar"
        extracted_amount_paise = self._extract_amount(query)
        is_record_intent = any(w in q_lower for w in ["bought", "purchase", "record", "add"]) or (
            any(w in q_lower for w in ["udhaar", "credit", "khata"])
            and any(w in q_lower for w in ["liya", "diya", "of", "worth", "bought", "add", "daal", "likho", "likh"])
        )

        if is_record_intent and extracted_amount_paise:
            amount_paise = extracted_amount_paise

            target_cust = matched_cust
            if not target_cust:
                name_match = re.search(r"(?:for|to|customer)\s+([A-Za-z\s]+?)(?:\s+bought|\s+for|\s+on|\s*$)", query, re.IGNORECASE)
                cust_name = name_match.group(1).strip() if name_match else "Customer"
                target_cust = Customer(
                    tenant_id="tenant_paytm_demo",
                    merchant_id=merchant_id,
                    name=cust_name,
                    phone="+919800000000",
                    notes="Recorded via Saathi voice/chat",
                    contact_permission=True,
                    permission_status="ALLOWED",
                    is_synthetic=True,
                    environment="DEMO",
                )
                self.db.add(target_cust)
                self.db.flush()

            now = datetime.now(timezone.utc)
            rec = Receivable(
                tenant_id="tenant_paytm_demo",
                merchant_id=merchant_id,
                customer_id=target_cust.id,
                amount=amount_paise,
                due_date=now + timedelta(days=7),
                status="PENDING",
                notes=f"Recorded via Saathi chat: {query}",
                is_disputed=False,
                reminder_count=0,
                settlement_verification_status="UNSETTLED",
                payment_link_url=f"https://paytm.demo/pay/rec_{uuid.uuid4().hex[:8]}",
                is_synthetic=True,
                environment="DEMO",
            )
            self.db.add(rec)
            self.db.commit()

            draft = self.tools.vasooli_adapter.draft_payment_reminder(rec.id)
            approval_card = {
                "type": "VASOOLI_REMINDER_CARD",
                "approval_id": f"appr_rec_{rec.id}",
                "receivable_id": rec.id,
                "customer_name": target_cust.name,
                "customer_phone": target_cust.phone,
                "amount_formatted": draft.amount_formatted,
                "draft_message_hi": draft.draft_message_hi,
                "payment_link_url": draft.payment_link_url,
                "status": "AWAITING_APPROVAL",
                "can_send": draft.can_send,
                "refusal_reason": draft.refusal_reason,
            }
            reply = (
                f"Recorded store credit (Udhaar) of {draft.amount_formatted} for {target_cust.name}. "
                f"I have drafted a respectful payment reminder with a secure UPI link below. "
                f"Please review and approve before sending."
            )
            return {
                "chip_status": "awaiting_approval",
                "action_type": "RECORD_UDHAAR",
                "agent_reply": reply,
                "approval_card": approval_card,
                "action_card": approval_card,
                "vasooli_card": approval_card,
                "receivable_id": rec.id,
                "customer_name": target_cust.name,
            }

        # 5. Check if Merchant asks to Remind a Specific Customer: e.g. "Vikram ko polite reminder bhejo udhari chukane k lie"
        is_reminder_intent = any(w in q_lower for w in ["remind", "reminder", "bhejo", "bhejna", "message", "suchna", "chukane", "yaad dilao"])
        if is_reminder_intent and matched_cust:
            rec = (
                self.db.query(Receivable)
                .filter(
                    Receivable.customer_id == matched_cust.id,
                    Receivable.merchant_id == merchant_id,
                )
                .order_by(Receivable.created_at.desc())
                .first()
            )
            if rec:
                draft = self.tools.vasooli_adapter.draft_payment_reminder(rec.id)
                if not draft.can_send:
                    refusal_card = {
                        "type": "VASOOLI_REFUSAL_CARD",
                        "receivable_id": rec.id,
                        "customer_name": matched_cust.name,
                        "amount_formatted": draft.amount_formatted,
                        "can_send": False,
                        "status": "REFUSED",
                        "refusal_reason": draft.refusal_reason,
                    }
                    return {
                        "chip_status": "needs_human",
                        "action_type": "DRAFT_REMINDER",
                        "agent_reply": f"Outreach Refused by Policy: {draft.refusal_reason}",
                        "refusal_reason": draft.refusal_reason,
                        "approval_card": refusal_card,
                        "action_card": refusal_card,
                        "vasooli_card": refusal_card,
                        "receivable_id": rec.id,
                        "customer_name": matched_cust.name,
                    }

                approval_card = {
                    "type": "VASOOLI_REMINDER_CARD",
                    "approval_id": f"appr_rec_{rec.id}",
                    "receivable_id": rec.id,
                    "customer_name": matched_cust.name,
                    "customer_phone": matched_cust.phone,
                    "amount_formatted": draft.amount_formatted,
                    "draft_message_hi": draft.draft_message_hi,
                    "payment_link_url": draft.payment_link_url,
                    "status": "AWAITING_APPROVAL",
                    "can_send": True,
                    "reminder_count": rec.reminder_count,
                }
                reply = (
                    f"I have drafted a respectful payment reminder for {matched_cust.name} ({draft.amount_formatted}) "
                    f"with a secure Paytm UPI payment link. Please review the message below and tap 'Approve & Send Reminder' to send it."
                )
                return {
                    "chip_status": "awaiting_approval",
                    "action_type": "DRAFT_REMINDER",
                    "agent_reply": reply,
                    "approval_card": approval_card,
                    "action_card": approval_card,
                    "vasooli_card": approval_card,
                    "receivable_id": rec.id,
                    "customer_name": matched_cust.name,
                }

        # 6. Specific Customer Balance / Khata Inquiry: e.g. "Vikram ka udhare kitna hai ??" or "Manish ka udhar batao"
        if matched_cust:
            recs = (
                self.db.query(Receivable)
                .filter(
                    Receivable.customer_id == matched_cust.id,
                    Receivable.merchant_id == merchant_id,
                )
                .order_by(Receivable.created_at.desc())
                .all()
            )
            if not recs:
                return {
                    "chip_status": "verified",
                    "action_type": "CUSTOMER_INQUIRY",
                    "agent_reply": f"No active store credit record found for {matched_cust.name}.",
                    "approval_card": None,
                    "action_card": None,
                    "vasooli_card": None,
                    "customer_name": matched_cust.name,
                }

            active_recs = [r for r in recs if r.status in ["PENDING", "PARTIALLY_PAID", "DISPUTED"]]
            if not active_recs:
                latest_paid = recs[0]
                amount_fmt = f"₹{latest_paid.amount / 100:,.2f}"
                reply = (
                    f"Namaste! {matched_cust.name} has completely cleared all dues. "
                    f"The previous balance of {amount_fmt} for '{latest_paid.notes or 'store credit'}' was settled in full via UPI today."
                )
                return {
                    "chip_status": "verified",
                    "action_type": "CUSTOMER_INQUIRY",
                    "agent_reply": reply,
                    "approval_card": None,
                    "action_card": None,
                    "vasooli_card": None,
                    "customer_name": matched_cust.name,
                    "receivable_id": latest_paid.id,
                }

            # Choose primary receivable (prefer non-disputed with consensual permissions, or largest)
            rec = next((r for r in active_recs if not r.is_disputed and matched_cust.contact_permission), active_recs[0])
            total_pending_paise = sum(r.amount - r.paid_amount for r in active_recs)
            amount_fmt = f"₹{total_pending_paise / 100:,.2f}"
            all_notes = "; ".join(r.notes for r in active_recs if r.notes) or "store credit"

            if rec.is_disputed:
                refusal_card = {
                    "type": "VASOOLI_REFUSAL_CARD",
                    "receivable_id": rec.id,
                    "customer_name": matched_cust.name,
                    "amount_formatted": amount_fmt,
                    "can_send": False,
                    "status": "DISPUTED",
                    "refusal_reason": f"Dispute hold: {rec.dispute_reason or 'Item discrepancy reported'}. Digital reminders suspended.",
                }
                reply = (
                    f"Namaste! {matched_cust.name} has a pending balance of {amount_fmt} for '{all_notes}'. "
                    f"However, this account is currently flagged as DISPUTED ({rec.dispute_reason or 'delivery discrepancy reported'}). "
                    f"Under Paytm Saathi's respectful policy, automated reminders are paused to preserve trust. "
                    f"We recommend checking the delivered items in person with the customer to resolve the discrepancy."
                )
                return {
                    "chip_status": "needs_human",
                    "action_type": "CUSTOMER_INQUIRY",
                    "agent_reply": reply,
                    "approval_card": refusal_card,
                    "action_card": refusal_card,
                    "vasooli_card": refusal_card,
                    "refusal_reason": rec.dispute_reason,
                    "customer_name": matched_cust.name,
                    "receivable_id": rec.id,
                }

            if not matched_cust.contact_permission or matched_cust.permission_status != "ALLOWED":
                refusal_card = {
                    "type": "VASOOLI_REFUSAL_CARD",
                    "receivable_id": rec.id,
                    "customer_name": matched_cust.name,
                    "amount_formatted": amount_fmt,
                    "can_send": False,
                    "status": "REVOKED",
                    "refusal_reason": "Customer opted out of digital notifications. In-store settlement only.",
                }
                reply = (
                    f"Namaste! {matched_cust.name} has a pending balance of {amount_fmt} for '{all_notes}'. "
                    f"Note: {matched_cust.name} has opted out of digital reminders (Revoked Consent). "
                    f"Under our zero-harassment policy, automated SMS/WhatsApp reminders cannot be sent. "
                    f"Please collect payment in person when they next visit your store."
                )
                return {
                    "chip_status": "needs_human",
                    "action_type": "CUSTOMER_INQUIRY",
                    "agent_reply": reply,
                    "approval_card": refusal_card,
                    "action_card": refusal_card,
                    "vasooli_card": refusal_card,
                    "refusal_reason": "Communication permission revoked",
                    "customer_name": matched_cust.name,
                    "receivable_id": rec.id,
                }

            # Active, consensual customer (e.g. Vikram Singh or Amit Shukla)
            draft = self.tools.vasooli_adapter.draft_payment_reminder(rec.id)
            approval_card = {
                "type": "VASOOLI_REMINDER_CARD",
                "approval_id": f"appr_rec_{rec.id}",
                "receivable_id": rec.id,
                "customer_name": matched_cust.name,
                "customer_phone": matched_cust.phone,
                "amount_formatted": amount_fmt,
                "draft_message_hi": draft.draft_message_hi,
                "payment_link_url": draft.payment_link_url,
                "status": "AWAITING_APPROVAL",
                "can_send": True,
                "reminder_count": rec.reminder_count,
            }
            reply = (
                f"Namaste! {matched_cust.name} owes {amount_fmt} for '{all_notes}'. "
                f"Contact permission is active (ALLOWED) and the account is in good standing. "
                f"I have prepared a respectful reminder with a secure Paytm UPI payment link below. "
                f"Tap 'Approve & Send Reminder' to send it, or tell me to split the payment or record payment."
            )
            return {
                "chip_status": "awaiting_approval",
                "action_type": "CUSTOMER_INQUIRY",
                "agent_reply": reply,
                "approval_card": approval_card,
                "action_card": approval_card,
                "vasooli_card": approval_card,
                "customer_name": matched_cust.name,
                "receivable_id": rec.id,
            }

        # 7. Store-wide All Udhaar / Top Debtors / General Khata Inquiry: e.g. "give me all details about my udhar", "who owes the most udhar?"
        summary = self.tools.vasooli_adapter.get_vasooli_summary(merchant_id)
        all_recs = (
            self.db.query(Receivable)
            .filter(Receivable.merchant_id == merchant_id)
            .order_by(Receivable.amount.desc())
            .all()
        )
        active_recs = [r for r in all_recs if r.status in ["PENDING", "PARTIALLY_PAID", "DISPUTED"]]
        active_recs.sort(key=lambda r: (r.amount - r.paid_amount), reverse=True)

        customers_list = []
        top_debtor = None
        for idx, r in enumerate(active_recs):
            c = r.customer
            rem_amount_fmt = f"₹{(r.amount - r.paid_amount) / 100:,.2f}"

            if r.is_disputed:
                status_tag = "DISPUTED"
                rec_action = f"Dispute hold ({r.dispute_reason or 'discrepancy'}). Reminders paused; resolve in store."
                q_label = "⚖️ Check Dispute"
                q_query = f"{c.name} ka udhar dispute kya hai?"
            elif not c.contact_permission or c.permission_status != "ALLOWED":
                status_tag = "REVOKED"
                rec_action = "Customer opted out of digital reminders. In-store collection only."
                q_label = "🏪 In-Store Cash"
                q_query = f"{c.name} ka hisab dikhao"
            elif (r.amount - r.paid_amount) >= 100000:
                status_tag = "SPLIT_CANDIDATE"
                rec_action = "High balance. Suggest 3-month split plan (₹500/mo) or gentle reminder."
                q_label = f"➗ Split {c.name.split()[0]}"
                q_query = f"{c.name} ka split plan banao"
            else:
                status_tag = "ALLOWED"
                rec_action = "Consensual reminder ready with UPI payment link."
                q_label = f"📲 Remind {c.name.split()[0]}"
                q_query = f"{c.name} ko polite reminder bhejo udhari chukane k lie"

            entry = {
                "name": c.name,
                "receivable_id": r.id,
                "amount_formatted": rem_amount_fmt,
                "amount_paise": r.amount - r.paid_amount,
                "status": status_tag,
                "consent_status": c.permission_status,
                "is_disputed": r.is_disputed,
                "notes": r.notes or "Store credit purchase",
                "recommended_action": rec_action,
                "quick_action_label": q_label,
                "quick_action_query": q_query,
            }
            customers_list.append(entry)
            if idx == 0:
                top_debtor = {
                    "name": c.name,
                    "amount_formatted": rem_amount_fmt,
                    "recommendation": f"Highest balance ({rem_amount_fmt}). {rec_action}",
                }

        ledger_card = {
            "type": "VASOOLI_LEDGER_CARD",
            "title": "Store Credit Ledger (Vasooli Khata)",
            "status": "verified",
            "total_outstanding_formatted": summary.total_outstanding_formatted,
            "total_recovered_formatted": summary.total_recovered_formatted,
            "total_receivables_count": len(active_recs),
            "top_debtor": top_debtor,
            "customers": customers_list,
            "quick_options": [
                {"label": "📲 Remind Vikram (₹850)", "textToSend": "Vikram ko polite reminder bhejo udhari chukane k lie"},
                {"label": "➗ Split Amit Plan (₹1,500)", "textToSend": "Amit Shukla ka split plan banao"},
                {"label": "⚖️ Check Manish Dispute", "textToSend": "Manish Gupta ka udhar dispute kya hai?"},
                {"label": "➕ Record New Udhaar", "textToSend": "Record udhaar of 250 for Suresh"},
            ],
        }

        top_text = f"Top Debtor: **{top_debtor['name']}** owes the most ({top_debtor['amount_formatted']})." if top_debtor else ""
        breakdown_lines = []
        for c_item in customers_list:
            breakdown_lines.append(f"• **{c_item['name']}**: {c_item['amount_formatted']} ({c_item['notes']}) — *{c_item['recommended_action']}*")

        reply = (
            f"Namaste! Here is the complete breakdown of your store credit (Udhaar):\n\n"
            f"📊 **Overview**: Total Outstanding: **{summary.total_outstanding_formatted}** across {len(active_recs)} customers. "
            f"Recovered Today: **{summary.total_recovered_formatted}**.\n\n"
            f"👑 {top_text}\n\n"
            f"**Customer Balances & Recommended Next Steps**:\n"
            + "\n".join(breakdown_lines) +
            f"\n\n💡 *Tip: You can tap any quick action below to send a gentle reminder, propose an installment split, or check dispute details.*"
        )

        return {
            "chip_status": "verified",
            "action_type": "PARSE_QUERY",
            "agent_reply": reply,
            "action_card": ledger_card,
            "approval_card": None,
            "vasooli_card": None,
        }

    def _node_udhaar_recorder(self, state: VasooliAgentState) -> Dict[str, Any]:
        merchant_id = state.get("merchant_id", "mer_sharma_kirana")
        cust_name = state.get("customer_name", "Customer")
        amount = state.get("amount_paise", 0)
        notes = state.get("notes", "Store credit purchase")

        # Find or create customer
        cust = (
            self.db.query(Customer)
            .filter(Customer.merchant_id == merchant_id, Customer.name == cust_name)
            .first()
        )
        if not cust:
            cust = Customer(
                tenant_id="tenant_paytm_demo",
                merchant_id=merchant_id,
                name=cust_name,
                phone=state.get("customer_phone", "+919811122233"),
                notes="Recorded via Saathi",
                contact_permission=True,
                permission_status="ALLOWED",
                is_synthetic=True,
                environment="DEMO",
            )
            self.db.add(cust)
            self.db.flush()

        now = datetime.now(timezone.utc)
        rec = Receivable(
            tenant_id="tenant_paytm_demo",
            merchant_id=merchant_id,
            customer_id=cust.id,
            amount=amount,
            due_date=now + timedelta(days=7),
            status="PENDING",
            notes=notes,
            is_disputed=False,
            reminder_count=0,
            settlement_verification_status="UNSETTLED",
            payment_link_url=f"https://paytm.demo/pay/rec_{uuid.uuid4().hex[:8]}",
            is_synthetic=True,
            environment="DEMO",
        )
        self.db.add(rec)
        self.db.commit()

        draft = self.tools.vasooli_adapter.draft_payment_reminder(rec.id)

        card = {
            "approval_id": f"appr_rec_{rec.id}",
            "receivable_id": rec.id,
            "customer_name": cust.name,
            "customer_phone": cust.phone,
            "amount_formatted": draft.amount_formatted,
            "draft_message_hi": draft.draft_message_hi,
            "payment_link_url": draft.payment_link_url,
            "status": "AWAITING_APPROVAL",
            "can_send": draft.can_send,
            "refusal_reason": draft.refusal_reason,
        }

        return {
            "chip_status": "awaiting_approval",
            "agent_reply": f"Recorded udhaar of {draft.amount_formatted} for {cust.name}. Approval card ready.",
            "approval_card": card,
            "action_card": card,
            "receivable_id": rec.id,
        }

    def _node_reminder_drafter(self, state: VasooliAgentState) -> Dict[str, Any]:
        receivable_id = state.get("receivable_id")
        custom_note = state.get("custom_message")

        res = self.tools.draft_payment_reminder(receivable_id, custom_note)
        if not res.get("drafted"):
            return {
                "chip_status": "needs_human",
                "agent_reply": f"Cannot Draft Reminder: {res.get('reason')}",
                "error": res.get("error"),
                "refusal_reason": res.get("reason"),
            }

        card = {
            "approval_id": f"appr_rec_{receivable_id}",
            "receivable_id": receivable_id,
            "customer_name": res["customer_name"],
            "customer_phone": res["customer_phone"],
            "amount_formatted": res["amount_formatted"],
            "draft_message_hi": res["draft_message_hi"],
            "payment_link_url": res["payment_link_url"],
            "status": "AWAITING_APPROVAL",
            "can_send": res["can_send"],
            "refusal_reason": res.get("refusal_reason"),
            "reminder_count": res["reminder_count"],
        }

        reply = (
            f"Drafted polite reminder for {res['customer_name']} ({res['amount_formatted']}). "
            if res["can_send"]
            else f"Outreach Refused: {res.get('refusal_reason')}"
        )

        return {
            "chip_status": "awaiting_approval" if res["can_send"] else "needs_human",
            "agent_reply": reply,
            "approval_card": card,
            "action_card": card,
            "refusal_reason": res.get("refusal_reason"),
        }

    def _node_reminder_sender(self, state: VasooliAgentState) -> Dict[str, Any]:
        receivable_id = state.get("receivable_id")
        approval_id = state.get("approval_id")
        actor_id = state.get("actor_id", "merchant_user")
        execution_id = state.get("execution_id", f"exec_send_{uuid.uuid4().hex[:8]}")

        res = self.tools.send_authorized_reminder(
            receivable_id=receivable_id,
            approval_id=approval_id,
            actor_id=actor_id,
            execution_id=execution_id,
        )

        if not res.get("sent"):
            return {
                "chip_status": "needs_human",
                "agent_reply": f"Reminder Delivery Failed: {res.get('reason')}",
                "error": res.get("error"),
                "refusal_reason": res.get("reason"),
            }

        reply = (
            f"Respectful reminder delivered to {res['recipient_phone']} via SMS/WhatsApp. "
            f"Attempt {res['reminder_count']}/3 recorded. Audit ID: {res['audit_event_id']}."
        )

        return {
            "chip_status": "executed",
            "agent_reply": reply,
            "action_card": res,
        }

    def _node_split_negotiator(self, state: VasooliAgentState) -> Dict[str, Any]:
        receivable_id = state.get("receivable_id")
        splits = state.get("split_amounts", [])
        actor_id = state.get("actor_id", "merchant_user")

        try:
            prop = self.tools.vasooli_adapter.negotiate_installment_split(
                receivable_id=receivable_id,
                split_amounts_paise=splits,
                actor_id=actor_id,
            )
            card = {
                "approval_id": prop.approval_id,
                "receivable_id": receivable_id,
                "total_amount_formatted": f"₹{prop.total_amount_paise / 100:,.2f}",
                "splits": prop.splits,
                "proposal_summary": prop.proposal_summary,
                "status": "AWAITING_APPROVAL",
            }
            return {
                "chip_status": "awaiting_approval",
                "agent_reply": f"Installment Split Negotiated: {prop.proposal_summary}. Merchant approval required.",
                "approval_card": card,
                "action_card": card,
            }
        except Exception as e:
            return {
                "chip_status": "needs_human",
                "agent_reply": f"Split Negotiation Error: {str(e)}",
                "error": str(e),
            }

    def _node_payment_recorder(self, state: VasooliAgentState) -> Dict[str, Any]:
        receivable_id = state.get("receivable_id")
        amount = state.get("amount_paise", 0)
        ref = state.get("payment_reference", f"PAYTM_PAY_{uuid.uuid4().hex[:8]}")
        is_auth = state.get("is_authoritative_payment", True)
        actor_id = state.get("actor_id", "system")

        res = self.tools.record_payment_status(
            receivable_id=receivable_id,
            paid_amount_paise=amount,
            payment_reference=ref,
            is_authoritative=is_auth,
            actor_id=actor_id,
        )

        reply = (
            f"Payment Verified! {res['message']} Reminders auto-stopped."
            if res.get("verified")
            else f"Payment Noted: {res['message']}"
        )

        return {
            "chip_status": "verified" if res.get("verified") else "pending",
            "agent_reply": reply,
            "action_card": res,
        }

    def run(
        self,
        query_text: str = "",
        merchant_id: str = "mer_sharma_kirana",
        action_type: str = "PARSE_QUERY",
        receivable_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
        amount_paise: Optional[int] = None,
        notes: Optional[str] = None,
        custom_message: Optional[str] = None,
        split_amounts: Optional[List[int]] = None,
        approval_id: Optional[str] = None,
        is_authoritative_payment: Optional[bool] = None,
        payment_reference: Optional[str] = None,
        actor_id: str = "merchant_user",
    ) -> Dict[str, Any]:
        initial_state: VasooliAgentState = {
            "merchant_id": merchant_id,
            "query_text": query_text,
            "actor_id": actor_id,
            "execution_id": f"exec_vasooli_{uuid.uuid4().hex[:8]}",
            "action_type": action_type,
            "receivable_id": receivable_id,
            "customer_id": None,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "amount_paise": amount_paise,
            "notes": notes,
            "custom_message": custom_message,
            "split_amounts": split_amounts,
            "approval_id": approval_id,
            "is_authoritative_payment": is_authoritative_payment,
            "payment_reference": payment_reference,
            "agent_reply": "",
            "explanation_hi": None,
            "chip_status": "pending",
            "approval_card": None,
            "action_card": None,
            "vasooli_card": None,
            "refusal_reason": None,
            "error": None,
        }
        res = self.graph.invoke(initial_state)
        reply = res.get("agent_reply")

        # Ensure cards are cross-populated for frontend consistency
        card = res.get("vasooli_card") or res.get("approval_card") or res.get("action_card")
        if card:
            if not res.get("vasooli_card"):
                res["vasooli_card"] = card
            if not res.get("action_card"):
                res["action_card"] = card
            if not res.get("approval_card") and card.get("status") == "AWAITING_APPROVAL":
                res["approval_card"] = card

        if gemini_adapter.is_available() and not res.get("refusal_reason") and not res.get("error"):
            action_c = res.get("action_card") or {}
            ground_truth = {
                "customer_name": res.get("customer_name"),
                "amount_paise": res.get("amount_paise"),
                "action_type": res.get("action_type"),
                "chip_status": res.get("chip_status"),
                "total_outstanding": action_c.get("total_outstanding_formatted"),
                "total_recovered_today": action_c.get("total_recovered_formatted"),
                "top_debtor": action_c.get("top_debtor"),
                "customers_breakdown": action_c.get("customers"),
                "action_card": res.get("action_card"),
                "approval_card": res.get("approval_card"),
                "vasooli_card": res.get("vasooli_card"),
                "deterministic_reply": reply,
            }
            llm_exp = gemini_adapter.generate_explanation(
                agent_name="VasooliAgent",
                branch=res.get("action_type", ""),
                ground_truth=ground_truth,
                user_query=query_text,
            )
            if llm_exp and llm_exp.reply:
                if reply and "Recorded store credit (Udhaar)" in reply:
                    res["agent_reply"] = f"{reply}\n\n{llm_exp.reply}"
                else:
                    res["agent_reply"] = llm_exp.reply
                if llm_exp.explanation_hi:
                    res["explanation_hi"] = llm_exp.explanation_hi
        return res
