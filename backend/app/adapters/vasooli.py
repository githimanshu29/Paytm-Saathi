from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import uuid
from typing import Any, Dict, List, Optional, Protocol
from sqlalchemy.orm import Session

from app.db.models import (
    Customer,
    Receivable,
    Merchant,
    ActionApproval,
    ApprovalDecision,
    AuditEvent,
)


class CoerciveCollectionError(Exception):
    """Raised when coercive, threatening, or harassing collection language is detected."""
    pass

VasooliPolicyViolationError = CoerciveCollectionError

BANNED_PHRASES = [
    "police",
    "jail",
    "arrest",
    "legal notice",
    "court",
    "lawyer",
    "fir",
    "defaulter",
    "chor",
    "fraud",
    "criminal",
    "threat",
    "blackmail",
    "final warning",
    "last chance",
    "strict action",
    "seize",
    "family",
    "relatives",
    "neighbors",
    "social media",
    "public shaming",
]


class CommunicationPermissionRevokedError(Exception):
    """Raised when reminder outreach is attempted on an opted-out or revoked customer."""
    pass


class ReceivableDisputedError(Exception):
    """Raised when reminder outreach is attempted on a disputed ledger entry."""
    pass


@dataclass
class CustomerRecord:
    id: str
    merchant_id: str
    name: str
    phone: str
    contact_permission: bool
    permission_status: str
    notes: Optional[str] = None


@dataclass
class ReceivableRecord:
    id: str
    merchant_id: str
    customer_id: str
    customer_name: str
    customer_phone: str
    amount_paise: int
    amount_formatted: str
    due_date: Optional[str]
    status: str
    notes: Optional[str]
    is_disputed: bool
    dispute_reason: Optional[str]
    reminder_count: int
    last_reminder_sent_at: Optional[str]
    paid_amount_paise: int
    paid_amount_formatted: str
    settled_at: Optional[str]
    settlement_verification_status: str
    payment_reference: Optional[str]
    payment_link_url: Optional[str]
    negotiated_installments: Optional[List[Dict[str, Any]]]


@dataclass
class ReminderDraftResult:
    receivable_id: str
    customer_id: str
    customer_name: str
    customer_phone: str
    amount_formatted: str
    payment_link_url: str
    draft_message_hi: str
    draft_message_en: str
    is_permission_allowed: bool
    is_disputed: bool
    can_send: bool
    refusal_reason: Optional[str]
    proposal_hash: str
    reminder_count: int


@dataclass
class ReminderSendResult:
    success: bool
    receivable_id: str
    recipient_phone: str
    message_sent: str
    reminder_count: int
    audit_event_id: str
    message: str


@dataclass
class InstallmentSplitProposal:
    receivable_id: str
    total_amount_paise: int
    splits: List[Dict[str, Any]]
    proposal_summary: str
    approval_id: Optional[str] = None


@dataclass
class PaymentEventVerificationResult:
    receivable_id: str
    verified: bool
    status: str
    paid_amount_paise: int
    settlement_verification_status: str
    reminders_stopped: bool
    cancelled_approval_ids: List[str]
    audit_event_id: str
    message: str


@dataclass
class VasooliSummaryRecord:
    total_receivables_count: int
    total_outstanding_paise: int
    total_outstanding_formatted: str
    total_recovered_paise: int
    total_recovered_formatted: str
    active_reminders_count: int
    disputed_count: int
    revoked_permission_count: int
    receivables: List[ReceivableRecord]


class IVasooliAdapter(Protocol):
    def get_receivable(self, receivable_id: str) -> Optional[ReceivableRecord]: ...
    def verify_receivable_owner(self, receivable_id: str, merchant_id: str) -> bool: ...
    def get_contact_permission(self, customer_id: str) -> Dict[str, Any]: ...
    def draft_payment_reminder(self, receivable_id: str, custom_note: Optional[str] = None) -> ReminderDraftResult: ...
    def create_demo_payment_link(self, receivable_id: str) -> str: ...
    def send_authorized_reminder(
        self,
        receivable_id: str,
        actor_id: str = "merchant_user",
        idempotency_key: Optional[str] = None,
    ) -> ReminderSendResult: ...
    def negotiate_installment_split(
        self, receivable_id: str, split_amounts_paise: List[int], actor_id: str
    ) -> InstallmentSplitProposal: ...
    def record_payment_status(
        self,
        receivable_id: str,
        paid_amount_paise: int,
        payment_reference: str,
        is_authoritative: bool,
        actor_id: str,
    ) -> PaymentEventVerificationResult: ...
    def get_vasooli_summary(self, merchant_id: str) -> VasooliSummaryRecord: ...


class MockVasooliAdapter:
    """
    Authoritative adapter for consensual merchant receivable tracking (Udhaar / Khata).
    Enforces:
    1. Consensual Communication Only: Strictly checks customer communication permission.
    2. Zero Harassment / Banned Phrases: Rejects any coercive or threatening language.
    3. Respectful Cap: Capped at 3 reminder attempts total.
    4. Dispute Suspension: Suspends reminders on any disputed entry.
    5. Immediate Auto-Stop: Cancels pending approvals and stops reminders upon authoritative payment.
    """

    BANNED_PHRASES = [
        "jail", "police", "arrest", "thana", "fir", "chalan",
        "legal notice", "court", "vakeel", "advocate", "lawyer", "case karenge",
        "seize", "auction", "kurki", "property", "ghar aayenge",
        "final warning", "last warning", "akhri chetavani", "last chance", "antim chetavani",
        "defaulter", "chor", "cheat", "fraudster", "dishonest", "dhokhebaaz", "bewakoof",
        "family", "employer", "boss", "relatives", "rishtedaar", "office mein aayenge",
        "public", "social media", "naam badnaam", "poster", "shame",
    ]

    def __init__(self, db: Session):
        self.db = db

    def check_banned_phrases(self, text: str) -> Optional[str]:
        """Returns the detected banned phrase if text contains prohibited coercive terms."""
        t_clean = text.lower()
        for phrase in self.BANNED_PHRASES:
            if phrase in t_clean:
                return phrase
        return None

    def get_receivable(self, receivable_id: str) -> Optional[ReceivableRecord]:
        r = self.db.query(Receivable).filter(Receivable.id == receivable_id).first()
        if not r:
            return None

        c = r.customer
        splits = json.loads(r.negotiated_installments) if r.negotiated_installments else None

        return ReceivableRecord(
            id=r.id,
            merchant_id=r.merchant_id,
            customer_id=c.id,
            customer_name=c.name,
            customer_phone=c.phone,
            amount_paise=r.amount,
            amount_formatted=f"₹{r.amount / 100:,.2f}",
            due_date=r.due_date.isoformat() if r.due_date else None,
            status=r.status,
            notes=r.notes,
            is_disputed=r.is_disputed,
            dispute_reason=r.dispute_reason,
            reminder_count=r.reminder_count,
            last_reminder_sent_at=r.last_reminder_sent_at.isoformat() if r.last_reminder_sent_at else None,
            paid_amount_paise=r.paid_amount,
            paid_amount_formatted=f"₹{r.paid_amount / 100:,.2f}",
            settled_at=r.settled_at.isoformat() if r.settled_at else None,
            settlement_verification_status=r.settlement_verification_status,
            payment_reference=r.payment_reference,
            payment_link_url=r.payment_link_url or self.create_demo_payment_link(r.id),
            negotiated_installments=splits,
        )

    def verify_receivable_owner(self, receivable_id: str, merchant_id: str) -> bool:
        r = self.db.query(Receivable).filter(Receivable.id == receivable_id).first()
        return r is not None and r.merchant_id == merchant_id

    def get_contact_permission(self, customer_id: str) -> Dict[str, Any]:
        c = self.db.query(Customer).filter(Customer.id == customer_id).first()
        if not c:
            return {"allowed": False, "status": "UNKNOWN", "reason": "Customer not found."}

        allowed = bool(c.contact_permission and c.permission_status == "ALLOWED")
        return {
            "allowed": allowed,
            "status": c.permission_status,
            "reason": "Permission granted." if allowed else f"Customer has revoked contact permission ({c.permission_status}).",
        }

    def create_demo_payment_link(self, receivable_id: str) -> str:
        """Simulated demo payment link."""
        return f"https://paytm.demo/pay/{receivable_id}"

    def draft_payment_reminder(
        self, receivable_id: str, custom_note: Optional[str] = None
    ) -> ReminderDraftResult:
        """
        Drafts a respectful, non-threatening reminder from a strictly constrained template.
        Validates:
        1. Banned phrases (threats, last warning, shaming).
        2. Customer contact permission (refuses if revoked).
        3. Dispute status (refuses if disputed).
        4. Reminder attempt cap (max 3).
        """
        r = self.db.query(Receivable).filter(Receivable.id == receivable_id).first()
        if not r:
            raise ValueError(f"Receivable {receivable_id} not found")

        c = r.customer
        m = r.merchant
        store_name = m.store_name if m else "Paytm Merchant Partner"
        amount_fmt = f"₹{r.amount / 100:,.2f}"
        payment_link = r.payment_link_url or self.create_demo_payment_link(r.id)

        # 1. Banned phrase check on optional custom note
        if custom_note:
            violation = self.check_banned_phrases(custom_note)
            if violation:
                raise CoerciveCollectionError(
                    f"Prohibited coercive language detected ('{violation}'). Vasooli strictly forbids threats, shaming, or legal intimidation."
                )

        # 2. Permission check
        perm = self.get_contact_permission(c.id)
        is_permission_allowed = perm["allowed"]

        # 3. Dispute check
        is_disputed = r.is_disputed

        # 4. Cap check
        is_capped = r.reminder_count >= 3

        # Formulate respectful template messages
        draft_hi = (
            f"Namaste {c.name} ji, {store_name} ki taraf se aadar sahit sandesh. "
            f"Aapka pichhla kirana udhaar {amount_fmt} baaki hai. "
            f"Aap suvidhanusar niche diye gaye surakshit UPI link se bhugtan kar sakte hain: {payment_link}. "
            f"Kisi bhi jaankari ya sankocha ke liye kripya dukan par sampark karein. Dhanyawad!"
        )

        draft_en = (
            f"Hello {c.name}, gentle reminder from {store_name}. "
            f"Your store credit balance of {amount_fmt} is pending. "
            f"You can pay conveniently via this secure UPI demo link: {payment_link}. "
            f"Feel free to visit or call us for any clarification. Thank you!"
        )

        can_send = True
        refusal_reason = None

        if not is_permission_allowed:
            can_send = False
            refusal_reason = (
                f"Customer {c.name} has revoked contact permission (Status: {perm['status']}). "
                f"Under Paytm Saathi consensual policy, reminder outreach is strictly forbidden."
            )
        elif is_disputed:
            can_send = False
            refusal_reason = (
                f"Receivable #{r.id} is currently disputed by the customer ('{r.dispute_reason}'). "
                f"Vasooli suspends all reminders until the merchant resolves the ledger discrepancy."
            )
        elif is_capped:
            can_send = False
            refusal_reason = (
                "Maximum reminder cap reached (3/3 attempts sent). "
                "Automated reminders are paused to avoid customer fatigue. Please follow up in person."
            )
        elif r.status == "PAID":
            can_send = False
            refusal_reason = "Receivable is already paid in full. No reminder needed."

        # Compute deterministic proposal hash for R2 approval gate
        canonical = f"{r.id}:{c.id}:{r.amount}:{draft_en}"
        prop_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]

        return ReminderDraftResult(
            receivable_id=r.id,
            customer_id=c.id,
            customer_name=c.name,
            customer_phone=c.phone,
            amount_formatted=amount_fmt,
            payment_link_url=payment_link,
            draft_message_hi=draft_hi,
            draft_message_en=draft_en,
            is_permission_allowed=is_permission_allowed,
            is_disputed=is_disputed,
            can_send=can_send,
            refusal_reason=refusal_reason,
            proposal_hash=prop_hash,
            reminder_count=r.reminder_count,
        )

    def send_authorized_reminder(
        self,
        receivable_id: str,
        actor_id: str = "merchant_user",
        idempotency_key: Optional[str] = None,
    ) -> ReminderSendResult:
        """
        Sends reminder message ONLY after merchant approval and clean permission check.
        Enforces idempotency: retried sends with same idempotency_key return previous result without re-sending.
        """
        if not idempotency_key:
            idempotency_key = f"idem_rem_{receivable_id}_{uuid.uuid4().hex[:8]}"
        r = self.db.query(Receivable).filter(Receivable.id == receivable_id).first()
        if not r:
            raise ValueError(f"Receivable {receivable_id} not found")

        c = r.customer
        if not c.contact_permission or c.permission_status != "ALLOWED":
            raise CommunicationPermissionRevokedError(
                f"Cannot send reminder: Customer {c.name} has revoked communication permission."
            )

        if r.is_disputed:
            raise ReceivableDisputedError(
                f"Cannot send reminder: Receivable is disputed ('{r.dispute_reason}')."
            )

        if r.status == "PAID":
            raise ValueError("Receivable is already settled in full.")

        if r.reminder_count >= 3:
            raise ValueError("Reminder cap (3) reached.")

        # Idempotency check: see if audit event with this idempotency key already exists
        existing_event = (
            self.db.query(AuditEvent)
            .filter(AuditEvent.idempotency_key == idempotency_key)
            .first()
        )
        if existing_event:
            return ReminderSendResult(
                success=True,
                receivable_id=r.id,
                recipient_phone=c.phone,
                message_sent="Respectful payment reminder sent previously (idempotent replay).",
                reminder_count=r.reminder_count,
                audit_event_id=existing_event.id,
                message="Reminder replay verified via idempotency key.",
            )

        # Update receivable reminder state
        now = datetime.now(timezone.utc)
        r.reminder_count += 1
        r.last_reminder_sent_at = now

        msg_text = (
            f"Namaste {c.name} ji, Sharma Kirana Store ki taraf se aadar sahit sandesh. "
            f"Aapka pichhla kirana udhaar ₹{r.amount / 100:,.2f} baaki hai. "
            f"Link: {r.payment_link_url or self.create_demo_payment_link(r.id)}. Dhanyawad!"
        )

        # Log audit event
        audit = AuditEvent(
            tenant_id=r.tenant_id,
            actor=actor_id,
            action="VASOOLI_REMINDER_SENT",
            target=f"receivables:{r.id}",
            policy_decision_id="dec_vasooli_authorized_reminder",
            idempotency_key=idempotency_key,
            result="SUCCESS",
            is_synthetic=True,
            environment="DEMO",
            created_at=now,
        )
        self.db.add(audit)
        self.db.commit()

        return ReminderSendResult(
            success=True,
            receivable_id=r.id,
            recipient_phone=c.phone,
            message_sent=msg_text,
            reminder_count=r.reminder_count,
            audit_event_id=audit.id,
            message="Authorized respectful reminder delivered successfully.",
        )

    def negotiate_installment_split(
        self, receivable_id: str, split_amounts_paise: List[int], actor_id: str
    ) -> InstallmentSplitProposal:
        """
        Negotiates partial / delayed payment installments.
        Proposes split as a NEW approval, capped at 3 reminder attempts total.
        """
        r = self.db.query(Receivable).filter(Receivable.id == receivable_id).first()
        if not r:
            raise ValueError(f"Receivable {receivable_id} not found")

        total_splits = sum(split_amounts_paise)
        if total_splits != r.amount:
            raise ValueError(
                f"Split amounts sum (₹{total_splits / 100}) must equal total receivable amount (₹{r.amount / 100})."
            )

        now = datetime.now(timezone.utc)
        splits_data = []
        for idx, amt in enumerate(split_amounts_paise, start=1):
            splits_data.append(
                {
                    "installment": idx,
                    "amount_paise": amt,
                    "amount_formatted": f"₹{amt / 100:,.2f}",
                    "due_date": (now.date()).isoformat(),
                    "status": "PROPOSED",
                }
            )

        r.negotiated_installments = json.dumps(splits_data)

        # Create ActionApproval for merchant to approve the negotiated split
        prop_hash = hashlib.sha256(f"split:{r.id}:{r.negotiated_installments}".encode("utf-8")).hexdigest()[:24]
        approval = ActionApproval(
            tenant_id=r.tenant_id,
            receivable_id=r.id,
            approver=r.merchant.merchant_name if r.merchant else "Merchant",
            decision=ApprovalDecision.PENDING,
            reason=f"Customer proposed 2-part split for ₹{r.amount / 100:,.2f} udhaar balance.",
            risk_tier="R2",
            proposal_hash=prop_hash,
            is_synthetic=True,
            environment="DEMO",
            created_at=now,
        )
        self.db.add(approval)

        # Emit audit event
        audit = AuditEvent(
            tenant_id=r.tenant_id,
            actor=actor_id,
            action="VASOOLI_INSTALLMENT_SPLIT_PROPOSED",
            target=f"receivables:{r.id}",
            policy_decision_id="dec_vasooli_split_proposed",
            idempotency_key=f"idemp_split_{r.id}_{prop_hash}",
            result="PROPOSAL_CREATED",
            is_synthetic=True,
            environment="DEMO",
            created_at=now,
        )
        self.db.add(audit)
        self.db.commit()

        summary = f"Proposed {len(split_amounts_paise)}-part installment plan: " + ", ".join(
            [f"₹{amt / 100:,.2f}" for amt in split_amounts_paise]
        )

        return InstallmentSplitProposal(
            receivable_id=r.id,
            total_amount_paise=r.amount,
            splits=splits_data,
            proposal_summary=summary,
            approval_id=approval.id,
        )

    def record_payment_status(
        self,
        receivable_id: str,
        paid_amount_paise: int,
        payment_reference: str,
        is_authoritative: bool,
        actor_id: str,
    ) -> PaymentEventVerificationResult:
        """
        Records payment status:
        - If authoritative payment event: marks VERIFIED_PAID, stops reminders, and cancels any pending approvals.
        - If merchant-reported: explicitly flags as MERCHANT_REPORTED_UNVERIFIED.
        """
        r = self.db.query(Receivable).filter(Receivable.id == receivable_id).first()
        if not r:
            raise ValueError(f"Receivable {receivable_id} not found")

        now = datetime.now(timezone.utc)
        cancelled_approvals: List[str] = []

        if is_authoritative:
            r.paid_amount += paid_amount_paise
            r.payment_reference = payment_reference

            if r.paid_amount >= r.amount:
                r.status = "PAID"
                r.settlement_verification_status = "VERIFIED_PAID"
                r.settled_at = now
            else:
                r.status = "PARTIALLY_PAID"
                r.settlement_verification_status = "PARTIALLY_SETTLED"

            # Auto-cancel any pending approvals for this receivable
            pending_approvals = (
                self.db.query(ActionApproval)
                .filter(
                    ActionApproval.receivable_id == r.id,
                    ActionApproval.decision == ApprovalDecision.PENDING,
                )
                .all()
            )
            for app in pending_approvals:
                app.decision = ApprovalDecision.REJECTED
                app.reason = "AUTO_CANCELLED: Payment arrived before reminder was sent."
                cancelled_approvals.append(app.id)

            action_name = "VASOOLI_PAYMENT_VERIFIED"
            result_code = "VERIFIED_PAID"
            msg = f"Authoritative payment event confirmed (Ref: {payment_reference}). Reminders auto-stopped."
        else:
            r.settlement_verification_status = "MERCHANT_REPORTED_UNVERIFIED"
            action_name = "VASOOLI_PAYMENT_REPORTED_UNVERIFIED"
            result_code = "PENDING_VERIFICATION"
            msg = "Payment recorded as merchant-reported (unverified until bank payment event arrives)."

        # Emit audit event
        audit = AuditEvent(
            tenant_id=r.tenant_id,
            actor=actor_id,
            action=action_name,
            target=f"receivables:{r.id}",
            policy_decision_id="dec_vasooli_payment_event",
            idempotency_key=f"idemp_pay_{r.id}_{payment_reference}_{r.paid_amount}",
            result=result_code,
            is_synthetic=True,
            environment="DEMO",
            created_at=now,
        )
        self.db.add(audit)
        self.db.commit()

        return PaymentEventVerificationResult(
            receivable_id=r.id,
            verified=is_authoritative,
            status=r.status,
            paid_amount_paise=r.paid_amount,
            settlement_verification_status=r.settlement_verification_status,
            reminders_stopped=is_authoritative and r.status == "PAID",
            cancelled_approval_ids=cancelled_approvals,
            audit_event_id=audit.id,
            message=msg,
        )

    def get_vasooli_summary(self, merchant_id: str) -> VasooliSummaryRecord:
        """Computes daily recovery summary and returns active receivable ledger."""
        recs = (
            self.db.query(Receivable)
            .filter(Receivable.merchant_id == merchant_id)
            .order_by(Receivable.created_at.desc())
            .all()
        )

        total_count = len(recs)
        outstanding = sum(r.amount - r.paid_amount for r in recs if r.status in ["PENDING", "PARTIALLY_PAID", "DISPUTED"])
        recovered = sum(r.paid_amount for r in recs)
        active_reminders = sum(1 for r in recs if r.status == "PENDING" and not r.is_disputed and r.customer.contact_permission)
        disputed = sum(1 for r in recs if r.is_disputed)
        revoked = sum(1 for r in recs if not r.customer.contact_permission or r.customer.permission_status != "ALLOWED")

        records_list = [self.get_receivable(r.id) for r in recs if self.get_receivable(r.id) is not None]

        return VasooliSummaryRecord(
            total_receivables_count=total_count,
            total_outstanding_paise=outstanding,
            total_outstanding_formatted=f"₹{outstanding / 100:,.2f}",
            total_recovered_paise=recovered,
            total_recovered_formatted=f"₹{recovered / 100:,.2f}",
            active_reminders_count=active_reminders,
            disputed_count=disputed,
            revoked_permission_count=revoked,
            receivables=records_list,
        )

    def create_receivable(
        self,
        merchant_id: str,
        customer_name: str,
        amount_paise: int,
        customer_phone: Optional[str] = None,
        notes: Optional[str] = None,
        due_days: int = 7,
    ) -> ReceivableRecord:
        """Creates a new consensual store credit (udhaar) record."""
        from datetime import timedelta

        clean_name = customer_name.strip()
        phone = (customer_phone or "").strip()
        if not phone:
            phone = f"91{uuid.uuid4().int % 9000000000 + 1000000000}"

        m = self.db.query(Merchant).filter(Merchant.id == merchant_id).first()
        tenant_id = m.tenant_id if m else "ten_paytm_default"

        cust = (
            self.db.query(Customer)
            .filter(Customer.merchant_id == merchant_id)
            .filter((Customer.name == clean_name) | (Customer.phone == phone))
            .first()
        )
        if not cust:
            cust = Customer(
                id=f"cust_{uuid.uuid4().hex[:10]}",
                tenant_id=tenant_id,
                merchant_id=merchant_id,
                name=clean_name,
                phone=phone,
                contact_permission=True,
                permission_status="ALLOWED",
                is_synthetic=True,
                created_at=datetime.now(timezone.utc),
            )
            self.db.add(cust)
            self.db.flush()

        due_date = datetime.now(timezone.utc) + timedelta(days=max(1, due_days))
        rec_id = f"rec_{uuid.uuid4().hex[:10]}"

        rec = Receivable(
            id=rec_id,
            tenant_id=tenant_id,
            merchant_id=merchant_id,
            customer_id=cust.id,
            amount=amount_paise,
            due_date=due_date,
            status="PENDING",
            notes=notes.strip() if notes else "Consensual store credit / Udhaar",
            is_disputed=False,
            reminder_count=0,
            paid_amount=0,
            settlement_verification_status="UNSETTLED",
            payment_link_url=f"https://paytm.me/pay?r={rec_id}",
            is_synthetic=True,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(rec)
        self.db.commit()
        self.db.refresh(rec)
        return self.get_receivable(rec.id)

