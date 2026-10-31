from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import AuditEvent
from app.agents.handoff_demo import HandoffDemoService
from app.schemas.orchestrator import (
    HandoffStepRequest,
    HandoffStepResponse,
    HandoffChainStatusResponse,
)

router = APIRouter(tags=["Multi-Agent Handoff Demo"])


class ResetHandoffRequest(BaseModel):
    merchant_id: str = "mer_singh_automobiles"


class RunAllHandoffRequest(BaseModel):
    merchant_id: str = "mer_singh_automobiles"
    actor_id: str = "demo_narrator"
    pause_seconds: float = 0.1


@router.post("/demo/handoff/step", response_model=HandoffStepResponse)
def execute_handoff_step(
    payload: HandoffStepRequest,
    db: Session = Depends(get_db),
):
    """
    Executes a single step (1-6) of the cross-agent handoff chain.
    Writes real audit_events for live narration.
    """
    svc = HandoffDemoService(db)
    try:
        return svc.execute_step(
            step=payload.step,
            merchant_id=payload.merchant_id,
            actor_id=payload.actor_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Handoff step failed: {str(e)}")


@router.post("/demo/handoff/run-all", response_model=List[HandoffStepResponse])
def run_all_handoff_steps(
    payload: RunAllHandoffRequest,
    db: Session = Depends(get_db),
):
    """
    Runs all 6 steps of the scripted cross-agent chain end-to-end.
    """
    svc = HandoffDemoService(db)
    try:
        return svc.run_all(
            merchant_id=payload.merchant_id,
            actor_id=payload.actor_id,
            pause_between_steps=payload.pause_seconds,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Handoff run failed: {str(e)}")


@router.post("/demo/handoff/reset")
def reset_handoff_demo(
    payload: ResetHandoffRequest,
    db: Session = Depends(get_db),
):
    """
    Resets the device, metric, visit, and task state to baseline.
    """
    svc = HandoffDemoService(db)
    return svc.reset_demo(merchant_id=payload.merchant_id)


@router.get("/demo/handoff/status", response_model=HandoffChainStatusResponse)
def get_handoff_status(
    merchant_id: str = Query("mer_singh_automobiles"),
    db: Session = Depends(get_db),
):
    """
    Returns current health, device status, and step in the handoff chain.
    """
    svc = HandoffDemoService(db)
    return svc.get_status(merchant_id=merchant_id)


@router.get("/employee/handoff/timeline")
def get_handoff_timeline(
    merchant_id: str = Query("mer_singh_automobiles"),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Handoff Timeline sourced strictly from real audit_events rows.
    Shows the cross-agent sequence (Revive -> Fix -> FieldMate -> Revive).
    """
    # Fetch audit events matching handoff actors or this merchant
    events = (
        db.query(AuditEvent)
        .filter(
            (AuditEvent.target.like(f"%{merchant_id}%"))
            | (AuditEvent.action.like("%Saathi routed to%"))
            | (AuditEvent.action.like("%REVIVE%"))
            | (AuditEvent.action.like("%FIX%"))
            | (AuditEvent.action.like("%FIELDMATE%"))
            | (AuditEvent.action.like("%TECHNICIAN%"))
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "merchant_id": merchant_id,
        "count": len(events),
        "events": [
            {
                "id": ev.id,
                "actor": ev.actor,
                "action": ev.action,
                "target": ev.target,
                "result": ev.result,
                "policy_decision_id": ev.policy_decision_id,
                "idempotency_key": ev.idempotency_key,
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
                "environment": ev.environment,
            }
            for ev in events
        ],
    }
