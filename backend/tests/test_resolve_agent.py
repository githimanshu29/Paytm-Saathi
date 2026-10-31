import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.db.models import (
    Task,
    TaskBucket,
    ActionApproval,
    ApprovalDecision,
    AuditEvent,
)
from app.agents.resolve import ResolveAgent
from app.adapters.transaction import MockTransactionAdapter
from app.tools.resolve import ResolveTools

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
    phone = "+919876543210"
    client.post("/auth/merchant/request-otp", json={"phone": phone})
    res = client.post("/auth/merchant/verify-otp", json={"phone": phone, "otp": "123456"})
    return res.json()["access_token"]

@pytest.fixture
def employee_token(client):
    res = client.post(
        "/auth/employee/login",
        json={"email": "support@paytm.demo", "password": "Demo@1234"},
    )
    return res.json()["access_token"]

# 1. Branch A: Auto-reversal in progress (U30) -> timeline stated, no goods on credit
def test_resolve_branch_a_autoreversal(db):
    agent = ResolveAgent(db)
    result = agent.run(
        merchant_id="mer_sharma_kirana",
        query_text="Customer Alok says payment of ₹250 failed, check auto reversal",
        actor_id="mer_sharma_kirana",
    )

    assert result["branch"] == "A_AUTO_REVERSAL"
    assert result["chip_status"] == "verified"
    assert "24–48 banking hours" in result["agent_reply"]
    assert "Do NOT provide goods on credit" in result["agent_reply"]
    assert result["tx_ref"] == "PAYTM_REV_AUTO_991201"
    assert result["approval_card"] is None

# 2. Branch B: Reversal stuck (U69, >48h) -> creates review task & approval card
def test_resolve_branch_b_stuck_reversal_creates_review_task(db):
    # Clean up any existing task for PAYTM_STUCK_881920 to ensure test isolation
    existing_tasks = db.query(Task).filter(Task.title.like("%PAYTM_STUCK_881920%")).all()
    for et in existing_tasks:
        db.query(ActionApproval).filter_by(task_id=et.id).delete()
        db.delete(et)
    db.commit()

    agent = ResolveAgent(db)
    result = agent.run(
        merchant_id="mer_sharma_kirana",
        query_text="Deepak Verma payment of ₹500 is stuck, customer did not get money back",
        actor_id="mer_sharma_kirana",
    )

    assert result["branch"] == "B_STUCK_REFUND_REVIEW"
    assert result["chip_status"] == "awaiting_approval"
    assert "Refund Review Request" in result["agent_reply"]
    assert result["approval_card"] is not None

    card = result["approval_card"]
    assert card["type"] == "REFUND_REVIEW_APPROVAL"
    assert card["risk_tier"] == "R2"
    assert card["utr"] == "PAYTM_STUCK_881920"
    assert "does NOT deduct from your settlement balance" in card["note"]

    # Verify task exists in DB under awaiting_approval
    task_id = result["case_id"]
    task = db.query(Task).filter_by(id=task_id).first()
    assert task is not None
    assert task.bucket == TaskBucket.AWAITING_APPROVAL
    assert "500" in task.title

    # Verify linked approval
    approval = db.query(ActionApproval).filter_by(task_id=task.id).first()
    assert approval is not None
    assert approval.decision == ApprovalDecision.PENDING

    # Verify audit event logged
    audit = (
        db.query(AuditEvent)
        .filter_by(action="REQUEST_REFUND_REVIEW", target=task.id)
        .first()
    )
    assert audit is not None
    assert audit.result == "CONFIRMED"

# 3. Branch C: Actually succeeded (00_SUCCESS) -> confirms credited status
def test_resolve_branch_c_payment_confirmed(db):
    agent = ResolveAgent(db)
    result = agent.run(
        merchant_id="mer_sharma_kirana",
        query_text="Customer Pooja says ₹320 was debited but Soundbox did not speak, did it go through?",
        actor_id="mer_sharma_kirana",
    )

    assert result["branch"] == "C_PAYMENT_CONFIRMED"
    assert result["chip_status"] == "verified"
    assert "SUCCESSFUL and credited" in result["agent_reply"]
    assert result["tx_ref"] == "PAYTM_SUCC_771829"
    assert result["approval_card"] is None

# 4. Branch D: Ambiguous / fraud-flavored (ZA_SECURITY_HOLD) -> escalates to needs_human
def test_resolve_branch_d_fraud_escalated_to_needs_human(db):
    agent = ResolveAgent(db)
    result = agent.run(
        merchant_id="mer_sharma_kirana",
        query_text="Suspicious payment of ₹1200 from unknown customer, check if fake",
        actor_id="mer_sharma_kirana",
    )

    assert result["branch"] == "D_FRAUD_ESCALATED"
    assert result["chip_status"] == "needs_human"
    assert "Compliance and Risk Operations" in result["agent_reply"]
    assert "Do NOT initiate manual payments" in result["agent_reply"]
    assert result["tx_ref"] == "PAYTM_FRAUD_661904"

    # Verify created task is in needs_human bucket
    case_id = result["case_id"]
    task = db.query(Task).filter_by(id=case_id).first()
    assert task is not None
    assert task.bucket == TaskBucket.NEEDS_HUMAN
    assert task.priority == "HIGH"

# 5. Policy Engine Enforcement: R3 direct refund execution strictly prohibited
def test_r3_refund_execution_blocked_by_policy(db):
    adapter = MockTransactionAdapter(db)
    tools = ResolveTools(adapter, db)

    # Directly attempting to execute an R3 refund
    result = tools.execute_refund(
        tx_id="txn_stuck_reversal",
        amount_paise=50000,
        actor_id="test_agent",
    )

    assert result["allowed"] is False
    assert result["executed"] is False
    assert "Direct refund execution is disabled in this prototype (R3 Financial Action)" in result["error"]

    # Verify audit event for blocked action
    audit = (
        db.query(AuditEvent)
        .filter_by(action="EXECUTE_REFUND_BLOCKED", target="txn_stuck_reversal")
        .first()
    )
    assert audit is not None
    assert audit.result == "BLOCKED_BY_POLICY"

# 6. Idempotency: Retrying the same refund review does not duplicate tasks
def test_refund_review_idempotency(db):
    adapter = MockTransactionAdapter(db)
    tools = ResolveTools(adapter, db)

    res1 = tools.request_refund_review(
        merchant_id="mer_sharma_kirana",
        tx_id="txn_stuck_reversal",
        reason="Idempotency test request 1",
        execution_id="exec_test_idemp_101",
        actor_id="mer_sharma_kirana",
    )
    assert res1["success"] is True

    # Second identical call
    res2 = tools.request_refund_review(
        merchant_id="mer_sharma_kirana",
        tx_id="txn_stuck_reversal",
        reason="Idempotency test request 2",
        execution_id="exec_test_idemp_101",
        actor_id="mer_sharma_kirana",
    )
    assert res2["success"] is True
    assert res2["is_duplicate_idempotent"] is True
    assert res2["task_id"] == res1["task_id"]

# 7. Merchant Approval Decision endpoint
def test_merchant_approval_decision_endpoint(client, merchant_token, db):
    # First ensure a pending approval exists
    agent = ResolveAgent(db)
    res = agent.run(
        merchant_id="mer_sharma_kirana",
        query_text="PAYTM_STUCK_881920 need refund review",
        actor_id="mer_sharma_kirana",
    )
    approval_card = res["approval_card"]
    assert approval_card is not None
    approval_id = approval_card["approval_id"]

    # Call approval endpoint
    decision_res = client.post(
        f"/merchant/approvals/{approval_id}/decide",
        headers={"Authorization": f"Bearer {merchant_token}"},
        json={"decision": "APPROVED", "reason": "Merchant confirmed customer proof"},
    )
    assert decision_res.status_code == 200
    d_data = decision_res.json()
    assert d_data["decision"] == "APPROVED"
    assert d_data["chip_status"] == "executed"

    # Verify database state
    approval = db.query(ActionApproval).filter_by(id=approval_id).first()
    assert approval.decision == ApprovalDecision.APPROVED

    task = db.query(Task).filter_by(id=approval.task_id).first()
    assert task.bucket == TaskBucket.EXECUTED

    # Verify audit event
    audit = (
        db.query(AuditEvent)
        .filter_by(action="MERCHANT_APPROVAL_DECISION", target=approval_id)
        .order_by(AuditEvent.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.result == "APPROVED"

# 8. Employee Web sees review task in Cases table and authoritative timeline
def test_employee_web_sees_case_and_timeline(client, employee_token, db):
    # Ensure review task exists
    cases_res = client.get(
        "/employee/cases",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert cases_res.status_code == 200
    cases_data = cases_res.json()
    assert cases_data["total"] > 0

    # Find the stuck reversal case
    target_case = next(
        (c for c in cases_data["cases"] if "Refund Review Request" in c["title"]),
        None,
    )
    assert target_case is not None

    # Inspect timeline for this case
    timeline_res = client.get(
        f"/employee/cases/{target_case['id']}/timeline",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert timeline_res.status_code == 200
    timeline_data = timeline_res.json()
    assert timeline_data["case_id"] == target_case["id"]
    assert len(timeline_data["events"]) > 0
