import pytest
import uuid
from datetime import datetime, timezone, timedelta
from starlette.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.db.models import (
    Customer,
    Receivable,
    ActionApproval,
    ApprovalDecision,
    AuditEvent,
)
from app.adapters.vasooli import (
    MockVasooliAdapter,
    VasooliPolicyViolationError,
    CoerciveCollectionError,
    CommunicationPermissionRevokedError,
    ReceivableDisputedError,
    BANNED_PHRASES,
)
from app.tools.vasooli import VasooliTools
from app.agents.vasooli import VasooliAgent
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
    res = client.post("/auth/merchant/request-otp", json={"phone": "9876543210"})
    assert res.status_code == 200
    res = client.post("/auth/merchant/verify-otp", json={"phone": "9876543210", "otp": "123456"})
    assert res.status_code == 200
    return res.json()["access_token"]


@pytest.fixture
def employee_token(client):
    res = client.post("/auth/employee/login", json={"email": "support@paytm.demo", "password": "Demo@1234"})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


@pytest.fixture(autouse=True)
def reset_vasooli_demo_state(db: Session):
    """Resets core seeded receivables to pristine state before each test."""
    # Reset Vikram Singh (rec_sharma_001)
    rec1 = db.query(Receivable).filter_by(id="rec_sharma_001").first()
    if rec1:
        rec1.status = "PENDING"
        rec1.reminder_count = 0
        rec1.last_reminder_sent_at = None
        rec1.settlement_verification_status = "UNSETTLED"
        rec1.paid_amount = 0
        rec1.payment_reference = None

    # Reset Sunita Devi permission (cust_sunita_devi)
    cust_sunita = db.query(Customer).filter_by(id="cust_sunita_devi").first()
    if cust_sunita:
        cust_sunita.contact_permission = False
        cust_sunita.permission_status = "REVOKED"

    # Reset Manish Gupta dispute (rec_sharma_002_disputed)
    rec_manish = db.query(Receivable).filter_by(id="rec_sharma_002_disputed").first()
    if rec_manish:
        rec_manish.is_disputed = True
        rec_manish.status = "PENDING"
        rec_manish.reminder_count = 0

    db.commit()
    yield


# =============================================================================
# 1. ANTI-COERCION & BANNED PHRASES POLICY TESTS
# =============================================================================

def test_banned_coercive_phrases_detected_by_adapter(db: Session):
    """Vasooli adapter must detect any prohibited coercive keyword."""
    adapter = MockVasooliAdapter(db)
    
    assert adapter.check_banned_phrases("Send police to customer house") == "police"
    assert adapter.check_banned_phrases("You will go to jail if you dont pay") == "jail"
    assert adapter.check_banned_phrases("Sending legal notice tomorrow") == "legal notice"
    assert adapter.check_banned_phrases("This is your final warning") == "final warning"
    assert adapter.check_banned_phrases("He is a defaulter") == "defaulter"
    assert adapter.check_banned_phrases("Kindly pay rs 500 when possible") is None


def test_coercive_message_draft_raises_policy_violation(db: Session):
    """Passing custom coercive text to draft_payment_reminder raises VasooliPolicyViolationError."""
    adapter = MockVasooliAdapter(db)
    
    with pytest.raises(VasooliPolicyViolationError) as exc_info:
        adapter.draft_payment_reminder("rec_sharma_001", custom_note="Pay now or police will come")
    
    assert "coercive language detected" in str(exc_info.value).lower()


def test_agent_blocks_coercive_language_query(db: Session):
    """When a merchant inputs coercive language in Saathi chat, Vasooli agent blocks it with R4 error."""
    agent = VasooliAgent(db)
    res = agent.run(
        query_text="Send police to Vikram's house to collect 500 rs immediately",
        merchant_id="mer_sharma_kirana",
    )
    
    assert res["chip_status"] == "needs_human"
    assert res["error"] == "R4_COERCIVE_LANGUAGE_BLOCKED"
    assert "Action Blocked by Policy" in res["agent_reply"]
    assert "strictly prohibits legal threats" in res["agent_reply"]


# =============================================================================
# 2. CONSENT & DISPUTE REFUSAL TESTS
# =============================================================================

def test_refused_outreach_on_revoked_permission(db: Session):
    """Customer Sunita Devi has revoked permission; outreach must be visibly refused."""
    adapter = MockVasooliAdapter(db)
    draft = adapter.draft_payment_reminder("rec_sharma_003_revoked")
    
    assert draft.can_send is False
    assert "revoked contact permission" in draft.refusal_reason.lower() or "revoked" in draft.refusal_reason.lower()


def test_agent_visibly_refuses_outreach_for_revoked_customer(db: Session):
    """Saathi chat query asking to remind Sunita Devi must visibly return refusal."""
    agent = VasooliAgent(db)
    res = agent.run(
        query_text="Send reminder to Sunita Devi",
        merchant_id="mer_sharma_kirana",
    )
    
    assert res["chip_status"] == "needs_human"
    assert "Outreach Refused" in res["agent_reply"]
    assert "revoked" in res["agent_reply"].lower()


def test_refused_outreach_on_disputed_receivable(db: Session):
    """Manish Gupta has an active dispute; reminder must be refused until resolved."""
    adapter = MockVasooliAdapter(db)
    draft = adapter.draft_payment_reminder("rec_sharma_002_disputed")
    
    assert draft.can_send is False
    assert "disputed" in draft.refusal_reason.lower()


def test_agent_visibly_refuses_outreach_for_disputed_receivable(db: Session):
    """Saathi chat query asking to remind Manish Gupta returns visible dispute refusal."""
    agent = VasooliAgent(db)
    res = agent.run(
        query_text="Remind Manish Gupta about udhaar",
        merchant_id="mer_sharma_kirana",
    )
    
    assert res["chip_status"] == "needs_human"
    assert "Outreach Refused" in res["agent_reply"]
    assert "disputed" in res["agent_reply"].lower()


# =============================================================================
# 3. CONSENSUAL DRAFTING, SENDING & 3-ATTEMPT CAP
# =============================================================================

def test_consensual_reminder_draft_and_send(db: Session):
    """Consensual pending receivable (Vikram Singh) drafts polite reminder and sends via adapter."""
    adapter = MockVasooliAdapter(db)
    
    # Draft
    draft = adapter.draft_payment_reminder("rec_sharma_001")
    assert draft.can_send is True
    assert "Vikram Singh" in draft.draft_message_hi or "Vikram" in draft.draft_message_en
    assert "₹850.00" in draft.draft_message_hi or "850" in draft.draft_message_hi
    assert "https://paytm.demo/pay/" in draft.payment_link_url

    # Send
    send_res = adapter.send_authorized_reminder("rec_sharma_001", actor_id="mer_sharma_kirana")
    assert send_res.success is True
    assert send_res.recipient_phone == "+919811122233"

    # Verify DB state
    rec = db.query(Receivable).filter_by(id="rec_sharma_001").first()
    assert rec.reminder_count == 1
    assert rec.last_reminder_sent_at is not None

    # Verify Audit Event
    audit = (
        db.query(AuditEvent)
        .filter(AuditEvent.action == "VASOOLI_REMINDER_SENT", AuditEvent.target == "receivables:rec_sharma_001")
        .order_by(AuditEvent.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.result == "SUCCESS"


def test_send_reminder_idempotency(db: Session):
    """Calling send_authorized_reminder with the same idempotency key does not re-send."""
    adapter = MockVasooliAdapter(db)
    idem_key = f"idem_test_{uuid.uuid4().hex[:8]}"

    res1 = adapter.send_authorized_reminder("rec_sharma_001", actor_id="mer_sharma_kirana", idempotency_key=idem_key)
    assert res1.success is True

    rec_after_first = db.query(Receivable).filter_by(id="rec_sharma_001").first()
    count_1 = rec_after_first.reminder_count

    # Re-send with identical idempotency key
    res2 = adapter.send_authorized_reminder("rec_sharma_001", actor_id="mer_sharma_kirana", idempotency_key=idem_key)
    assert res2.success is True

    rec_after_second = db.query(Receivable).filter_by(id="rec_sharma_001").first()
    assert rec_after_second.reminder_count == count_1, "Reminder count must not increment on duplicate idempotency key"


def test_reminder_attempt_capped_at_three(db: Session):
    """Reminders are strictly capped at 3 attempts per receivable."""
    adapter = MockVasooliAdapter(db)
    rec = db.query(Receivable).filter_by(id="rec_sharma_001").first()
    rec.reminder_count = 3
    db.commit()

    draft = adapter.draft_payment_reminder("rec_sharma_001")
    assert draft.can_send is False
    assert "cap reached" in draft.refusal_reason.lower()

    with pytest.raises(ValueError) as exc:
        adapter.send_authorized_reminder("rec_sharma_001", actor_id="mer_sharma_kirana")
    assert "cap (3) reached" in str(exc.value)


# =============================================================================
# 4. INSTALLMENT SPLIT NEGOTIATION
# =============================================================================

def test_negotiate_split_installment(db: Session):
    """Splits a receivable into smaller installments and creates an ActionApproval."""
    adapter = MockVasooliAdapter(db)
    rec = db.query(Receivable).filter_by(id="rec_sharma_004_split").first()
    assert rec is not None

    split_res = adapter.negotiate_installment_split(rec.id, split_amounts_paise=[75000, 75000], actor_id="mer_sharma_kirana")
    assert split_res.total_amount_paise == 150000
    assert len(split_res.splits) == 2
    assert split_res.splits[0]["amount_paise"] == 75000
    assert split_res.splits[1]["amount_paise"] == 75000

    # Verify ActionApproval created
    appr = db.query(ActionApproval).filter_by(receivable_id=rec.id).order_by(ActionApproval.created_at.desc()).first()
    assert appr is not None
    assert appr.decision == ApprovalDecision.PENDING
    assert "2-part split" in (appr.reason or "").lower()


# =============================================================================
# 5. AUTHORITATIVE PAYMENT AUTO-STOP & APPROVAL AUTO-CANCELLATION
# =============================================================================

def test_payment_arrival_auto_cancels_approvals_and_stops_reminders(db: Session):
    """When authoritative payment arrives, pending approvals are auto-cancelled and reminders stop."""
    adapter = MockVasooliAdapter(db)
    rec = db.query(Receivable).filter_by(id="rec_sharma_001").first()
    rec.status = "PENDING"
    rec.settlement_verification_status = "UNSETTLED"
    db.commit()

    # Create a pending approval linked to this receivable
    appr = ActionApproval(
        tenant_id="tenant_paytm_demo",
        receivable_id=rec.id,
        approver="Sharma Kirana",
        decision=ApprovalDecision.PENDING,
        reason="Test reminder queue",
        risk_tier="R1",
        proposal_hash=uuid.uuid4().hex[:24],
        is_synthetic=True,
        environment="DEMO",
    )
    db.add(appr)
    db.commit()

    # Authoritative Payment Webhook Simulation
    pay_res = adapter.record_payment_status(
        receivable_id=rec.id,
        paid_amount_paise=rec.amount,
        payment_reference="UPI-AUTO-STOP-TEST-9999",
        is_authoritative=True,
        actor_id="demo_webhook",
    )
    assert pay_res.verified is True
    assert pay_res.status == "PAID"
    assert len(pay_res.cancelled_approval_ids) >= 1

    # Invariant 1: Receivable status is PAID and VERIFIED_PAID
    db.refresh(rec)
    assert rec.status == "PAID"
    assert rec.settlement_verification_status == "VERIFIED_PAID"
    assert rec.payment_reference == "UPI-AUTO-STOP-TEST-9999"

    # Invariant 2: Pending approval was auto-cancelled
    db.refresh(appr)
    assert appr.decision == ApprovalDecision.REJECTED
    assert "AUTO_CANCELLED" in (appr.reason or "")

    # Invariant 3: Further reminders are strictly rejected
    with pytest.raises(ValueError) as exc:
        adapter.send_authorized_reminder(rec.id, actor_id="mer_sharma_kirana")
    assert "already settled" in str(exc.value)


# =============================================================================
# 6. SAATHI CHAT & FREE-TEXT UDHAAR RECORDING
# =============================================================================

def test_free_text_udhaar_recording_via_agent(db: Session):
    """Merchant asks: 'Record udhaar of 250 for Vikram Singh'. Agent creates receivable & approval card."""
    agent = VasooliAgent(db)
    res = agent.run(
        query_text="Record udhaar of 250 for Vikram Singh",
        merchant_id="mer_sharma_kirana",
    )

    assert res["chip_status"] == "awaiting_approval"
    assert "Recorded store credit (Udhaar)" in res["agent_reply"]
    assert "Vikram Singh" in res["agent_reply"]

    card = res.get("vasooli_card") or res.get("approval_card")
    assert card is not None
    assert card["customer_name"] == "Vikram Singh"
    assert card["can_send"] is True
    assert "draft_message_hi" in card


def test_orchestrator_routes_udhaar_to_vasooli(db: Session):
    """SaathiBrainOrchestrator routes udhaar keywords directly to Vasooli specialist agent."""
    orchestrator = SaathiBrainOrchestrator(db)
    res = orchestrator.route_and_run(
        merchant_id="mer_sharma_kirana",
        query_text="Vikram Singh bought 5kg aata on udhaar for rs 300",
        city="Jaipur",
    )

    assert res["agent"] == "VASOOLI"
    assert "Vikram Singh" in res["reply"]
    assert res["chip_status"] == "awaiting_approval"


# =============================================================================
# 7. END-TO-END FASTAPI HTTP ENDPOINTS
# =============================================================================

def test_merchant_vasooli_api_endpoints(client: TestClient, merchant_token: str):
    """Verifies /merchant/vasooli/* REST endpoints."""
    headers = {"Authorization": f"Bearer {merchant_token}"}

    # Summary
    sum_res = client.get("/merchant/vasooli/summary", headers=headers)
    assert sum_res.status_code == 200
    data = sum_res.json()
    assert "total_outstanding_formatted" in data
    assert "total_recovered_formatted" in data
    assert data["total_receivables_count"] >= 4

    # Draft reminder
    draft_res = client.post("/merchant/vasooli/draft-reminder", headers=headers, json={"receivable_id": "rec_sharma_001"})
    assert draft_res.status_code == 200
    d_data = draft_res.json()
    assert d_data["can_send"] is True
    assert "draft_message_hi" in d_data

    # Send reminder
    send_res = client.post("/merchant/vasooli/send-reminder", headers=headers, json={"receivable_id": "rec_sharma_001"})
    assert send_res.status_code == 200
    s_data = send_res.json()
    assert s_data["success"] is True


def test_demo_payment_event_triggers_auto_stop(client: TestClient):
    """Verifies /demo/vasooli/payment-event authoritatively settles receivable and auto-cancels."""
    res = client.post(
        "/demo/vasooli/payment-event",
        json={
            "receivable_id": "rec_sharma_001",
            "amount_paise": 85000,
            "payment_reference": "UPI-AUTO-STOP-DEMO-ENDPOINT",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["verified"] is True
    assert data["status"] == "PAID"
    assert data["reminders_stopped"] is True
    assert "auto-stopped" in data["message"].lower()


def test_employee_vasooli_overview_and_dashboard_kpis(client: TestClient, employee_token: str):
    """Verifies employee web endpoints return Vasooli data and recovered totals."""
    headers = {"Authorization": f"Bearer {employee_token}"}

    # Overview
    ov_res = client.get("/employee/vasooli/overview", headers=headers)
    assert ov_res.status_code == 200
    ov_data = ov_res.json()
    assert "receivables" in ov_data
    assert ov_data["total_receivables_count"] >= 4

    # Dashboard summary
    kpi_res = client.get("/employee/dashboard/summary", headers=headers)
    assert kpi_res.status_code == 200
    kpi_data = kpi_res.json()
    assert "total_vasooli_recovered_formatted" in kpi_data
    assert "total_vasooli_recovered_paise" in kpi_data
