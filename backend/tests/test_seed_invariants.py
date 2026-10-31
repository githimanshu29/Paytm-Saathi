import pytest
from app.db.session import SessionLocal
from app.db.models import (
    Merchant,
    Transaction,
    Device,
    Task,
    TaskBucket,
    Employee,
)
from app.policy.engine import PolicyEngine
from app.schemas.policy import ActionProposal, RiskTier

def test_merchant_seed_invariants():
    db = SessionLocal()
    try:
        merchants = db.query(Merchant).all()
        assert len(merchants) >= 3, "Expected at least 3 demo merchants"

        for m in merchants:
            assert m.is_synthetic is True, f"Merchant {m.store_name} must be synthetic"
            assert m.environment == "DEMO", f"Merchant {m.store_name} environment must be DEMO"
            assert len(m.store_name) > 0
            assert len(m.phone) > 0
    finally:
        db.close()

def test_transaction_invariants():
    db = SessionLocal()
    try:
        transactions = db.query(Transaction).all()
        assert len(transactions) > 0, "Expected transactions in seed data"

        for tx in transactions:
            assert tx.is_synthetic is True
            assert tx.environment == "DEMO"
            # Invariant: Money is stored as integer paise and never negative
            assert isinstance(tx.amount, int), f"Transaction amount must be int, got {type(tx.amount)}"
            assert tx.amount > 0, f"Transaction amount must be positive, got {tx.amount}"
            assert tx.currency == "INR"
    finally:
        db.close()

def test_device_invariants():
    db = SessionLocal()
    try:
        devices = db.query(Device).all()
        assert len(devices) > 0, "Expected devices in seed data"

        for dev in devices:
            assert dev.is_synthetic is True
            assert dev.environment == "DEMO"
            assert 0 <= dev.battery_level <= 100
            assert dev.serial_number is not None
    finally:
        db.close()

def test_task_bucket_states_represented():
    db = SessionLocal()
    try:
        tasks = db.query(Task).all()
        assert len(tasks) > 0

        represented_buckets = {task.bucket.value for task in tasks}
        expected_buckets = {
            TaskBucket.VERIFIED.value,
            TaskBucket.EXECUTED.value,
            TaskBucket.PENDING.value,
            TaskBucket.AWAITING_APPROVAL.value,
            TaskBucket.NEEDS_HUMAN.value,
        }
        # Verify all 5 status states exist in seed data
        assert expected_buckets.issubset(represented_buckets), (
            f"Expected all 5 status bucket states, got {represented_buckets}"
        )
    finally:
        db.close()

def test_policy_engine_rules():
    # R0 read rule
    r0_proposal = ActionProposal(
        action_type="GET_SETTLEMENT_HISTORY",
        target_id="mer_sharma_kirana",
        risk_tier=RiskTier.R0,
        actor_id="agent_reconcile",
        actor_role="specialist_agent",
    )
    r0_decision = PolicyEngine.evaluate(r0_proposal)
    assert r0_decision.allowed is True
    assert "R0_READ_ALWAYS_ALLOWED" in r0_decision.reason_codes

    # R4 prohibited rule
    r4_proposal = ActionProposal(
        action_type="THREATEN_CUSTOMER",
        target_id="cust_vikram_singh",
        risk_tier=RiskTier.R4,
        actor_id="agent_vasooli",
        actor_role="specialist_agent",
    )
    r4_decision = PolicyEngine.evaluate(r4_proposal)
    assert r4_decision.allowed is False
    assert "R4_PROHIBITED_ACTION_BLOCKED" in r4_decision.reason_codes

    # R3 regulated financial action
    r3_proposal = ActionProposal(
        action_type="EXECUTE_REFUND",
        target_id="txn_sharma_001",
        risk_tier=RiskTier.R3,
        actor_id="agent_resolve",
        actor_role="specialist_agent",
    )
    r3_decision = PolicyEngine.evaluate(r3_proposal)
    assert r3_decision.allowed is False
    assert "R3_REGULATED_FINANCIAL_AUTOMATION_DISABLED" in r3_decision.reason_codes

    # R2 external action
    r2_proposal = ActionProposal(
        action_type="DISPATCH_TECHNICIAN",
        target_id="dev_soundbox_202",
        risk_tier=RiskTier.R2,
        actor_id="agent_fix",
        actor_role="specialist_agent",
    )
    r2_decision = PolicyEngine.evaluate(r2_proposal)
    assert r2_decision.allowed is False
    assert "R2_EXTERNAL_ACTION_REQUIRES_APPROVAL" in r2_decision.reason_codes
