from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import (
    Merchant,
    MerchantActivityMetric,
    MerchantFollowup,
    Task,
    TaskBucket,
)
from app.api.auth import get_current_user
from app.api.employee import ensure_employee
from app.adapters.revive import MockReviveAdapter
from app.agents.revive import ReviveAgent
from app.tools.revive import ReviveTools
from app.schemas.revive import (
    MerchantHealthKPI,
    MerchantHealthItem,
    MerchantHealthResponse,
    ScanTriggerResponse,
    FollowupResponseRequest,
    FollowupResponseResult,
    SimulateRecoveryRequest,
    SimulateRecoveryResponse,
)

revive_router = APIRouter(tags=["Revive & Merchant Health"])


def map_stage_to_chip(stage: str) -> str:
    stage_upper = stage.upper()
    if stage_upper == "REVIVED":
        return "verified"
    elif stage_upper == "WARM_LEAD":
        return "awaiting_approval"
    elif stage_upper == "FOLLOWUP_SENT":
        return "executed"
    elif stage_upper == "AT_RISK":
        return "needs_human"
    return "pending"


# 1. Employee Web: Merchant Health & Dormancy Overview
@revive_router.get("/employee/revive/merchants", response_model=MerchantHealthResponse)
def get_merchant_health_overview(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_employee(user)

    metrics_rows = (
        db.query(MerchantActivityMetric)
        .join(Merchant, MerchantActivityMetric.merchant_id == Merchant.id)
        .order_by(MerchantActivityMetric.drop_percentage.desc())
        .all()
    )

    items = []
    device_issues = 0
    settlement_issues = 0
    competitor_issues = 0
    followups_sent = 0
    warm_leads = 0
    revived = 0

    for m in metrics_rows:
        store = m.merchant.store_name if m.merchant else "Kirana Store"
        city = m.merchant.city if m.merchant else "Jaipur"

        if m.diagnosed_cause == "DEVICE_ISSUE":
            device_issues += 1
        elif m.diagnosed_cause == "SETTLEMENT_ISSUE":
            settlement_issues += 1
        elif m.diagnosed_cause == "COMPETITOR_OR_DISENGAGEMENT":
            competitor_issues += 1

        if m.revival_stage in ["FOLLOWUP_SENT", "WARM_LEAD"]:
            followups_sent += 1
        if m.revival_stage == "WARM_LEAD":
            warm_leads += 1
        if m.revival_stage == "REVIVED":
            revived += 1

        # Check latest followup
        latest_fol = (
            db.query(MerchantFollowup)
            .filter_by(merchant_id=m.merchant_id)
            .order_by(MerchantFollowup.delivered_at.desc())
            .first()
        )
        fol_data = None
        if latest_fol:
            fol_data = {
                "id": latest_fol.id,
                "cause_type": latest_fol.cause_type,
                "title": latest_fol.message_title,
                "body": latest_fol.message_body,
                "status": latest_fol.status,
                "offer_code": latest_fol.offer_code,
                "offer_details": latest_fol.offer_details,
                "handed_off_to": latest_fol.handed_off_to,
                "task_id": latest_fol.task_id,
            }

        items.append(
            MerchantHealthItem(
                id=m.id,
                merchant_id=m.merchant_id,
                store_name=store,
                city=city,
                baseline_daily_tx_count=m.baseline_daily_tx_count,
                baseline_daily_volume_paise=m.baseline_daily_volume_paise,
                baseline_daily_volume_inr=f"₹{m.baseline_daily_volume_paise / 100:,.2f}",
                recent_daily_tx_count=m.recent_daily_tx_count,
                recent_daily_volume_paise=m.recent_daily_volume_paise,
                recent_daily_volume_inr=f"₹{m.recent_daily_volume_paise / 100:,.2f}",
                drop_percentage=m.drop_percentage,
                health_status=m.health_status,
                diagnosed_cause=m.diagnosed_cause,
                revival_stage=m.revival_stage,
                chip_status=map_stage_to_chip(m.revival_stage),
                last_scanned_at=m.last_scanned_at.strftime("%Y-%m-%d %H:%M:%S") if m.last_scanned_at else "Today",
                recovered_at=m.recovered_at.strftime("%Y-%m-%d %H:%M:%S") if m.recovered_at else None,
                active_followup=fol_data,
            )
        )

    kpi = MerchantHealthKPI(
        total_at_risk=len([m for m in metrics_rows if m.health_status in ["AT_RISK", "DORMANT"]]),
        device_issues_count=device_issues,
        settlement_issues_count=settlement_issues,
        competitor_issues_count=competitor_issues,
        followups_sent_count=followups_sent,
        warm_leads_count=warm_leads,
        revived_count=revived,
    )

    return MerchantHealthResponse(kpi=kpi, merchants=items)


# 2. Manual Scan Trigger (On-Demand Scan for Demo & Testing)
@revive_router.post("/employee/revive/scan", response_model=ScanTriggerResponse)
def trigger_revive_dormancy_scan(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_employee(user)
    agent = ReviveAgent(db)
    scan_res = agent.scan_all_at_risk_merchants(threshold=40)

    return ScanTriggerResponse(
        success=True,
        scanned_count=scan_res["total_at_risk_scanned"],
        message=f"Dormancy scan executed across {scan_res['total_at_risk_scanned']} at-risk merchants.",
        results=scan_res["results"],
    )


# 3. Merchant Mobile: Get Active Retention Check-in
@revive_router.get("/merchant/revive/active-checkin")
def get_merchant_active_checkin(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    merchant_id = user.get("sub", "mer_sharma_kirana")
    adapter = MockReviveAdapter(db)
    fol = adapter.get_active_followup(merchant_id)
    if not fol:
        return {"has_checkin": False}

    fol_dump = fol.model_dump()
    return {
        "has_checkin": True,
        "followup": fol_dump,
        "checkin": fol_dump,
    }


# 4. Merchant Mobile: Respond to Followup (Accept / Dismiss)
@revive_router.post("/merchant/revive/{followup_id}/respond", response_model=FollowupResponseResult)
def respond_to_merchant_followup(
    followup_id: str,
    req: FollowupResponseRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    merchant_id = user.get("sub", "mer_sharma_kirana")
    fol = db.query(MerchantFollowup).filter_by(id=followup_id).first()
    if not fol:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Followup not found.")

    adapter = MockReviveAdapter(db)
    tools = ReviveTools(db=db)

    updated_fol = adapter.respond_to_followup(followup_id, req.decision)
    if not updated_fol:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to process response.")

    task_id = None
    if req.decision.upper() == "ACCEPT":
        # Create warm-lead task for Sales Rep with full Kirana context
        merchant = db.query(Merchant).filter_by(id=merchant_id).first()
        store_name = merchant.store_name if merchant else "Kirana Store"
        lead_res = tools.create_retention_review(
            merchant_id=merchant_id,
            followup_id=followup_id,
            notes=(
                f"Merchant {store_name} ({merchant_id}) accepted Kirana Booster retention offer. "
                f"Soundbox and payouts are healthy. Sales Rep assigned to deliver fresh QR standee, "
                f"review volume metrics, and onboard 0% MDR offer."
            ),
            actor_id=merchant_id,
        )
        task_id = lead_res.get("task_id")
        msg = f"Offer activated! Your dedicated Paytm Sales Rep has been assigned to visit {store_name}."
    else:
        msg = "Offer dismissed. Thank you for your feedback."

    return FollowupResponseResult(
        success=True,
        followup_id=followup_id,
        status=updated_fol.status,
        task_id=task_id,
        message=msg,
    )


# 5. Demo Simulated Recovery Endpoint (Proves Invariant: Revived ONLY after fresh volume rebound)
@revive_router.post("/demo/revive/{merchant_id}/simulate-recovery", response_model=SimulateRecoveryResponse)
def simulate_merchant_recovery(
    merchant_id: str,
    req: SimulateRecoveryRequest,
    db: Session = Depends(get_db),
):
    tools = ReviveTools(db=db)
    res = tools.verify_merchant_revival(
        merchant_id=merchant_id,
        simulated_daily_volume_paise=req.new_daily_volume_paise,
        simulated_daily_tx_count=req.new_daily_tx_count,
    )
    if not res.get("success"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant metric not found.")

    return SimulateRecoveryResponse(
        success=True,
        merchant_id=merchant_id,
        health_status=res["health_status"],
        revival_stage=res["revival_stage"],
        drop_percentage=res["drop_percentage"],
        is_revived=res["is_revived"],
        message=res["message"],
    )
