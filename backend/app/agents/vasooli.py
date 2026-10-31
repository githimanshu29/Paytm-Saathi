from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any, Dict, List, Optional, TypedDict
import uuid
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.db.models import Customer, Receivable, ActionApproval, ApprovalDecision, Task, TaskBucket
from app.tools.vasooli import VasooliTools
from app.adapters.speech import MockSpeechAdapter


class VasooliAgentState(TypedDict):
    merchant_id: str
    query_text: str
    actor_id: str
    execution_id: str
    action_type: str  # RECORD_UDHAAR | DRAFT_REMINDER | APPROVE_AND_SEND | NEGOTIATE_SPLIT | RECORD_PAYMENT
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
    chip_status: str  # verified | executed | pending | awaiting_approval | needs_human
    approval_card: Optional[Dict[str, Any]]
    action_card: Optional[Dict[str, Any]]
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
        self.speech_adapter = MockSpeechAdapter()
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

    def _node_entry_analyzer(self, state: VasooliAgentState) -> Dict[str, Any]:
        """Parses plain language merchant udhaar recording or reminder requests."""
        query = state.get("query_text", "").strip()
        merchant_id = state.get("merchant_id", "mer_sharma_kirana")
        q_lower = query.lower()

        # Check for prohibited coercive language in merchant input
        banned = self.tools.vasooli_adapter.check_banned_phrases(query) if self.tools.vasooli_adapter else None
        if banned:
            return {
                "chip_status": "needs_human",
                "agent_reply": (
                    f"Action Blocked by Policy: Prohibited coercive term '{banned}' detected. "
                    "Vasooli is a respectful store credit helper and strictly prohibits legal threats, police action, or public shaming."
                ),
                "error": "R4_COERCIVE_LANGUAGE_BLOCKED",
            }

        # Check for free-text udhaar recording: "Vikram Singh bought 5kg aata for 250 rs on udhaar"
        # Or: "Record udhaar of 500 for Suresh"
        amount_match = re.search(r"(?:₹|rs\.?|inr)?\s*(\d+)(?:\s*(?:rs|rupees|paise))?", q_lower)
        is_record_intent = any(w in q_lower for w in ["udhaar", "credit", "khata", "bought", "purchase", "record", "add"])

        # Detect customer name from existing customers
        customers = self.db.query(Customer).filter(Customer.merchant_id == merchant_id).all()
        matched_cust = None
        for c in customers:
            if c.name.lower() in q_lower:
                matched_cust = c
                break

        if is_record_intent and amount_match:
            amount_val = int(amount_match.group(1))
            # If specified in rupees, convert to paise
            amount_paise = amount_val * 100 if amount_val < 100000 else amount_val

            target_cust = matched_cust
            if not target_cust:
                # Fallback or create customer
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

            # Create Receivable
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

            # Draft polite reminder and approval card
            draft = self.tools.vasooli_adapter.draft_payment_reminder(rec.id)

            approval_card = {
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
                "agent_reply": reply,
                "approval_card": approval_card,
                "action_card": approval_card,
                "receivable_id": rec.id,
                "customer_name": target_cust.name,
            }

        # Check if merchant asks to remind a specific customer: "Remind Sunita Devi" / "Send reminder to Vikram Singh"
        if "remind" in q_lower or "send reminder" in q_lower or "message" in q_lower:
            if matched_cust:
                # Find pending receivable for this customer
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
                        # Visible refusal
                        return {
                            "chip_status": "needs_human",
                            "agent_reply": f"Outreach Refused: {draft.refusal_reason}",
                            "refusal_reason": draft.refusal_reason,
                            "receivable_id": rec.id,
                        }

                    approval_card = {
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
                    return {
                        "chip_status": "awaiting_approval",
                        "agent_reply": (
                            f"Drafted polite reminder for {matched_cust.name} ({draft.amount_formatted}). "
                            "Please review the approval card below to send."
                        ),
                        "approval_card": approval_card,
                        "action_card": approval_card,
                        "receivable_id": rec.id,
                    }

        # Default summary query or explanation
        summary = self.tools.vasooli_adapter.get_vasooli_summary(merchant_id)
        reply = (
            f"Namaste! Vasooli Udhaar Summary for your store:\n"
            f"• Total Outstanding: {summary.total_outstanding_formatted} across {summary.total_receivables_count} customers\n"
            f"• Recovered Today: {summary.total_recovered_formatted}\n"
            f"• Disputed / Paused: {summary.disputed_count}\n"
            f"• Opted Out / Revoked: {summary.revoked_permission_count}\n"
            f"Tell me in plain words (e.g., 'Vikram bought 200 rs items on credit') to record udhaar."
        )
        return {
            "chip_status": "verified",
            "agent_reply": reply,
            "approval_card": None,
            "action_card": None,
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
            "chip_status": "pending",
            "approval_card": None,
            "action_card": None,
            "refusal_reason": None,
            "error": None,
        }
        return self.graph.invoke(initial_state)
