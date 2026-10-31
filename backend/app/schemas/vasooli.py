from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ReceivableItemSchema(BaseModel):
    id: str
    merchant_id: str
    customer_id: str
    customer_name: str
    customer_phone: str
    amount_paise: int
    amount_formatted: str
    due_date: Optional[str]
    status: str
    notes: Optional[str] = None
    is_disputed: bool
    dispute_reason: Optional[str] = None
    reminder_count: int
    last_reminder_sent_at: Optional[str] = None
    paid_amount_paise: int
    paid_amount_formatted: str
    settled_at: Optional[str] = None
    settlement_verification_status: str
    payment_reference: Optional[str] = None
    payment_link_url: Optional[str] = None
    negotiated_installments: Optional[List[Dict[str, Any]]] = None


class VasooliSummaryResponse(BaseModel):
    merchant_id: str
    total_receivables_count: int
    total_outstanding_paise: int
    total_outstanding_formatted: str
    total_recovered_paise: int
    total_recovered_formatted: str
    active_reminders_count: int
    disputed_count: int
    revoked_permission_count: int
    receivables: List[ReceivableItemSchema]


class ReminderDraftRequest(BaseModel):
    receivable_id: str
    custom_note: Optional[str] = None


class ReminderDraftResponse(BaseModel):
    receivable_id: str
    customer_name: str
    customer_phone: str
    amount_formatted: str
    payment_link_url: str
    draft_message_hi: str
    draft_message_en: str
    can_send: bool
    refusal_reason: Optional[str] = None
    proposal_hash: str
    reminder_count: int


class ReminderSendRequest(BaseModel):
    receivable_id: str
    approval_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class ReminderSendResponse(BaseModel):
    success: bool
    receivable_id: str
    recipient_phone: str
    message_sent: str
    reminder_count: int
    audit_event_id: str
    message: str


class RecordPaymentEventRequest(BaseModel):
    receivable_id: str
    amount_paise: int
    payment_reference: Optional[str] = None
    is_authoritative: bool = True


class RecordPaymentEventResponse(BaseModel):
    receivable_id: str
    verified: bool
    status: str
    paid_amount_paise: int
    settlement_verification_status: str
    reminders_stopped: bool
    cancelled_approval_ids: List[str]
    audit_event_id: str
    message: str


class NegotiateSplitRequest(BaseModel):
    receivable_id: str
    split_amounts_paise: List[int]


class NegotiateSplitResponse(BaseModel):
    receivable_id: str
    total_amount_paise: int
    splits: List[Dict[str, Any]]
    proposal_summary: str
    approval_id: Optional[str] = None


class CreateReceivableRequest(BaseModel):
    customer_name: str
    customer_phone: Optional[str] = None
    amount_rupees: Optional[float] = None
    amount_paise: Optional[int] = None
    notes: Optional[str] = None
    due_days: Optional[int] = 7


class CreateReceivableResponse(BaseModel):
    success: bool
    receivable: ReceivableItemSchema
    message: str

