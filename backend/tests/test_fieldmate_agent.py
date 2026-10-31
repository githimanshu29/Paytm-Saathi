import pytest
from starlette.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.db.models import Merchant, MerchantVisit, AuditEvent, Device
from app.adapters.fieldmate import (
    MockFieldMateAdapter,
    ConcurrencyConflictError,
    RepPolicyViolationError,
)
from app.tools.fieldmate import FieldMateTools
from app.agents.fieldmate import FieldMateAgent
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
def sales_rep_token(client):
    res = client.post("/auth/employee/login", json={"email": "sales@paytm.demo", "password": "Demo@1234"})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


@pytest.fixture
def manager_token(client):
    res = client.post("/auth/employee/login", json={"email": "manager@paytm.demo", "password": "Demo@1234"})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


@pytest.fixture(autouse=True)
def reset_test_visits(db: Session):
    for vid in ["visit_jai_001_singh", "visit_jai_002_gupta", "visit_jai_003_radhe", "visit_jai_004_apex"]:
        v = db.query(MerchantVisit).filter_by(id=vid).first()
        if v:
            v.is_confirmed_by_rep = False
            v.confirmed_notes = None
            v.lead_interest = None
            v.visit_status = "SCHEDULED"
            v.version = 1

    # Ensure Singh Automobiles device is in offline baseline state
    dev = db.query(Device).filter_by(id="dev_soundbox_505").first()
    if dev:
        dev.status = "OFFLINE"
        dev.battery_level = 12
        dev.technician_visit_booked = False

    db.commit()
    yield


# -----------------------------------------------------------------------------
# 1. Truthful Evidence-Backed Briefs
# -----------------------------------------------------------------------------
def test_merchant_briefs_truthful_from_db_records(db: Session):
    adapter = MockFieldMateAdapter(db)

    # (a) Singh Automobiles: Offline Soundbox + Missing Bank Proof
    brief_singh = adapter.get_merchant_brief("mer_singh_automobiles")
    assert brief_singh is not None
    assert brief_singh.priority == "HIGH"
    assert "Soundbox offline" in brief_singh.one_line_brief
    assert "missing" in brief_singh.one_line_brief
    assert brief_singh.evidence_breakdown["device"]["status"] == "OFFLINE"
    assert "BANK_PROOF" in brief_singh.evidence_breakdown["kyc"]["missing_docs"]

    # (b) Gupta Electronics: Blurry PAN
    brief_gupta = adapter.get_merchant_brief("mer_gupta_electronics")
    assert brief_gupta is not None
    assert brief_gupta.priority == "HIGH"
    assert "blurry" in brief_gupta.one_line_brief.lower()
    assert "PAN_CARD" in brief_gupta.evidence_breakdown["kyc"]["blurry_docs"]

    # (c) Radhe Bakery: Missing Shop Photo
    brief_radhe = adapter.get_merchant_brief("mer_shree_radhe_bakery")
    assert brief_radhe is not None
    assert "missing" in brief_radhe.one_line_brief.lower()
    assert "SHOP_PHOTO" in brief_radhe.evidence_breakdown["kyc"]["missing_docs"]

    # (d) Apex Retail: All KYC passed OCR
    brief_apex = adapter.get_merchant_brief("mer_apex_retail")
    assert brief_apex is not None
    assert brief_apex.priority == "LOW"
    assert "passed ocr" in brief_apex.one_line_brief.lower()
    assert brief_apex.evidence_breakdown["kyc"]["all_passed"] is True

    # (e) Sharma Kirana: Dormancy sales drop 70% -> Kirana booster pitch
    brief_sharma = adapter.get_merchant_brief("mer_sharma_kirana")
    assert brief_sharma is not None
    assert "dropped" in brief_sharma.one_line_brief.lower() or "booster" in brief_sharma.one_line_brief.lower()
    assert brief_sharma.evidence_breakdown["activity"]["drop_percentage"] == 70


# -----------------------------------------------------------------------------
# 2. Route Recommendation Heuristic
# -----------------------------------------------------------------------------
def test_suggest_visit_order_heuristic(db: Session):
    adapter = MockFieldMateAdapter(db)
    route = adapter.suggest_visit_order("emp_sales_01", rep_lat=26.9150, rep_lon=75.8150)
    assert len(route) >= 4

    # High priority visits should appear first among scheduled visits
    scheduled = [r for r in route if r.visit_status == "SCHEDULED"]
    assert scheduled[0].priority == "HIGH"
    assert all(r.distance_km > 0 for r in route)
    assert all(r.planned_order >= 1 for r in route)


# -----------------------------------------------------------------------------
# 3. Voice Note Flow & Confirmation Gate (Core Invariant)
# -----------------------------------------------------------------------------
def test_voice_note_unconfirmed_draft_invariant(db: Session):
    adapter = MockFieldMateAdapter(db)

    # Pick scheduled visit
    visit = db.query(MerchantVisit).filter(MerchantVisit.id == "visit_jai_001_singh").first()
    assert visit is not None
    initial_version = visit.version
    assert visit.is_confirmed_by_rep is False

    # Extract draft from voice note
    transcript = "Spoke with Rajesh ji. He showed me the offline Soundbox, power adapter was loose. He is keen on UPI Soundbox 4G Pro and handed over cancelled cheque."
    draft = adapter.extract_voice_note_draft(
        visit_id=visit.id,
        raw_transcript=transcript,
        sales_rep_id="emp_sales_01",
    )

    # Invariant checks: Must be an unconfirmed draft
    assert draft.requires_rep_confirmation is True
    assert draft.extracted_candidate_fields["merchant_sentiment"] == "POSITIVE"

    # Verify DB has NOT confirmed or updated persistent CRM notes yet
    db.refresh(visit)
    assert visit.is_confirmed_by_rep is False
    assert visit.confirmed_notes is None
    assert visit.visit_status == "SCHEDULED"
    assert visit.version == initial_version  # Version did NOT increment yet


def test_confirm_visit_note_persists_and_audits(db: Session):
    adapter = MockFieldMateAdapter(db)
    visit = db.query(MerchantVisit).filter(MerchantVisit.id == "visit_jai_003_radhe").first()
    assert visit is not None
    expected_v = visit.version

    # Rep explicitly reviews and confirms note
    confirmed_notes = "Visited Radhe Krishna Bakery. Checked signboard and photographed storefront. Introduced Kirana Booster 0% MDR offer. Merchant agreed to follow up Friday."
    result = adapter.confirm_and_save_visit_note(
        visit_id=visit.id,
        expected_version=expected_v,
        confirmed_notes=confirmed_notes,
        lead_interest="INTERESTED_KIRANA_BOOSTER",
        sales_rep_id="emp_sales_01",
    )

    assert result.is_confirmed is True
    assert result.new_version == expected_v + 1
    assert result.audit_event_id is not None

    # Verify DB state
    db.refresh(visit)
    assert visit.is_confirmed_by_rep is True
    assert visit.visit_status == "COMPLETED"
    assert visit.confirmed_notes == confirmed_notes
    assert visit.lead_interest == "INTERESTED_KIRANA_BOOSTER"
    assert visit.version == expected_v + 1

    # Verify Audit Event exists
    audit = db.query(AuditEvent).filter(AuditEvent.id == result.audit_event_id).first()
    assert audit is not None
    assert audit.action == "CRM_VISIT_NOTE_SAVED"


# -----------------------------------------------------------------------------
# 4. Concurrency Guardrail (Optimistic Locking)
# -----------------------------------------------------------------------------
def test_optimistic_locking_concurrency_conflict(db: Session):
    adapter = MockFieldMateAdapter(db)
    visit = db.query(MerchantVisit).filter(MerchantVisit.id == "visit_jai_004_apex").first()
    assert visit is not None
    original_v = visit.version

    # Session A confirms with expected_version = original_v -> SUCCODS
    res_a = adapter.confirm_and_save_visit_note(
        visit_id=visit.id,
        expected_version=original_v,
        confirmed_notes="Session A: Verified storefront signboard and QR code.",
        lead_interest="VERIFIED_MERCHANT",
        sales_rep_id="emp_sales_01",
    )
    assert res_a.is_confirmed is True
    assert res_a.new_version == original_v + 1

    # Session B attempts to confirm with STALE version (original_v) -> MUST RAISE ConcurrencyConflictError
    with pytest.raises(ConcurrencyConflictError) as exc_info:
        adapter.confirm_and_save_visit_note(
            visit_id=visit.id,
            expected_version=original_v,  # Stale version!
            confirmed_notes="Session B concurrent write that would silently overwrite Session A.",
            lead_interest="OVERWRITE_ATTEMPT",
            sales_rep_id="emp_sales_01",
        )
    assert "Conflict: Visit was modified by another session" in str(exc_info.value)


# -----------------------------------------------------------------------------
# 5. Policy Guardrails (Disallowed Actions Enforced)
# -----------------------------------------------------------------------------
def test_policy_blocks_loan_auto_approval(db: Session):
    tools = FieldMateTools(db=db)
    visit = db.query(MerchantVisit).filter(MerchantVisit.id == "visit_jai_002_gupta").first()
    assert visit is not None

    # Rep tries to save note containing "loan approved"
    res = tools.save_structured_visit_note(
        visit_id=visit.id,
        expected_version=visit.version,
        confirmed_notes="Merchant accepted terms and loan approved for ₹50,000 immediately.",
        sales_rep_id="emp_sales_01",
    )
    assert res["saved"] is False
    assert res["error"] == "POLICY_VIOLATION"
    assert "cannot approve loans" in res["reason"]


def test_policy_blocks_unassigned_merchant_edit(db: Session):
    adapter = MockFieldMateAdapter(db)

    # Attempting to save note for a visit belonging to another rep
    with pytest.raises(RepPolicyViolationError) as exc_info:
        adapter.confirm_and_save_visit_note(
            visit_id="visit_jai_001_singh",
            expected_version=1,
            confirmed_notes="Unauthorized rep note",
            lead_interest="UNAUTHORIZED",
            sales_rep_id="emp_support_01",  # Not the assigned sales rep!
        )
    assert "Access denied" in str(exc_info.value)


# -----------------------------------------------------------------------------
# 6. Manager End-of-Day Summary Reflects Real Data
# -----------------------------------------------------------------------------
def test_manager_rep_summary(db: Session):
    adapter = MockFieldMateAdapter(db)
    summary = adapter.get_manager_rep_summary("emp_sales_01")

    assert summary.sales_rep_id == "emp_sales_01"
    assert summary.total_assigned_merchants >= 5
    assert summary.completed_visits_today >= 1  # seeded visit_jai_005_sharma is completed
    assert summary.completion_rate_pct >= 20
    assert len(summary.confirmed_visits) >= 1

    # Check seeded completed visit
    completed_sharma = next((v for v in summary.confirmed_visits if v["merchant_id"] == "mer_sharma_kirana"), None)
    assert completed_sharma is not None
    assert "Ramesh ji" in completed_sharma["confirmed_notes"]


# -----------------------------------------------------------------------------
# 7. LangGraph Agent Execution
# -----------------------------------------------------------------------------
def test_fieldmate_agent_langgraph(db: Session):
    agent = FieldMateAgent(db)

    # Route Planner
    route_res = agent.run(query_type="GET_ROUTE", sales_rep_id="emp_sales_01")
    assert route_res["chip_status"] == "executed"
    assert len(route_res["route_items"]) >= 4

    # Brief Generator
    brief_res = agent.run(
        query_type="GET_BRIEF",
        sales_rep_id="emp_sales_01",
        merchant_id="mer_singh_automobiles",
    )
    assert brief_res["chip_status"] == "executed"
    assert "Singh Automobiles" in brief_res["agent_reply"]


# -----------------------------------------------------------------------------
# 8. Saathi Brain Orchestrator Routing to FieldMate
# -----------------------------------------------------------------------------
def test_orchestrator_routes_to_fieldmate(db: Session):
    orchestrator = SaathiBrainOrchestrator(db)
    res = orchestrator.route_and_run(
        merchant_id="mer_sharma_kirana",
        query_text="Show my sales route today with fieldmate",
        actor_id="emp_sales_01",
    )
    assert res["agent"] == "FIELDMATE"
    assert "scheduled merchant visits" in res["reply"].lower()


# -----------------------------------------------------------------------------
# 9. API Endpoints Suite
# -----------------------------------------------------------------------------
def test_api_fieldmate_route(client: TestClient, sales_rep_token: str):
    res = client.get(
        "/employee/fieldmate/route",
        headers={"Authorization": f"Bearer {sales_rep_token}"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["sales_rep_id"] == "emp_sales_01"
    assert len(data["merchants"]) >= 4
    assert "heuristic" in data["disclaimer"].lower()


def test_api_fieldmate_brief(client: TestClient, sales_rep_token: str):
    res = client.get(
        "/employee/fieldmate/brief/mer_singh_automobiles",
        headers={"Authorization": f"Bearer {sales_rep_token}"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["merchant_id"] == "mer_singh_automobiles"
    assert data["priority"] == "HIGH"
    assert "Soundbox offline" in data["one_line_brief"]


def test_api_fieldmate_extract_and_confirm_flow(client: TestClient, sales_rep_token: str, db: Session):
    # Step 1: Extract candidate draft (unconfirmed)
    extract_res = client.post(
        "/employee/fieldmate/voice-note/extract",
        headers={"Authorization": f"Bearer {sales_rep_token}"},
        json={
            "visit_id": "visit_jai_001_singh",
            "raw_transcript": "Visited Singh Automobiles. Fixed loose power cable, soundbox powered back on. Merchant requested ₹50,000 loan info.",
        },
    )
    assert extract_res.status_code == 200, extract_res.text
    extract_data = extract_res.json()
    assert extract_data["requires_rep_confirmation"] is True
    version = extract_data["version"]

    # Step 2: Confirm visit note
    confirm_res = client.post(
        "/employee/fieldmate/voice-note/confirm",
        headers={"Authorization": f"Bearer {sales_rep_token}"},
        json={
            "visit_id": "visit_jai_001_singh",
            "expected_version": version,
            "confirmed_notes": "Rep verified: Soundbox power cable restored. Collected physical bank cheque. Follow-up for merchant loan next week.",
            "lead_interest": "INTERESTED_MERCHANT_LOAN",
        },
    )
    assert confirm_res.status_code == 200, confirm_res.text
    confirm_data = confirm_res.json()
    assert confirm_data["is_confirmed"] is True
    assert confirm_data["new_version"] == version + 1

    # Step 3: Concurrent attempt with old version returns 409
    stale_res = client.post(
        "/employee/fieldmate/voice-note/confirm",
        headers={"Authorization": f"Bearer {sales_rep_token}"},
        json={
            "visit_id": "visit_jai_001_singh",
            "expected_version": version,  # Old version!
            "confirmed_notes": "Stale duplicate note write",
            "lead_interest": "STALE",
        },
    )
    assert stale_res.status_code == 409, stale_res.text


def test_api_fieldmate_manager_summary(client: TestClient, manager_token: str):
    res = client.get(
        "/employee/fieldmate/manager-summary?sales_rep_id=emp_sales_01",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["sales_rep_id"] == "emp_sales_01"
    assert data["completed_visits_today"] >= 1
    assert len(data["confirmed_visits"]) >= 1
