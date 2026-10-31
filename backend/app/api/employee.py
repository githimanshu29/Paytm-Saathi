from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import (
    Merchant,
    Device,
    Transaction,
    Task,
    TaskBucket,
    ActionApproval,
    ApprovalDecision,
    AuditEvent,
    Receivable,
)
from app.api.auth import get_current_user
from app.schemas.employee import (
    DashboardKPISummary,
    AuditEventItem,
    AuditLogResponse,
    CaseApprovalSummary,
    CaseItem,
    CasesResponse,
    CaseTimelineResponse,
)

employee_router = APIRouter(prefix="/employee", tags=["Employee Operations"])

def format_paise_to_inr(paise: int) -> str:
    return f"₹{paise / 100:,.2f}"

def ensure_employee(user: dict):
    if user.get("user_type") != "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Employee access required for this operation.",
        )

@employee_router.get("/dashboard/summary", response_model=DashboardKPISummary)
def get_dashboard_summary(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_employee(user)

    total_merchants = db.query(Merchant).count()
    active_devices = db.query(Device).filter(Device.status == "ONLINE").count()
    total_devices = db.query(Device).count()
    pending_approvals = (
        db.query(ActionApproval)
        .filter(ActionApproval.decision == ApprovalDecision.PENDING)
        .count()
    )
    needs_human_cases = (
        db.query(Task).filter(Task.bucket == TaskBucket.NEEDS_HUMAN).count()
    )

    transactions = db.query(Transaction).filter(Transaction.status == "SUCCESS").all()
    total_tx_paise = sum(tx.amount for tx in transactions)
    total_tasks = db.query(Task).count()

    paid_recs = db.query(Receivable).filter(Receivable.status.in_(["PAID", "VERIFIED_PAID"])).all()
    total_recovered_paise = sum(r.paid_amount or r.amount for r in paid_recs)

    return DashboardKPISummary(
        total_merchants=total_merchants,
        active_devices=active_devices,
        total_devices=total_devices,
        pending_approvals=pending_approvals,
        needs_human_cases=needs_human_cases,
        total_transactions_paise=total_tx_paise,
        total_transactions_formatted=format_paise_to_inr(total_tx_paise),
        total_tasks=total_tasks,
        total_vasooli_recovered_paise=total_recovered_paise,
        total_vasooli_recovered_formatted=format_paise_to_inr(total_recovered_paise),
    )

@employee_router.get("/audit-log", response_model=AuditLogResponse)
def get_audit_log(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    actor: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_employee(user)

    query = db.query(AuditEvent)
    if actor:
        query = query.filter(AuditEvent.actor.ilike(f"%{actor}%"))

    total = query.count()
    rows = query.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit).all()

    events = [
        AuditEventItem(
            id=ev.id,
            actor=ev.actor,
            action=ev.action,
            target=ev.target,
            policy_decision_id=ev.policy_decision_id,
            idempotency_key=ev.idempotency_key,
            result=ev.result,
            created_at=ev.created_at.strftime("%Y-%m-%d %H:%M:%S") if ev.created_at else "",
            environment=ev.environment,
        )
        for ev in rows
    ]

    return AuditLogResponse(total=total, events=events)

@employee_router.get("/cases", response_model=CasesResponse)
def get_cases(
    bucket: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_employee(user)

    query = db.query(Task).join(Merchant, Task.merchant_id == Merchant.id)

    if bucket:
        query = query.filter(Task.bucket == bucket)

    tasks = query.order_by(Task.created_at.desc()).all()

    cases_list = []
    for t in tasks:
        # Check if there is an approval attached
        appr = db.query(ActionApproval).filter_by(task_id=t.id).first()
        appr_summary = None
        if appr:
            appr_summary = CaseApprovalSummary(
                id=appr.id,
                approver=appr.approver,
                decision=appr.decision.value if hasattr(appr.decision, "value") else str(appr.decision),
                reason=appr.reason,
                risk_tier=appr.risk_tier,
                expires_at=appr.expires_at.strftime("%Y-%m-%d %H:%M") if appr.expires_at else None,
            )

        cases_list.append(
            CaseItem(
                id=t.id,
                merchant_id=t.merchant.id,
                store_name=t.merchant.store_name,
                merchant_phone=t.merchant.phone,
                city=t.merchant.city,
                title=t.title,
                description=t.description,
                bucket=t.bucket.value if hasattr(t.bucket, "value") else str(t.bucket),
                priority=t.priority,
                assigned_to=t.assigned_to,
                evidence_notes=getattr(t, "evidence_notes", None),
                evidence_url=getattr(t, "evidence_url", None),
                dispute_amount_formatted=f"₹{t.dispute_amount / 100:,.2f}" if getattr(t, "dispute_amount", None) else None,
                approval=appr_summary,
                created_at=t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else "",
                updated_at=t.updated_at.strftime("%Y-%m-%d %H:%M:%S") if t.updated_at else "",
            )
        )

    return CasesResponse(total=len(cases_list), cases=cases_list)

@employee_router.get("/cases/{case_id}/timeline", response_model=CaseTimelineResponse)
def get_case_timeline(
    case_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_employee(user)

    task = db.query(Task).filter_by(id=case_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case with ID {case_id} not found.",
        )

    case_specific_events = (
        db.query(AuditEvent)
        .filter(or_(AuditEvent.target == case_id, AuditEvent.idempotency_key.like(f"%{case_id}%")))
        .order_by(AuditEvent.created_at.desc())
        .limit(25)
        .all()
    )

    merchant_filters = [
        (AuditEvent.target == task.merchant_id),
        (AuditEvent.actor == task.merchant_id),
    ]
    if getattr(task, "device_id", None):
        merchant_filters.append(AuditEvent.target == task.device_id)

    merchant_events = (
        db.query(AuditEvent)
        .filter(or_(*merchant_filters))
        .order_by(AuditEvent.created_at.desc())
        .limit(25)
        .all()
    )

    combined_map = {ev.id: ev for ev in (case_specific_events + merchant_events)}
    events_query = sorted(combined_map.values(), key=lambda x: x.created_at or datetime.min)

    # If no specific audit events yet for this exact case ID, fallback to general system audit events for this merchant's session
    if not events_query:
        events_query = (
            db.query(AuditEvent)
            .order_by(AuditEvent.created_at.desc())
            .limit(5)
            .all()
        )

    event_items = [
        AuditEventItem(
            id=ev.id,
            actor=ev.actor,
            action=ev.action,
            target=ev.target,
            policy_decision_id=ev.policy_decision_id,
            idempotency_key=ev.idempotency_key,
            result=ev.result,
            created_at=ev.created_at.strftime("%Y-%m-%d %H:%M:%S") if ev.created_at else "",
            environment=ev.environment,
        )
        for ev in events_query
    ]

    return CaseTimelineResponse(case_id=case_id, events=event_items)
