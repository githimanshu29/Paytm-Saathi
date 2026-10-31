from typing import List, Optional
from pydantic import BaseModel, Field

class DeviceSummary(BaseModel):
    device_type: str
    serial_number: str
    battery_level: int
    status: str
    chip_status: str  # verified | executed | pending | awaiting_approval | needs_human

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
    device: Optional[DeviceSummary] = None
    payments: PaymentSummary
    dues: DuesSummary

class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)

class ChatMessageResponse(BaseModel):
    reply: str
    sender: str = "saathi"
    timestamp: str
    is_synthetic: bool = True
