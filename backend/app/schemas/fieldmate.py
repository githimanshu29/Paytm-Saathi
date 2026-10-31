from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MerchantRouteItemSchema(BaseModel):
    visit_id: str
    merchant_id: str
    store_name: str
    merchant_name: str
    phone: str
    city: str
    latitude: float
    longitude: float
    distance_km: float
    priority: str
    planned_order: int
    visit_status: str
    evidence_backed_brief: str
    brief_cause_type: str
    lead_status: str
    is_confirmed_by_rep: bool
    version: int


class RouteResponse(BaseModel):
    sales_rep_id: str
    rep_lat: float
    rep_lon: float
    count: int
    disclaimer: str
    merchants: List[MerchantRouteItemSchema]


class MerchantBriefDetailResponse(BaseModel):
    merchant_id: str
    store_name: str
    merchant_name: str
    phone: str
    city: str
    distance_km: float
    priority: str
    one_line_brief: str
    brief_cause_type: str
    evidence_breakdown: Dict[str, Any]
    talking_points: List[str]
    recommended_pitch: str
    visit_id: Optional[str]
    version: int


class VoiceNoteExtractRequest(BaseModel):
    visit_id: str
    raw_transcript: Optional[str] = None
    audio_base64: Optional[str] = None


class VoiceNoteExtractResponse(BaseModel):
    visit_id: str
    merchant_id: str
    raw_transcript: str
    extracted_candidate_fields: Dict[str, Any]
    proposed_lead_interest: Optional[str] = None
    requires_rep_confirmation: bool = True
    disclaimer: str
    version: int


class VoiceNoteConfirmRequest(BaseModel):
    visit_id: str
    expected_version: int
    confirmed_notes: str
    lead_interest: Optional[str] = None


class VoiceNoteConfirmResponse(BaseModel):
    visit_id: str
    merchant_id: str
    is_confirmed: bool
    confirmed_notes: str
    lead_interest: Optional[str] = None
    new_version: int
    audit_event_id: str
    message: str


class ConfirmedVisitItem(BaseModel):
    visit_id: str
    merchant_id: str
    store_name: str
    merchant_name: str
    confirmed_notes: Optional[str]
    lead_interest: Optional[str]
    confirmed_at: Optional[str]
    version: int


class ManagerRepSummaryResponse(BaseModel):
    sales_rep_id: str
    rep_name: str
    total_assigned_merchants: int
    planned_visits_today: int
    completed_visits_today: int
    completion_rate_pct: int
    leads_generated_today: int
    confirmed_visits: List[ConfirmedVisitItem]
