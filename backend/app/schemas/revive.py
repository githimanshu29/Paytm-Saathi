from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MerchantHealthKPI(BaseModel):
    total_at_risk: int
    device_issues_count: int
    settlement_issues_count: int
    competitor_issues_count: int
    followups_sent_count: int
    warm_leads_count: int
    revived_count: int


class MerchantHealthItem(BaseModel):
    id: str
    merchant_id: str
    store_name: str
    city: str
    baseline_daily_tx_count: int
    baseline_daily_volume_paise: int
    baseline_daily_volume_inr: str
    recent_daily_tx_count: int
    recent_daily_volume_paise: int
    recent_daily_volume_inr: str
    drop_percentage: int
    health_status: str  # HEALTHY | AT_RISK | DORMANT
    diagnosed_cause: Optional[str] = None  # DEVICE_ISSUE | SETTLEMENT_ISSUE | COMPETITOR_OR_DISENGAGEMENT
    revival_stage: str  # AT_RISK | FOLLOWUP_SENT | WARM_LEAD | REVIVED
    chip_status: str
    last_scanned_at: str
    recovered_at: Optional[str] = None
    active_followup: Optional[Dict[str, Any]] = None


class MerchantHealthResponse(BaseModel):
    kpi: MerchantHealthKPI
    merchants: List[MerchantHealthItem]


class ScanTriggerResponse(BaseModel):
    success: bool
    scanned_count: int
    message: str
    results: List[Dict[str, Any]]


class FollowupResponseRequest(BaseModel):
    decision: str = Field(..., description="ACCEPT or DISMISS")


class FollowupResponseResult(BaseModel):
    success: bool
    followup_id: str
    status: str
    task_id: Optional[str] = None
    message: str


class SimulateRecoveryRequest(BaseModel):
    new_daily_volume_paise: int = 1000000  # Default 10,000 INR
    new_daily_tx_count: int = 35


class SimulateRecoveryResponse(BaseModel):
    success: bool
    merchant_id: str
    health_status: str
    revival_stage: str
    drop_percentage: int
    is_revived: bool
    message: str
