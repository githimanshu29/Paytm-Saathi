import pytest
from datetime import datetime
from starlette.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.db.models import Task, AuditEvent, Settlement, TransactionFee, Chargeback
from app.adapters.settlement import MockSettlementAdapter
from app.tools.reconcile import ReconcileTools
from app.agents.reconcile import ReconcileAgent
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


# TEST 1: Adapter lookup for normal and anomalous settlement records
def test_settlement_adapter_normal_and_anomalous_lookup(db: Session):
    adapter = MockSettlementAdapter(db)

    # 1. Normal Day: 2026-10-28
    rec_normal = adapter.get_settlement("mer_sharma_kirana", "2026-10-28")
    assert rec_normal is not None
    assert rec_normal.settlement_date == "2026-10-28"
    assert rec_normal.gross_sales == 1000000  # ₹10,000.00
    assert rec_normal.refunds == 50000        # ₹500.00
    assert rec_normal.fees == 30000           # ₹300.00
    assert rec_normal.chargebacks == 0        # ₹0.00
    assert rec_normal.net_expected == 920000  # ₹9,200.00
    assert rec_normal.net_settled == 920000   # ₹9,200.00
    assert rec_normal.discrepancy == 0
    assert rec_normal.status == "RECONCILED"
    assert rec_normal.bank_utr == "ICICINODAL99281028"

    # 2. Anomalous Day: 2026-10-27
    rec_anom = adapter.get_settlement("mer_sharma_kirana", "2026-10-27")
    assert rec_anom is not None
    assert rec_anom.settlement_date == "2026-10-27"
    assert rec_anom.gross_sales == 1500000   # ₹15,000.00
    assert rec_anom.refunds == 100000        # ₹1,000.00
    assert rec_anom.fees == 45000            # ₹450.00
    assert rec_anom.chargebacks == 55000     # ₹550.00
    assert rec_anom.net_expected == 1300000  # ₹13,000.00
    assert rec_anom.net_settled == 1180000   # ₹11,800.00
    assert rec_anom.discrepancy == -120000   # Shortfall of ₹1,200.00
    assert rec_anom.status in ("DISCREPANCY", "DISPUTED")
    assert rec_anom.bank_utr == "ICICINODAL99271027"


# TEST 2: Deterministic code-based integer arithmetic (zero float tolerance)
def test_deterministic_integer_arithmetic_zero_float():
    tools = ReconcileTools()

    # Normal day values (in integer paise)
    res_normal = tools.calculate_settlement_difference(
        gross_sales_paise=1000000,
        refunds_paise=50000,
        fees_paise=30000,
        chargebacks_paise=0,
        net_settled_paise=920000,
    )
    assert res_normal["is_reconciled"] is True
    assert res_normal["difference_paise"] == 0
    assert res_normal["net_expected_paise"] == 920000
    assert res_normal["net_settled_paise"] == 920000
    assert res_normal["difference_inr"] == "₹0.00"
    assert res_normal["direction"] == "BALANCED"

    # Anomalous day values (in integer paise)
    res_anom = tools.calculate_settlement_difference(
        gross_sales_paise=1500000,
        refunds_paise=100000,
        fees_paise=45000,
        chargebacks_paise=55000,
        net_settled_paise=1180000,
    )
    assert res_anom["is_reconciled"] is False
    assert res_anom["difference_paise"] == -120000
    assert res_anom["net_expected_paise"] == 1300000
    assert res_anom["net_settled_paise"] == 1180000
    assert res_anom["difference_inr"] == "₹1,200.00"
    assert res_anom["direction"] == "SHORTFALL"


# TEST 3: Tools extract breakdown line items
def test_reconcile_tools_get_settlement_line_items(db: Session):
    tools = ReconcileTools(db=db)
    items = tools.get_settlement_line_items(
        merchant_id="mer_sharma_kirana",
        settlement_date="2026-10-28",
        execution_id="test_exec_001",
        actor_id="test_runner",
    )
    assert items["settlement_date"] == "2026-10-28"
    assert len(items["fee_items"]) >= 2  # MDR fee + Soundbox rental fee
    assert any("MDR" in f["fee_type"] for f in items["fee_items"])
    assert any("SOUNDBOX" in f["fee_type"] for f in items["fee_items"])
    assert len(items["refund_transactions"]) >= 1
    assert items["refund_transactions"][0]["amount"] == 50000


# TEST 4: Normal day NEVER produces a false dispute
def test_normal_day_never_produces_false_dispute(db: Session):
    # Count existing dispute tasks before run
    initial_disputes_count = db.query(Task).filter(
        Task.merchant_id == "mer_sharma_kirana",
        Task.title.like("%Settlement Dispute%2026-10-28%"),
    ).count()

    agent = ReconcileAgent(db=db)
    result = agent.run(
        merchant_id="mer_sharma_kirana",
        query_text="Why does yesterday settlement 2026-10-28 not match?",
        settlement_date="2026-10-28",
        actor_id="test_merchant",
    )

    assert result["agent"] == "RECONCILE"
    assert result["branch"] == "FULLY_RECONCILED"
    assert result["chip_status"] == "verified"
    assert result["breakdown_card"] is not None
    assert result["breakdown_card"]["is_reconciled"] is True
    assert result["breakdown_card"]["discrepancy"] == "₹0.00"
    assert result["breakdown_card"]["dispute_case_id"] is None
    assert "reconciles completely" in result["agent_reply"]
    assert "₹9,200.00" in result["agent_reply"]

    # Verify database: NO new dispute task was created for this normal day
    final_disputes_count = db.query(Task).filter(
        Task.merchant_id == "mer_sharma_kirana",
        Task.title.like("%Settlement Dispute%2026-10-28%"),
    ).count()
    assert final_disputes_count == initial_disputes_count


# TEST 5: Anomalous day produces exact-match dispute amount
def test_anomalous_day_produces_exact_match_dispute(db: Session):
    agent = ReconcileAgent(db=db)
    result = agent.run(
        merchant_id="mer_sharma_kirana",
        query_text="Explain 27 Oct settlement, payout received is lower than expected",
        settlement_date="2026-10-27",
        actor_id="test_merchant",
    )

    assert result["agent"] == "RECONCILE"
    assert result["branch"] == "ANOMALY_DISPUTE_FILED"
    assert result["chip_status"] == "needs_human"
    assert result["breakdown_card"] is not None
    assert result["breakdown_card"]["is_reconciled"] is False
    assert result["breakdown_card"]["discrepancy"] == "-₹1,200.00"
    assert result["breakdown_card"]["dispute_case_id"] is not None

    dispute_task_id = result["breakdown_card"]["dispute_case_id"]

    # Check task in DB
    task = db.query(Task).filter_by(id=dispute_task_id).first()
    assert task is not None
    assert task.bucket == "needs_human"
    assert task.dispute_amount == 120000  # Exact ₹1,200.00 shortfall in integer minor units
    assert task.priority == "HIGH"
    assert "shortfall of ₹1,200.00" in task.evidence_notes
    assert "ICICINODAL99271027" in task.evidence_notes

    # Check audit log for CREATE_SETTLEMENT_DISPUTE
    audit_ev = (
        db.query(AuditEvent)
        .filter(AuditEvent.action == "CREATE_SETTLEMENT_DISPUTE", AuditEvent.target == dispute_task_id)
        .first()
    )
    assert audit_ev is not None
    assert audit_ev.result in ("CONFIRMED", "SUCCESS")


# TEST 6: Retrying reconciliation on the same day does NOT create duplicate disputes (Idempotency)
def test_retrying_reconciliation_does_not_create_duplicate_disputes(db: Session):
    agent = ReconcileAgent(db=db)

    # First run
    res1 = agent.run(
        merchant_id="mer_sharma_kirana",
        query_text="Check 27 Oct payout discrepancy",
        settlement_date="2026-10-27",
    )
    case_id_1 = res1["breakdown_card"]["dispute_case_id"]

    # Second run (retry on same merchant & date)
    res2 = agent.run(
        merchant_id="mer_sharma_kirana",
        query_text="Check 27 Oct payout discrepancy again",
        settlement_date="2026-10-27",
    )
    case_id_2 = res2["breakdown_card"]["dispute_case_id"]

    # Assert returns the SAME case ID
    assert case_id_1 == case_id_2

    # Assert total count of disputes for 2026-10-27 is exactly 1
    count = db.query(Task).filter(
        Task.merchant_id == "mer_sharma_kirana",
        Task.title.like("%Settlement Dispute%2026-10-27%"),
    ).count()
    assert count == 1


# TEST 7: Orchestrator routes settlement queries to ReconcileAgent
def test_orchestrator_routes_settlement_queries_to_reconcile(db: Session):
    orch = SaathiBrainOrchestrator(db=db)
    res = orch.route_and_run(
        merchant_id="mer_sharma_kirana",
        query_text="My yesterday payout does not match calculations",
        city="Jaipur",
    )
    assert res["agent"] == "RECONCILE"
    assert res["breakdown_card"] is not None
    assert res["breakdown_card"]["type"] == "SETTLEMENT_BREAKDOWN"
    assert res["speech_audio_base64"] is not None


# TEST 8: Merchant chat API endpoint returns breakdown card
def test_merchant_chat_endpoint_settlement(client: TestClient, merchant_token: str):
    res = client.post(
        "/merchant/chat/message",
        headers={"Authorization": f"Bearer {merchant_token}"},
        json={"message": "Show settlement breakdown for yesterday"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["agent"] == "RECONCILE"
    assert data["breakdown_card"] is not None
    assert data["breakdown_card"]["settlement_date"] == "2026-10-28"
    assert data["breakdown_card"]["is_reconciled"] is True
    assert data["chip_status"] == "verified"


# TEST 9: Employee web cases API surfaces settlement dispute with attached evidence
def test_employee_cases_shows_settlement_dispute_with_evidence(
    client: TestClient,
    employee_token: str,
    db: Session,
):
    # Ensure 2026-10-27 dispute exists
    agent = ReconcileAgent(db=db)
    agent.run(
        merchant_id="mer_sharma_kirana",
        query_text="27 Oct settlement shortfall",
        settlement_date="2026-10-27",
    )

    res = client.get("/employee/cases", headers={"Authorization": f"Bearer {employee_token}"})
    assert res.status_code == 200
    cases_data = res.json()
    cases = cases_data["cases"]

    dispute_case = next(
        (c for c in cases if "Settlement Dispute" in c["title"] and "2026-10-27" in c["title"]),
        None,
    )
    assert dispute_case is not None
    assert dispute_case["bucket"] == "needs_human"
    assert dispute_case["priority"] == "HIGH"
    assert dispute_case["dispute_amount_formatted"] == "₹1,200.00"
    assert "shortfall of ₹1,200.00" in dispute_case["evidence_notes"]
    assert dispute_case["evidence_url"] is not None

    # Verify timeline for this case
    t_res = client.get(
        f"/employee/cases/{dispute_case['id']}/timeline",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert t_res.status_code == 200
    timeline = t_res.json()
    assert len(timeline["events"]) >= 1
    assert any(ev["action"] == "CREATE_SETTLEMENT_DISPUTE" for ev in timeline["events"])
