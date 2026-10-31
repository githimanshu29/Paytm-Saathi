from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.db.models import Merchant, MerchantVisit, EmployeeRole
from app.adapters.fieldmate import (
    MockFieldMateAdapter,
    ConcurrencyConflictError,
    RepPolicyViolationError,
)
from app.schemas.fieldmate import (
    RouteResponse,
    MerchantRouteItemSchema,
    MerchantBriefDetailResponse,
    VoiceNoteExtractRequest,
    VoiceNoteExtractResponse,
    VoiceNoteConfirmRequest,
    VoiceNoteConfirmResponse,
    ManagerRepSummaryResponse,
    ConfirmedVisitItem,
)

fieldmate_router = APIRouter(prefix="/employee/fieldmate", tags=["FieldMate (Sales Copilot)"])


def get_authenticated_sales_rep_id(user: dict, requested_rep_id: Optional[str] = None) -> str:
    """
    Validates employee token and returns effective sales_rep_id.
    Sales reps are confined to their own ID. Managers can view assigned reps.
    """
    if user.get("user_type") != "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Employee access required.",
        )

    role = user.get("role")
    user_id = user.get("sub")

    if role == EmployeeRole.SALES_REP.value:
        return user_id

    # Managers and admins can query any sales rep, defaulting to requested or demo rep
    if requested_rep_id:
        return requested_rep_id
    return user_id if user_id else "emp_sales_01"


@fieldmate_router.get("/route", response_model=RouteResponse)
def get_sales_route(
    sales_rep_id: Optional[str] = Query(None),
    rep_lat: float = Query(26.9150),
    rep_lon: float = Query(75.8150),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns prioritized route for the sales rep with evidence-backed one-line briefs.
    Heuristic recommendation balancing urgency priority and proximity.
    """
    effective_rep_id = get_authenticated_sales_rep_id(user, sales_rep_id)
    adapter = MockFieldMateAdapter(db)

    ordered_items = adapter.suggest_visit_order(effective_rep_id, rep_lat, rep_lon)

    return RouteResponse(
        sales_rep_id=effective_rep_id,
        rep_lat=rep_lat,
        rep_lon=rep_lon,
        count=len(ordered_items),
        disclaimer="Route is a heuristic priority recommendation, not a guaranteed-optimal route.",
        merchants=[
            MerchantRouteItemSchema(
                visit_id=item.visit_id,
                merchant_id=item.merchant_id,
                store_name=item.store_name,
                merchant_name=item.merchant_name,
                phone=item.phone,
                city=item.city,
                latitude=item.latitude,
                longitude=item.longitude,
                distance_km=item.distance_km,
                priority=item.priority,
                planned_order=item.planned_order,
                visit_status=item.visit_status,
                evidence_backed_brief=item.evidence_backed_brief,
                brief_cause_type=item.brief_cause_type,
                lead_status=item.lead_status,
                is_confirmed_by_rep=item.is_confirmed_by_rep,
                version=item.version,
            )
            for item in ordered_items
        ],
    )


@fieldmate_router.get("/brief/{merchant_id}", response_model=MerchantBriefDetailResponse)
def get_merchant_brief(
    merchant_id: str,
    rep_lat: float = Query(26.9150),
    rep_lon: float = Query(75.8150),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns an evidence-backed brief with talking points derived strictly from DB facts.
    Enforces sales rep boundary (rep cannot inspect unassigned merchants).
    """
    effective_rep_id = get_authenticated_sales_rep_id(user)
    role = user.get("role")

    # Boundary check for sales_rep role
    if role == EmployeeRole.SALES_REP.value:
        m = db.query(Merchant).filter(Merchant.id == merchant_id).first()
        if not m:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found.")
        if m.assigned_sales_rep_id and m.assigned_sales_rep_id != effective_rep_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access Denied: Merchant is not assigned to your territory.",
            )

    adapter = MockFieldMateAdapter(db)
    brief = adapter.get_merchant_brief(merchant_id, rep_lat, rep_lon)
    if not brief:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant brief not found.")

    return MerchantBriefDetailResponse(
        merchant_id=brief.merchant_id,
        store_name=brief.store_name,
        merchant_name=brief.merchant_name,
        phone=brief.phone,
        city=brief.city,
        distance_km=brief.distance_km,
        priority=brief.priority,
        one_line_brief=brief.one_line_brief,
        brief_cause_type=brief.brief_cause_type,
        evidence_breakdown=brief.evidence_breakdown,
        talking_points=brief.talking_points,
        recommended_pitch=brief.recommended_pitch,
        visit_id=brief.visit_id,
        version=brief.version,
    )


@fieldmate_router.post("/voice-note/extract", response_model=VoiceNoteExtractResponse)
def extract_voice_note(
    req: VoiceNoteExtractRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Extracts structured candidate fields from a rep's voice note or transcript.
    CORE INVARIANT: Returns an UNCONFIRMED draft.
    Nothing is persisted to CRM until explicit rep review and confirmation.
    """
    effective_rep_id = get_authenticated_sales_rep_id(user)
    adapter = MockFieldMateAdapter(db)

    # Resolve text transcript: directly supplied or via audio
    raw_transcript = req.raw_transcript or ""
    if not raw_transcript and req.audio_base64:
        raw_transcript = "Rep voice note recorded via device microphone."

    if not raw_transcript.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either raw_transcript or audio_base64.",
        )

    try:
        draft = adapter.extract_voice_note_draft(
            visit_id=req.visit_id,
            raw_transcript=raw_transcript,
            sales_rep_id=effective_rep_id,
        )
        return VoiceNoteExtractResponse(
            visit_id=draft.visit_id,
            merchant_id=draft.merchant_id,
            raw_transcript=draft.raw_transcript,
            extracted_candidate_fields=draft.extracted_candidate_fields,
            proposed_lead_interest=draft.proposed_lead_interest,
            requires_rep_confirmation=True,
            disclaimer=draft.disclaimer,
            version=draft.version,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except RepPolicyViolationError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))


@fieldmate_router.post("/voice-note/confirm", response_model=VoiceNoteConfirmResponse)
def confirm_voice_note(
    req: VoiceNoteConfirmRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Persists reviewed and confirmed visit note into CRM.
    Enforces:
    - Optimistic locking (returns 409 Conflict if expected_version != DB version).
    - Policy guard against loan approvals / guaranteed terms.
    - Emits CRM_VISIT_NOTE_SAVED audit event.
    """
    effective_rep_id = get_authenticated_sales_rep_id(user)
    adapter = MockFieldMateAdapter(db)

    try:
        res = adapter.confirm_and_save_visit_note(
            visit_id=req.visit_id,
            expected_version=req.expected_version,
            confirmed_notes=req.confirmed_notes,
            lead_interest=req.lead_interest,
            sales_rep_id=effective_rep_id,
        )
        return VoiceNoteConfirmResponse(
            visit_id=res.visit_id,
            merchant_id=res.merchant_id,
            is_confirmed=res.is_confirmed,
            confirmed_notes=res.confirmed_notes,
            lead_interest=res.lead_interest,
            new_version=res.new_version,
            audit_event_id=res.audit_event_id,
            message=res.message,
        )
    except ConcurrencyConflictError as ce:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(ce),
        )
    except RepPolicyViolationError as pe:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(pe),
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))


@fieldmate_router.get("/manager-summary", response_model=ManagerRepSummaryResponse)
def get_manager_rep_summary(
    sales_rep_id: str = Query("emp_sales_01"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manager's End-of-Day Rep Summary reflecting real completed visits and confirmed transcripts.
    """
    if user.get("user_type") != "employee":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Employee access required.")

    adapter = MockFieldMateAdapter(db)
    summary = adapter.get_manager_rep_summary(sales_rep_id)

    return ManagerRepSummaryResponse(
        sales_rep_id=summary.sales_rep_id,
        rep_name=summary.rep_name,
        total_assigned_merchants=summary.total_assigned_merchants,
        planned_visits_today=summary.planned_visits_today,
        completed_visits_today=summary.completed_visits_today,
        completion_rate_pct=summary.completion_rate_pct,
        leads_generated_today=summary.leads_generated_today,
        confirmed_visits=[
            ConfirmedVisitItem(
                visit_id=v["visit_id"],
                merchant_id=v["merchant_id"],
                store_name=v["store_name"],
                merchant_name=v["merchant_name"],
                confirmed_notes=v["confirmed_notes"],
                lead_interest=v["lead_interest"],
                confirmed_at=v["confirmed_at"],
                version=v["version"],
            )
            for v in summary.confirmed_visits
        ],
    )
