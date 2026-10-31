from typing import List, Optional
from pydantic import BaseModel, Field

class DashboardKPISummary(BaseModel):
    total_merchants: int
    active_devices: int
    total_devices: int
    pending_approvals: int
    needs_human_cases: int
    total_transactions_paise: int
    total_transactions_formatted: str
    total_tasks: int

class AuditEventItem(BaseModel):
    id: str
    actor: str
    action: str
    target: str
    policy_decision_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    result: str
    created_at: str
    environment: str = "DEMO"

class AuditLogResponse(BaseModel):
    total: int
    events: List[AuditEventItem]

class CaseApprovalSummary(BaseModel):
    id: str
    approver: Optional[str] = None
    decision: str
    reason: Optional[str] = None
    risk_tier: str
    expires_at: Optional[str] = None

class CaseItem(BaseModel):
    id: str
    merchant_id: str
    store_name: str
    merchant_phone: str
    city: str
    title: str
    description: Optional[str] = None
    bucket: str  # verified | executed | pending | awaiting_approval | needs_human
    priority: str
    assigned_to: Optional[str] = None
    evidence_notes: Optional[str] = None
    evidence_url: Optional[str] = None
    dispute_amount_formatted: Optional[str] = None
    approval: Optional[CaseApprovalSummary] = None
    created_at: str
    updated_at: str

class CasesResponse(BaseModel):
    total: int
    cases: List[CaseItem]

class CaseTimelineResponse(BaseModel):
    case_id: str
    events: List[AuditEventItem]
