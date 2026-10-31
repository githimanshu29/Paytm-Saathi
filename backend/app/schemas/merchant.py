from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class DeviceSummary(BaseModel):
    device_type: str
    serial_number: str
    battery_level: int
    status: str
    chip_status: str  # verified | executed | pending | awaiting_approval | needs_human
    last_heartbeat: Optional[str] = None
    signal_strength_dbm: Optional[int] = -70
    technician_visit_booked: bool = False
    technician_slot: Optional[str] = None

class TransactionItem(BaseModel):
    id: str
    amount: int  # in paise
    amount_formatted: str
    customer_name: Optional[str] = None
    status: str
    payment_rail: str
    created_at: str

class PaymentSummary(BaseModel):
    today_total_paise: int
    today_total_formatted: str
    today_count: int
    chip_status: str
    recent_transactions: List[TransactionItem] = Field(default_factory=list)

class ReceivableItem(BaseModel):
    id: str
    customer_name: str
    amount: int  # in paise
    amount_formatted: str
    due_date: Optional[str] = None
    status: str

class DuesSummary(BaseModel):
    total_dues_paise: int
    total_dues_formatted: str
    total_recovered_paise: int = 0
    total_recovered_formatted: str = "₹0.00"
    pending_count: int
    chip_status: str
    receivables: List[ReceivableItem] = Field(default_factory=list)

class MerchantSummaryResponse(BaseModel):
    merchant_id: str
    store_name: str
    merchant_name: str
    phone: str
    city: str
    status: str
    kyc_status: str
    onboarding_status: Optional[str] = "COMPLETED"
    device: Optional[DeviceSummary] = None
    payments: PaymentSummary
    dues: DuesSummary

class ChatHistoryItem(BaseModel):
    role: str = "user"  # "user" or "assistant"
    content: str
    agent: Optional[str] = None
    step: Optional[str] = None

class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    history: Optional[List[ChatHistoryItem]] = Field(default_factory=list)

class VoiceChatRequest(BaseModel):
    audio_base64: Optional[str] = None
    transcript: Optional[str] = None
    language: str = "hi-IN"

class ApprovalCardData(BaseModel):
    type: str
    task_id: str
    approval_id: str
    title: str
    utr: Optional[str] = None
    customer: Optional[str] = None
    risk_tier: str
    reason: str
    note: str
    status: str
    receivable_id: Optional[str] = None
    customer_phone: Optional[str] = None
    amount_formatted: Optional[str] = None
    draft_message_hi: Optional[str] = None
    payment_link_url: Optional[str] = None
    can_send: Optional[bool] = True
    refusal_reason: Optional[str] = None
    reminder_count: Optional[int] = 0

class ChatMessageResponse(BaseModel):
    reply: str
    sender: str = "saathi"
    timestamp: str
    agent: Optional[str] = "ORCHESTRATOR"
    branch: Optional[str] = None
    step: Optional[str] = None
    chip_status: Optional[str] = None
    explanation_en: Optional[str] = None
    explanation_hi: Optional[str] = None
    tx_ref: Optional[str] = None
    case_id: Optional[str] = None
    technician_booked: Optional[bool] = False
    technician_slot: Optional[str] = None
    action_card: Optional[Dict[str, Any]] = None
    breakdown_card: Optional[Dict[str, Any]] = None
    checkin_card: Optional[Dict[str, Any]] = None
    missing_item_card: Optional[Dict[str, Any]] = None
    vasooli_card: Optional[Dict[str, Any]] = None
    checklist: Optional[Dict[str, Any]] = None
    verification_result: Optional[Dict[str, Any]] = None
    settlement_date: Optional[str] = None
    approval_card: Optional[ApprovalCardData] = None
    speech_audio_base64: Optional[str] = None
    speech_duration_seconds: Optional[float] = None
    is_synthetic: bool = True

class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., description="APPROVED or REJECTED")
    reason: Optional[str] = None

class ApprovalDecisionResponse(BaseModel):
    approval_id: str
    task_id: str
    decision: str
    chip_status: str
    message: str

class DeviceToggleResponse(BaseModel):
    success: bool
    device_id: str
    serial_number: str
    new_status: str
    message: str
