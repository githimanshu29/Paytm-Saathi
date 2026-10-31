import pytest
from datetime import datetime, timezone
from starlette.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.db.models import (
    Merchant,
    MerchantDocument,
    Task,
    TaskBucket,
    AuditEvent,
)
from app.adapters.onboard import MockOnboardAdapter
from app.tools.onboard import OnboardTools
from app.agents.onboard import OnboardAgent
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
def reset_apex_merchant(db: Session):
    merchant = db.query(Merchant).filter_by(id="mer_apex_retail").first()
    if merchant:
        merchant.onboarding_status = "PENDING_VERIFICATION"
        merchant.kyc_status = "PENDING"
        merchant.status = "INCOMPLETE"
        for d in merchant.documents:
            d.status = "OCR_PASSED"
            d.is_ocr_passed = True
            d.ocr_quality_flag = "CLEAR"
            d.authorized_verification_status = "PENDING"
            d.verified_at = None
        db.commit()
    yield


# =========================================================================
# 1. ADAPTER & INVARIANT TESTS
# =========================================================================

def test_blurry_document_rejected_with_specific_reason(db: Session):
    """
    INVARIANT: A bad/blurry document must be flagged with a specific,
    actionable reason, never a generic rejection.
    """
    adapter = MockOnboardAdapter(db)
    checklist = adapter.get_onboarding_checklist("mer_gupta_electronics")

    assert checklist is not None
    assert "PAN_CARD" in checklist.blurry_documents
    assert not checklist.can_submit_for_verification

    # Find the PAN document item
    pan_doc = next(d for d in checklist.documents if d.document_type == "PAN_CARD")
    assert pan_doc.status == "OCR_FAILED"
    assert pan_doc.ocr_quality_flag == "BLURRY"
    assert pan_doc.rejection_reason is not None
    assert "blurry" in pan_doc.rejection_reason.lower()
    assert "resend a sharp" in pan_doc.rejection_reason.lower()


def test_missing_document_identified_correctly(db: Session):
    """
    Verifies that missing documents are explicitly flagged as missing.
    """
    adapter = MockOnboardAdapter(db)
    checklist = adapter.get_onboarding_checklist("mer_singh_automobiles")

    assert checklist is not None
    assert "BANK_PROOF" in checklist.missing_documents
    assert not checklist.can_submit_for_verification

    bank_doc = next(d for d in checklist.documents if d.document_type == "BANK_PROOF")
    assert bank_doc.status == "MISSING"
    assert "missing" in bank_doc.rejection_reason.lower()


def test_untrusted_ocr_candidate_fields_invariant(db: Session):
    """
    INVARIANT: OCR extractions are candidate fields and explicitly UNTRUSTED.
    They cannot directly authorize or verify documents.
    """
    adapter = MockOnboardAdapter(db)
    ocr_res = adapter.extract_document_fields("PAN_CARD", "pan_sample.jpg")

    assert ocr_res.is_ocr_passed is True
    assert "candidate_fields" in ocr_res.__dict__
    assert ocr_res.disclaimer == "Candidate OCR fields are explicitly UNTRUSTED until authorized verification."
    assert "candidate_pan" in ocr_res.candidate_fields
    assert ocr_res.candidate_fields.get("untrusted") is True


def test_ocr_alone_cannot_activate_or_verify(db: Session):
    """
    INVARIANT: Even when all documents pass OCR, kyc_status remains PENDING
    and merchant status is NOT ACTIVE until authorized verification is executed.
    """
    adapter = MockOnboardAdapter(db)
    merchant = db.query(Merchant).filter_by(id="mer_apex_retail").first()
    assert merchant is not None

    checklist = adapter.get_onboarding_checklist("mer_apex_retail")
    assert checklist.can_submit_for_verification is True
    # Invariant: OCR passed does NOT mean verified yet
    assert checklist.is_fully_verified is False
    assert merchant.kyc_status != "VERIFIED"
    assert merchant.status != "ACTIVE"


def test_full_pass_reaches_active_only_after_simulated_verification(db: Session):
    """
    INVARIANT: A fully passing set of documents reaches 'ACTIVE' only after
    the simulated authorized verification step runs.
    """
    adapter = MockOnboardAdapter(db)
    # mer_apex_retail has all 3 docs passing OCR
    res = adapter.submit_for_authorized_verification("mer_apex_retail")

    assert res.success is True
    assert res.application_status == "ACTIVE"
    assert res.kyc_status == "VERIFIED"
    assert len(res.verified_documents) == 3

    # Check merchant record in database
    merchant = db.query(Merchant).filter_by(id="mer_apex_retail").first()
    assert merchant.status == "ACTIVE"
    assert merchant.kyc_status == "VERIFIED"
    assert merchant.onboarding_status == "COMPLETED"

    # Verify audit event was logged
    audit_ev = (
        db.query(AuditEvent)
        .filter_by(
            target="mer_apex_retail",
            action="AUTHORIZED_KYC_VERIFICATION_COMPLETED",
        )
        .first()
    )
    assert audit_ev is not None
    assert audit_ev.actor == "authorized_kyc_verification_engine"


def test_cannot_submit_incomplete_application_for_verification(db: Session):
    """
    Verifies that calling authorized verification on an application with blurry
    or missing documents is rejected.
    """
    adapter = MockOnboardAdapter(db)
    # mer_gupta_electronics has a blurry PAN
    res = adapter.submit_for_authorized_verification("mer_gupta_electronics")

    assert res.success is False
    assert "Cannot submit for verification" in res.message
    assert "Blurry" in res.message or "PAN_CARD" in res.message


# =========================================================================
# 2. SECURITY INVARIANT TESTS
# =========================================================================

def test_security_invariant_blocks_asking_for_password_otp_pin(db: Session):
    """
    INVARIANT: Asking the merchant for a password, OTP, or UPI PIN
    is an explicit security violation and MUST be halted.
    """
    tools = OnboardTools(db)
    agent = OnboardAgent(db)

    # Test tools validator
    unsafe_query = "Please tell me your UPI PIN and OTP to verify your account"
    sec_res = tools.validate_security_invariants(unsafe_query)
    assert sec_res["is_safe"] is False
    assert "pin" in sec_res["violation"].lower() or "otp" in sec_res["violation"].lower()

    # Test agent response
    agent_res = agent.run("mer_gupta_electronics", query_text=unsafe_query)
    assert agent_res["is_security_violation"] is True
    assert agent_res["chip_status"] == "needs_human"
    assert "Security Alert" in agent_res["agent_reply"]


# =========================================================================
# 3. ONBOARD AGENT & GRAPH WORKFLOW TESTS
# =========================================================================

def test_agent_chases_blurry_pan_with_specific_guidance(db: Session):
    """
    Tests OnboardAgent chasing the blurry PAN card on mer_gupta_electronics
    with specific resubmission instructions.
    """
    agent = OnboardAgent(db)
    res = agent.run("mer_gupta_electronics", query_text="Why is my signup pending?")

    assert res["success"] is True
    assert res["agent"] == "ONBOARD"
    assert res["chip_status"] == "needs_human"
    assert "PAN" in res["agent_reply"]
    assert "blurry" in res["agent_reply"].lower()

    card = res["missing_item_card"]
    assert card is not None
    assert card["doc_type"] == "PAN_CARD"
    assert card["is_blurry"] is True
    assert "blurry" in card["specific_reason"].lower()


def test_agent_submits_verification_when_all_docs_pass(db: Session):
    """
    When all 3 documents pass OCR, agent proceeds to submit for authorized verification.
    """
    # Reset apex retail state so it's ready for verification test
    merchant = db.query(Merchant).filter_by(id="mer_apex_retail").first()
    merchant.onboarding_status = "PENDING_VERIFICATION"
    merchant.kyc_status = "PENDING"
    merchant.status = "INCOMPLETE"
    for d in merchant.documents:
        d.status = "OCR_PASSED"
        d.authorized_verification_status = "PENDING"
    db.commit()

    agent = OnboardAgent(db)
    res = agent.run("mer_apex_retail", query_text="Check my documents and finish signup")

    assert res["success"] is True
    assert res["chip_status"] == "verified"
    assert "ACTIVE" in res["agent_reply"] or "verification" in res["agent_reply"].lower()

    card = res["missing_item_card"]
    assert card is not None
    assert card["type"] == "ONBOARDING_COMPLETED_CARD"
    assert card["application_status"] == "ACTIVE"


# =========================================================================
# 4. ORCHESTRATOR ROUTING TESTS
# =========================================================================

def test_orchestrator_routes_onboard_query_and_generates_speech(db: Session):
    """
    Verifies SaathiBrainOrchestrator routes onboarding/KYC queries to OnboardAgent
    and synthesizes speech audio.
    """
    orchestrator = SaathiBrainOrchestrator(db)
    result = orchestrator.route_and_run(
        merchant_id="mer_gupta_electronics",
        query_text="What documents are missing for my KYC onboarding?",
    )

    assert result["agent"] == "ONBOARD"
    assert result["chip_status"] == "needs_human"
    assert "PAN" in result["reply"]
    assert result["missing_item_card"] is not None
    assert result["speech_audio_base64"] is not None
    assert result["speech_duration_seconds"] > 0


# =========================================================================
# 5. API ENDPOINTS TESTS
# =========================================================================

def test_api_merchant_onboarding_checklist(client: TestClient, merchant_token: str):
    res = client.get(
        "/merchant/onboarding/checklist",
        headers={"Authorization": f"Bearer {merchant_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["found"] is True
    assert "documents" in data
    assert len(data["documents"]) == 3


def test_api_merchant_upload_blurry_document(client: TestClient, merchant_token: str):
    res = client.post(
        "/merchant/onboarding/upload",
        headers={"Authorization": f"Bearer {merchant_token}"},
        json={
            "document_type": "PAN_CARD",
            "file_name": "blurry_pan_camera.jpg",
            "simulate_blur": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "OCR_FAILED"
    assert data["ocr_quality_flag"] == "BLURRY"
    assert data["untrusted"] is True
    assert "blurry" in data["rejection_reason"].lower()


def test_api_merchant_upload_clear_document(client: TestClient, merchant_token: str):
    res = client.post(
        "/merchant/onboarding/upload",
        headers={"Authorization": f"Bearer {merchant_token}"},
        json={
            "document_type": "PAN_CARD",
            "file_name": "clear_pan_camera.jpg",
            "simulate_blur": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "OCR_PASSED"
    assert data["ocr_quality_flag"] == "CLEAR"
    assert data["untrusted"] is True
    assert data["candidate_fields"] is not None


def test_api_employee_pipeline_view(client: TestClient, employee_token: str):
    res = client.get(
        "/employee/onboarding/pipeline",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_applications"] >= 4
    assert len(data["applications"]) >= 4
    assert data["blurry_count"] >= 1
