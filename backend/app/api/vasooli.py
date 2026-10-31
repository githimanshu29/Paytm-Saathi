import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.db.models import Receivable, Customer, ActionApproval, ApprovalDecision
from app.adapters.vasooli import (
    MockVasooliAdapter,
    CoerciveCollectionError,
    CommunicationPermissionRevokedError,
    ReceivableDisputedError,
)
from app.schemas.vasooli import (
    VasooliSummaryResponse,
    ReceivableItemSchema,
    ReminderDraftRequest,
    ReminderDraftResponse,
    ReminderSendRequest,
    ReminderSendResponse,
    RecordPaymentEventRequest,
    RecordPaymentEventResponse,
    NegotiateSplitRequest,
    NegotiateSplitResponse,
)

vasooli_router = APIRouter(prefix="/merchant/vasooli", tags=["Vasooli (Receivables)"])
demo_vasooli_router = APIRouter(prefix="/demo/vasooli", tags=["Vasooli Demo Triggers"])
employee_vasooli_router = APIRouter(prefix="/employee/vasooli", tags=["Vasooli Employee Control"])


@vasooli_router.get("/summary", response_model=VasooliSummaryResponse)
def get_merchant_vasooli_summary(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns consensual receivable tracking summary for the logged-in merchant.
    """
    merchant_id = user.get("sub", "mer_sharma_kirana")
    adapter = MockVasooliAdapter(db)
    summary = adapter.get_vasooli_summary(merchant_id)

    return VasooliSummaryResponse(
        merchant_id=merchant_id,
        total_receivables_count=summary.total_receivables_count,
        total_outstanding_paise=summary.total_outstanding_paise,
        total_outstanding_formatted=summary.total_outstanding_formatted,
        total_recovered_paise=summary.total_recovered_paise,
        total_recovered_formatted=summary.total_recovered_formatted,
        active_reminders_count=summary.active_reminders_count,
        disputed_count=summary.disputed_count,
        revoked_permission_count=summary.revoked_permission_count,
        receivables=[
            ReceivableItemSchema(
                id=r.id,
                merchant_id=r.merchant_id,
                customer_id=r.customer_id,
                customer_name=r.customer_name,
                customer_phone=r.customer_phone,
                amount_paise=r.amount_paise,
                amount_formatted=r.amount_formatted,
                due_date=r.due_date,
                status=r.status,
                notes=r.notes,
                is_disputed=r.is_disputed,
                dispute_reason=r.dispute_reason,
                reminder_count=r.reminder_count,
                last_reminder_sent_at=r.last_reminder_sent_at,
                paid_amount_paise=r.paid_amount_paise,
                paid_amount_formatted=r.paid_amount_formatted,
                settled_at=r.settled_at,
                settlement_verification_status=r.settlement_verification_status,
                payment_reference=r.payment_reference,
                payment_link_url=r.payment_link_url,
                negotiated_installments=r.negotiated_installments,
            )
            for r in summary.receivables
        ],
    )


@vasooli_router.post("/draft-reminder", response_model=ReminderDraftResponse)
def draft_payment_reminder(
    req: ReminderDraftRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Drafts a polite, non-threatening reminder. Rejects coercive/shaming language.
    """
    merchant_id = user.get("sub", "mer_sharma_kirana")
    adapter = MockVasooliAdapter(db)

    # Ownership check
    if not adapter.verify_receivable_owner(req.receivable_id, merchant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Receivable belongs to another merchant.")

    try:
        draft = adapter.draft_payment_reminder(req.receivable_id, req.custom_note)
        return ReminderDraftResponse(
            receivable_id=draft.receivable_id,
            customer_name=draft.customer_name,
            customer_phone=draft.customer_phone,
            amount_formatted=draft.amount_formatted,
            payment_link_url=draft.payment_link_url,
            draft_message_hi=draft.draft_message_hi,
            draft_message_en=draft.draft_message_en,
            can_send=draft.can_send,
            refusal_reason=draft.refusal_reason,
            proposal_hash=draft.proposal_hash,
            reminder_count=draft.reminder_count,
        )
    except CoerciveCollectionError as ce:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ce),
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))


@vasooli_router.post("/send-reminder", response_model=ReminderSendResponse)
def send_authorized_reminder(
    req: ReminderSendRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Sends authorized reminder. Gated by merchant approval and communication permission.
    """
    merchant_id = user.get("sub", "mer_sharma_kirana")
    adapter = MockVasooliAdapter(db)

    if not adapter.verify_receivable_owner(req.receivable_id, merchant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Receivable belongs to another merchant.")

    idemp = req.idempotency_key or f"idemp_send_{req.receivable_id}_{uuid.uuid4().hex[:8]}"

    try:
        res = adapter.send_authorized_reminder(
            receivable_id=req.receivable_id,
            actor_id=merchant_id,
            idempotency_key=idemp,
        )
        return ReminderSendResponse(
            success=res.success,
            receivable_id=res.receivable_id,
            recipient_phone=res.recipient_phone,
            message_sent=res.message_sent,
            reminder_count=res.reminder_count,
            audit_event_id=res.audit_event_id,
            message=res.message,
        )
    except CommunicationPermissionRevokedError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ReceivableDisputedError as de:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(de))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@vasooli_router.post("/negotiate-split", response_model=NegotiateSplitResponse)
def negotiate_installment_split(
    req: NegotiateSplitRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Negotiates installment split proposal.
    """
    merchant_id = user.get("sub", "mer_sharma_kirana")
    adapter = MockVasooliAdapter(db)

    if not adapter.verify_receivable_owner(req.receivable_id, merchant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    try:
        prop = adapter.negotiate_installment_split(
            receivable_id=req.receivable_id,
            split_amounts_paise=req.split_amounts_paise,
            actor_id=merchant_id,
        )
        return NegotiateSplitResponse(
            receivable_id=prop.receivable_id,
            total_amount_paise=prop.total_amount_paise,
            splits=prop.splits,
            proposal_summary=prop.proposal_summary,
            approval_id=prop.approval_id,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve))


# -----------------------------------------------------------------------------
# Demo Trigger: Authoritative Payment Received Webhook
# -----------------------------------------------------------------------------
@demo_vasooli_router.post("/payment-event", response_model=RecordPaymentEventResponse)
def demo_trigger_payment_received(
    req: RecordPaymentEventRequest,
    db: Session = Depends(get_db),
):
    """
    Demo Payment Trigger: Simulates an authoritative customer payment event.
    Auto-stops reminders, cancels pending approvals, marks VERIFIED_PAID.
    """
    adapter = MockVasooliAdapter(db)
    ref = req.payment_reference or f"PAYTM_UPI_DEMO_{uuid.uuid4().hex[:8].upper()}"

    try:
        res = adapter.record_payment_status(
            receivable_id=req.receivable_id,
            paid_amount_paise=req.amount_paise,
            payment_reference=ref,
            is_authoritative=req.is_authoritative,
            actor_id="demo_webhook_icici_nodal",
        )
        return RecordPaymentEventResponse(
            receivable_id=res.receivable_id,
            verified=res.verified,
            status=res.status,
            paid_amount_paise=res.paid_amount_paise,
            settlement_verification_status=res.settlement_verification_status,
            reminders_stopped=res.reminders_stopped,
            cancelled_approval_ids=res.cancelled_approval_ids,
            audit_event_id=res.audit_event_id,
            message=res.message,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))


# -----------------------------------------------------------------------------
# Employee Control Tower Overview
# -----------------------------------------------------------------------------
@employee_vasooli_router.get("/overview")
def get_employee_vasooli_overview(
    merchant_id: str = Query("mer_sharma_kirana"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns store credit recovery overview for employee web dashboard.
    """
    if user.get("user_type") != "employee":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Employee access required.")

    adapter = MockVasooliAdapter(db)
    summary = adapter.get_vasooli_summary(merchant_id)

    return {
        "merchant_id": merchant_id,
        "total_receivables_count": summary.total_receivables_count,
        "total_outstanding_paise": summary.total_outstanding_paise,
        "total_outstanding_formatted": summary.total_outstanding_formatted,
        "total_recovered_paise": summary.total_recovered_paise,
        "total_recovered_formatted": summary.total_recovered_formatted,
        "active_reminders_count": summary.active_reminders_count,
        "disputed_count": summary.disputed_count,
        "revoked_permission_count": summary.revoked_permission_count,
        "receivables": [
            {
                "id": r.id,
                "customer_name": r.customer_name,
                "customer_phone": r.customer_phone,
                "amount_formatted": r.amount_formatted,
                "paid_amount_formatted": r.paid_amount_formatted,
                "status": r.status,
                "is_disputed": r.is_disputed,
                "dispute_reason": r.dispute_reason,
                "reminder_count": r.reminder_count,
                "settlement_verification_status": r.settlement_verification_status,
                "last_reminder_sent_at": r.last_reminder_sent_at,
            }
            for r in summary.receivables
        ],
    }
