import pytest
from datetime import datetime, timezone
from starlette.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.db.models import (
    Merchant,
    MerchantActivityMetric,
    MerchantFollowup,
    Task,
    TaskBucket,
    AuditEvent,
    Device,
    Settlement,
)
from app.adapters.revive import MockReviveAdapter
from app.adapters.device import MockDeviceAdapter
from app.adapters.settlement import MockSettlementAdapter
from app.tools.revive import ReviveTools
from app.agents.revive import ReviveAgent
from app.agents.orchestrator import SaathiBrainOrchestrator


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def merchant_token(client):
    res = client.post("/auth/merchant/verify-otp", json={"phone": "+919876543210", "otp": "123456"})
    return res.json()["access_token"]


@pytest.fixture
def employee_token(client):
    res = client.post("/auth/employee/login", json={"email": "support@paytm.demo", "password": "Demo@1234"})
    return res.json()["access_token"]


@pytest.fixture(autouse=True)
def ensure_seed_metrics(db: Session):
    """
    Ensures all 3 test kiranas have deterministic decline metrics before each test.
    """
    metrics = {
        "mer_gupta_electronics": {"drop": 92, "recent": 160000, "base": 2000000, "cause": "DEVICE_ISSUE", "stage": "AT_RISK"},
        "mer_verma_sweets": {"drop": 79, "recent": 250000, "base": 1200000, "cause": "SETTLEMENT_ISSUE", "stage": "AT_RISK"},
        "mer_sharma_kirana": {"drop": 70, "recent": 285000, "base": 950000, "cause": "COMPETITOR_OR_DISENGAGEMENT", "stage": "FOLLOWUP_SENT"},
    }
    for m_id, data in metrics.items():
        row = db.query(MerchantActivityMetric).filter_by(merchant_id=m_id).first()
        if row:
            row.drop_percentage = data["drop"]
            row.recent_daily_volume_paise = data["recent"]
            row.baseline_daily_volume_paise = data["base"]
            row.health_status = "AT_RISK"
            row.diagnosed_cause = data["cause"]
            row.revival_stage = data["stage"]
            row.recovered_at = None

    # Ensure device SB-DEL-404 is OFFLINE
    d_gupta = db.query(Device).filter_by(serial_number="SB-DEL-404").first()
    if d_gupta:
        d_gupta.status = "OFFLINE"

    # Ensure device SB-JAI-101 is ONLINE
    d_sharma = db.query(Device).filter_by(serial_number="SB-JAI-101").first()
    if d_sharma:
        d_sharma.status = "ONLINE"

    # Ensure settlement status for pure isolation of drop causes:
    # Verma Sweets has active DISCREPANCY; Sharma Kirana has resolved/disputed settlement
    s_sharma = db.query(Settlement).filter_by(id="sett_sharma_20261027").first()
    if s_sharma:
        s_sharma.status = "DISPUTED"

    s_verma = db.query(Settlement).filter_by(id="sett_verma_20261027").first()
    if s_verma:
        s_verma.status = "DISCREPANCY"

    # Ensure Sharma Kirana has an active delivered followup
    fol = db.query(MerchantFollowup).filter_by(merchant_id="mer_sharma_kirana").first()
    if fol:
        fol.status = "DELIVERED"
        fol.merchant_response = None
        fol.responded_at = None

    db.commit()
    yield


# ==============================================================================
# TEST 1: Revive Adapter decline computation & metric lookups
# ==============================================================================
def test_revive_adapter_decline_and_metrics(db: Session):
    adapter = MockReviveAdapter(db)

    # 1. Verify all 3 seeded merchants with distinct drops
    m_gupta = adapter.get_merchant_metrics("mer_gupta_electronics")
    assert m_gupta is not None
    assert m_gupta.merchant_id == "mer_gupta_electronics"
    assert m_gupta.drop_percentage == 92
    assert m_gupta.health_status == "AT_RISK"
    assert m_gupta.baseline_daily_volume_paise == 2000000  # ₹20,000
    assert m_gupta.recent_daily_volume_paise == 160000     # ₹1,600

    m_verma = adapter.get_merchant_metrics("mer_verma_sweets")
    assert m_verma is not None
    assert m_verma.merchant_id == "mer_verma_sweets"
    assert m_verma.drop_percentage == 79
    assert m_verma.health_status == "AT_RISK"
    assert m_verma.baseline_daily_volume_paise == 1200000  # ₹12,000
    assert m_verma.recent_daily_volume_paise == 250000     # ₹2,500

    m_sharma = adapter.get_merchant_metrics("mer_sharma_kirana")
    assert m_sharma is not None
    assert m_sharma.merchant_id == "mer_sharma_kirana"
    assert m_sharma.drop_percentage == 70
    assert m_sharma.health_status == "AT_RISK"
    assert m_sharma.baseline_daily_volume_paise == 950000  # ₹9,500
    assert m_sharma.recent_daily_volume_paise == 285000    # ₹2,850

    # 2. Threshold filtering (>= 40% decline)
    at_risk = adapter.list_at_risk_merchants(threshold_drop_percentage=40)
    assert len(at_risk) >= 3
    for item in at_risk:
        assert item.drop_percentage >= 40


# ==============================================================================
# TEST 2: Branch 1 - Offline Device Issue -> Handoff to Fix Agent
# ==============================================================================
def test_revive_branch_1_device_issue_handoff(db: Session):
    agent = ReviveAgent(db)
    result = agent.run("mer_gupta_electronics")

    assert result["success"] is True
    assert result["diagnosed_cause"] == "DEVICE_ISSUE"
    assert result["handoff_agent"] == "FIX"
    assert result["action_taken"] == "HANDOFF_TO_FIX_AGENT"

    # Evidence handed off from DeviceAdapter
    assert "SB-DEL-404" in result["handoff_evidence"]["serial_number"]
    assert result["handoff_evidence"]["status"] == "OFFLINE"

    # Follow-up reflects device check-in, NOT an unapproved commercial discount
    assert "Soundbox" in result["followup"]["message_title"]
    assert result["followup"]["handed_off_to"] == "FIX"

    # Metric updated to reflect diagnosis
    metric = db.query(MerchantActivityMetric).filter_by(merchant_id="mer_gupta_electronics").first()
    assert metric.diagnosed_cause == "DEVICE_ISSUE"


# ==============================================================================
# TEST 3: Branch 2 - Settlement Discrepancy -> Handoff to Reconcile Agent
# ==============================================================================
def test_revive_branch_2_settlement_issue_handoff(db: Session):
    agent = ReviveAgent(db)
    result = agent.run("mer_verma_sweets")

    assert result["success"] is True
    assert result["diagnosed_cause"] == "SETTLEMENT_ISSUE"
    assert result["handoff_agent"] == "RECONCILE"
    assert result["action_taken"] == "HANDOFF_TO_RECONCILE_AGENT"

    # Evidence handed off from SettlementAdapter
    assert result["handoff_evidence"]["has_discrepancy"] is True
    assert result["handoff_evidence"]["discrepancy_paise"] < 0
    assert result["handoff_evidence"]["discrepancy_inr"] == "₹940.00"

    # Follow-up reflects settlement support
    assert "Settlement" in result["followup"]["message_title"]
    assert result["followup"]["handed_off_to"] == "RECONCILE"

    # Metric updated to reflect diagnosis
    metric = db.query(MerchantActivityMetric).filter_by(merchant_id="mer_verma_sweets").first()
    assert metric.diagnosed_cause == "SETTLEMENT_ISSUE"


# ==============================================================================
# TEST 4: Branch 3 - Non-Technical Drop -> Retention Offer (Kirana Booster)
# ==============================================================================
def test_revive_branch_3_retention_offer(db: Session):
    agent = ReviveAgent(db)
    result = agent.run("mer_sharma_kirana")

    assert result["success"] is True
    assert result["diagnosed_cause"] == "COMPETITOR_OR_DISENGAGEMENT"
    assert result["handoff_agent"] is None
    assert result["action_taken"] == "OFFER_RETENTION_BOOSTER"

    # Valid retention offer created
    assert result["followup"]["offer_code"] == "BOOSTER30"
    assert "Kirana Booster" in result["followup"]["message_title"]
    assert result["followup"]["status"] == "DELIVERED"

    # Core Invariant: Revival stage is NOT REVIVED
    assert result["revival_stage"] == "FOLLOWUP_SENT"
    metric = db.query(MerchantActivityMetric).filter_by(merchant_id="mer_sharma_kirana").first()
    assert metric.revival_stage == "FOLLOWUP_SENT"
    assert metric.recovered_at is None


# ==============================================================================
# TEST 5: Merchant Accepts Offer -> Warm-Lead Task for Sales Rep (Amit V.)
# ==============================================================================
def test_merchant_accepts_offer_creates_warm_lead(db: Session):
    adapter = MockReviveAdapter(db)

    # Get active delivered followup for Sharma Kirana
    followup = adapter.get_active_followup("mer_sharma_kirana")
    assert followup is not None
    followup_id = followup.id

    # Merchant responds with ACCEPT
    rec = adapter.respond_to_followup(followup_id, decision="ACCEPT")
    assert rec is not None
    assert rec.status == "ACCEPTED"

    # Create warm-lead retention review task for sales rep
    tools = ReviveTools(db)
    lead_res = tools.create_retention_review(
        merchant_id="mer_sharma_kirana",
        followup_id=followup_id,
        notes="Merchant accepted 0% MDR offer; dispatch field rep.",
    )
    assert lead_res["success"] is True
    task_id = lead_res["task_id"]

    # Verify Task record in database
    task = db.query(Task).filter_by(id=task_id).first()
    assert task is not None
    assert "Warm Lead" in task.title
    assert task.assigned_to == "Amit V. (Sales Rep)"
    assert task.priority == "HIGH"
    assert task.bucket == TaskBucket.NEEDS_HUMAN

    # Verify Revival stage is WARM_LEAD (Honest invariant: still NOT REVIVED)
    metric = adapter.get_merchant_metrics("mer_sharma_kirana")
    assert metric.revival_stage == "WARM_LEAD"
    assert metric.recovered_at is None


# ==============================================================================
# TEST 6: Invariant Test - "Follow-up Sent" ≠ "Revived"
# ==============================================================================
def test_core_invariant_followup_sent_does_not_equal_revived(db: Session):
    adapter = MockReviveAdapter(db)

    # A followup sent or accepted MUST NOT mark the merchant as REVIVED
    metric = adapter.get_merchant_metrics("mer_sharma_kirana")
    assert metric.revival_stage in ("FOLLOWUP_SENT", "WARM_LEAD")
    assert metric.health_status == "AT_RISK"
    assert metric.recovered_at is None

    # An insufficient volume increase (e.g., ₹4,000 vs baseline ₹9,500 - only 42%) must NOT revive
    rec = adapter.record_merchant_recovery(
        merchant_id="mer_sharma_kirana",
        new_daily_volume_paise=400000,
        new_daily_tx_count=15,
    )
    assert rec is not None
    assert rec.health_status == "AT_RISK"
    assert rec.revival_stage != "REVIVED"
    assert rec.recovered_at is None

    # Merchant remains AT_RISK in DB
    metric_after = adapter.get_merchant_metrics("mer_sharma_kirana")
    assert metric_after.health_status == "AT_RISK"
    assert metric_after.revival_stage != "REVIVED"
    assert metric_after.recovered_at is None


# ==============================================================================
# TEST 7: Invariant Test - Merchant ONLY Revived After Metrics Recheck (>=80%)
# ==============================================================================
def test_core_invariant_verified_revival_after_metrics_recheck(db: Session):
    adapter = MockReviveAdapter(db)

    # Baseline for Sharma Kirana is ₹9,500 (950,000 paise).
    # 80% is ₹7,600 (760,000 paise). We supply ₹10,000 (1,000,000 paise).
    recovery = adapter.record_merchant_recovery(
        merchant_id="mer_sharma_kirana",
        new_daily_volume_paise=1000000,  # ₹10,000.00
        new_daily_tx_count=40,
    )
    assert recovery is not None
    assert recovery.revival_stage == "REVIVED"
    assert recovery.health_status == "HEALTHY"
    assert recovery.recovered_at is not None

    # Authoritative DB verification
    metric = adapter.get_merchant_metrics("mer_sharma_kirana")
    assert metric.health_status == "HEALTHY"
    assert metric.revival_stage == "REVIVED"
    assert metric.recovered_at is not None
    assert metric.drop_percentage == 0


# ==============================================================================
# TEST 8: Disallowed Actions & Policy Engine Protection
# ==============================================================================
def test_disallowed_actions_policy_gating(db: Session):
    tools = ReviveTools(db)

    # Attempting to create an unapproved fee waiver/discount
    res = tools.create_merchant_followup(
        merchant_id="mer_gupta_electronics",
        cause_type="COMPETITOR_OR_DISENGAGEMENT",
        message_title="Free Money 100% Fee Waiver",
        message_body="We give you free 100% waiver forever",
        offer_code="ILLEGAL_100_PERCENT",
    )
    # PolicyEngine rejects unauthorized discount codes
    assert res["success"] is False
    assert "Policy violation" in res.get("message", "") or "disallowed" in res.get("message", "")


# ==============================================================================
# TEST 9: Employee Console Endpoints (KPI & Manual Scan Trigger)
# ==============================================================================
def test_employee_revive_api_endpoints(client: TestClient, employee_token: str):
    headers = {"Authorization": f"Bearer {employee_token}"}

    # 1. GET /employee/revive/merchants
    res = client.get("/employee/revive/merchants", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert "kpi" in data
    assert "merchants" in data
    kpi = data["kpi"]
    assert kpi["total_at_risk"] >= 3
    assert kpi["device_issues_count"] >= 1
    assert kpi["settlement_issues_count"] >= 1

    # Check merchant item fields
    merchants = data["merchants"]
    sharma = next((m for m in merchants if m["merchant_id"] == "mer_sharma_kirana"), None)
    assert sharma is not None
    assert "baseline_daily_volume_inr" in sharma
    assert "recent_daily_volume_inr" in sharma
    assert "drop_percentage" in sharma
    assert "chip_status" in sharma

    # 2. POST /employee/revive/scan (Manual trigger)
    scan_res = client.post("/employee/revive/scan", headers=headers)
    assert scan_res.status_code == 200
    scan_data = scan_res.json()
    assert scan_data["success"] is True
    assert scan_data["scanned_count"] >= 3
    assert len(scan_data["results"]) >= 3


# ==============================================================================
# TEST 10: Merchant Active Checkin, Response, & Recovery Simulation API
# ==============================================================================
def test_merchant_checkin_and_recovery_flow(client: TestClient, merchant_token: str):
    headers = {"Authorization": f"Bearer {merchant_token}"}

    # 1. GET /merchant/revive/active-checkin
    res = client.get("/merchant/revive/active-checkin", headers=headers)
    assert res.status_code == 200
    checkin = res.json()
    assert checkin["has_checkin"] is True
    assert checkin["checkin"] is not None
    followup_id = checkin["checkin"]["id"]

    # 2. POST /merchant/revive/{followup_id}/respond (DISMISS option test)
    dismiss_res = client.post(
        f"/merchant/revive/{followup_id}/respond",
        headers=headers,
        json={"decision": "DISMISS"},
    )
    assert dismiss_res.status_code == 200
    assert dismiss_res.json()["status"] == "DISMISSED"

    # 3. POST /demo/revive/{merchant_id}/simulate-recovery
    sim_res = client.post(
        "/demo/revive/mer_sharma_kirana/simulate-recovery",
        json={"new_daily_volume_paise": 1200000, "new_daily_tx_count": 45},
    )
    assert sim_res.status_code == 200
    sim_data = sim_res.json()
    assert sim_data["success"] is True
    assert sim_data["is_revived"] is True
    assert sim_data["revival_stage"] == "REVIVED"


# ==============================================================================
# TEST 11: Saathi Brain Orchestrator Revive Intent & Voice
# ==============================================================================
def test_orchestrator_revive_intent_and_voice(client: TestClient, merchant_token: str):
    headers = {"Authorization": f"Bearer {merchant_token}"}

    # Send natural language dormancy query to Saathi Chat
    res = client.post(
        "/merchant/chat/message",
        headers=headers,
        json={"message": "Why is my payment volume down so much this week? How can Paytm help me revive sales?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["agent"] == "REVIVE"
    assert "Kirana Booster" in data["reply"] or "volume" in data["reply"].lower()
    assert data["speech_audio_base64"] is not None
    assert data["checkin_card"] is not None
