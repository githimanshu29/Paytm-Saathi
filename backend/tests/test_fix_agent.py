import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.db.models import (
    Device,
    Task,
    TaskBucket,
    AuditEvent,
    ScheduledJob,
)
from app.adapters.device import MockDeviceAdapter
from app.adapters.speech import MockSpeechAdapter
from app.tools.fix import FixTools
from app.agents.fix import FixAgent
from app.agents.orchestrator import SaathiBrainOrchestrator
from app.core.clockwork import get_clockwork_scheduler


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


# 1. Device Adapter Telemetry
def test_device_adapter_telemetry(db):
    adapter = MockDeviceAdapter(db)
    device = adapter.get_device_by_serial("SB-DEL-404")
    assert device is not None
    assert device.serial_number == "SB-DEL-404"
    assert device.status == "OFFLINE"
    assert device.battery_level == 76

    diag = adapter.get_device_diagnostics("SB-DEL-404")
    assert diag is not None
    assert diag.status == "OFFLINE"
    assert diag.firmware_version == "v3.4.0"
    assert diag.sim_status is not None


# 2. Demo Toggle Flips Device Status
def test_device_adapter_toggle_demo(db):
    adapter = MockDeviceAdapter(db)
    initial_device = adapter.get_device_by_serial("SB-DEL-404")
    original_status = initial_device.status

    target = "ONLINE" if original_status == "OFFLINE" else "OFFLINE"
    flipped = adapter.flip_device_status("SB-DEL-404", target)
    assert flipped is True

    updated_device = adapter.get_device_by_serial("SB-DEL-404")
    assert updated_device.status == target

    # Flip back to original status for test determinism
    restored = adapter.flip_device_status("SB-DEL-404", original_status)
    assert restored is True


# 3. Speech Adapter Transcription & Synthesis
def test_speech_adapter_transcription_and_synthesis():
    speech = MockSpeechAdapter()

    # Transcription
    trans_res = speech.transcribe(
        audio_data="साउंडबॉक्स काम नहीं कर रहा है".encode("utf-8"),
        language_hint="hi-IN",
    )
    assert trans_res.text == "साउंडबॉक्स काम नहीं कर रहा है"
    assert trans_res.language_detected == "hi-IN"
    assert trans_res.confidence >= 0.90

    # Synthesis
    synth_res = speech.synthesize(
        text="आपका साउंडबॉक्स चालू हो गया है",
        language="hi-IN",
    )
    assert synth_res.audio_base64 is not None
    assert len(synth_res.audio_base64) > 10
    assert synth_res.mime_type == "audio/wav"
    assert synth_res.duration_seconds > 0.0


# 4. Fix Tools Policy Checks & Execution
def test_fix_tools_policy_and_execution(db):
    adapter = MockDeviceAdapter(db)
    tools = FixTools(adapter=adapter, db=db)

    # R0 tools
    status_res = tools.get_device_status(
        device_ref="SB-DEL-404",
        execution_id="exec_test_01",
        actor_id="mer_gupta_electronics",
    )
    assert status_res["found"] is True
    assert status_res["status"] == "OFFLINE"

    diag_res = tools.get_device_diagnostics(
        device_ref="SB-DEL-404",
        execution_id="exec_test_02",
        actor_id="mer_gupta_electronics",
    )
    assert diag_res["found"] is True
    assert "signal_strength_dbm" in diag_res

    slots_res = tools.get_technician_slots(
        city="Delhi",
        execution_id="exec_test_03",
        actor_id="mer_gupta_electronics",
    )
    assert len(slots_res) > 0

    # R1 restart tool
    restart_res = tools.request_remote_restart(
        device_ref="SB-DEL-404",
        execution_id="exec_test_04",
        actor_id="mer_gupta_electronics",
    )
    assert restart_res["success"] is True
    assert restart_res["status"] == "SIMULATED_REBOOTING"

    # Check Audit event created
    audit = (
        db.query(AuditEvent)
        .filter_by(action="REQUEST_REMOTE_RESTART", target="SB-DEL-404")
        .first()
    )
    assert audit is not None


# 5. Technician Task Booking & Idempotency Guard
def test_fix_technician_idempotency(db):
    adapter = MockDeviceAdapter(db)
    tools = FixTools(adapter=adapter, db=db)

    # First booking
    res1 = tools.create_technician_task(
        merchant_id="mer_gupta_electronics",
        device_ref="SB-DEL-404",
        slot_str="Tomorrow 10:00 AM - 12:00 PM",
        issue_description="Speaker hardware test failure",
        execution_id="exec_tech_01",
        actor_id="mer_gupta_electronics",
    )
    assert res1["success"] is True
    first_task_id = res1["task_id"]

    # Second booking attempt for same device
    res2 = tools.create_technician_task(
        merchant_id="mer_gupta_electronics",
        device_ref="SB-DEL-404",
        slot_str="Tomorrow 02:00 PM - 04:00 PM",
        issue_description="Duplicate attempt",
        execution_id="exec_tech_02",
        actor_id="mer_gupta_electronics",
    )
    assert res2["success"] is True
    assert res2["task_id"] == first_task_id
    assert res2.get("is_duplicate_idempotent") is True


# 6. Crash-Safe Clockwork Scheduler & Recovery
def test_clockwork_persistent_scheduling_and_recovery(db):
    clockwork = get_clockwork_scheduler()

    job = clockwork.schedule_device_recheck(
        db=db,
        merchant_id="mer_gupta_electronics",
        device_ref="SB-DEL-404",
        delay_seconds=1,
    )
    assert job is not None
    job_id = job.id

    # Verify persisted in DB
    job_record = db.query(ScheduledJob).filter_by(id=job_id).first()
    assert job_record is not None
    assert job_record.status in ["SCHEDULED", "RUNNING", "COMPLETED"]

    # Test recovery of pending jobs
    recovered_count = clockwork.recover_pending_jobs(db)
    assert isinstance(recovered_count, int)


# 7. Fix Agent: Offline Soundbox Guided Restart & Technician Booking
def test_fix_agent_offline_device_never_claims_verified(db):
    agent = FixAgent(db)

    # Ensure device is OFFLINE
    device = db.query(Device).filter_by(serial_number="SB-DEL-404").first()
    device.status = "OFFLINE"
    device.technician_visit_booked = False
    device.technician_slot = None
    db.commit()

    result = agent.run(
        merchant_id="mer_gupta_electronics",
        query_text="Soundbox SB-DEL-404 light is red and not playing any sound",
        actor_id="mer_gupta_electronics",
    )

    # CRITICAL INVARIANT: The agent must NEVER claim verified when device is still offline!
    assert result["chip_status"] != "verified"
    assert result["chip_status"] == "needs_human"
    assert result["step"] == "TECHNICIAN_DISPATCHED"
    assert "technician" in result["agent_reply"].lower()
    assert "visit" in result["agent_reply"].lower()
    assert result["action_card"] is not None
    assert result["action_card"]["type"] == "TECHNICIAN_VISIT_BOOKED"
    assert result["action_card"]["slot"] is not None

    # Check Task created in DB under NEEDS_HUMAN
    task = db.query(Task).filter_by(id=result["case_id"]).first()
    assert task is not None
    assert task.bucket == TaskBucket.NEEDS_HUMAN
    assert "SB-DEL-404" in task.title or "Soundbox" in task.title


# 8. Fix Agent: Online Device Resolves as Verified
def test_fix_agent_online_device_resolves_verified(db):
    agent = FixAgent(db)

    # Ensure SB-JAI-101 is ONLINE
    device = db.query(Device).filter_by(serial_number="SB-JAI-101").first()
    device.status = "ONLINE"
    device.battery_level = 88
    device.last_heartbeat = datetime.now(timezone.utc)
    db.commit()

    result = agent.run(
        merchant_id="mer_sharma_kirana",
        query_text="Soundbox SB-JAI-101 check status and battery",
        actor_id="mer_sharma_kirana",
    )

    assert result["chip_status"] == "verified"
    assert result["step"] == "DEVICE_HEALTHY"
    assert "ONLINE" in result["agent_reply"]
    assert "88%" in result["agent_reply"]
    assert result["action_card"] is None


# 9. Demo Toggle Endpoint Flips Fix Outcome
def test_demo_toggle_flips_fix_outcome(client, db):
    agent = FixAgent(db)
    adapter = MockDeviceAdapter(db)

    # 1. Start with OFFLINE
    adapter.flip_device_status("SB-DEL-404", "OFFLINE")
    res_offline = agent.run(
        merchant_id="mer_gupta_electronics",
        query_text="Check SB-DEL-404",
        actor_id="mer_gupta_electronics",
    )
    assert res_offline["chip_status"] == "needs_human"

    # 2. Call public demo toggle endpoint
    toggle_resp = client.post("/demo/device/SB-DEL-404/toggle")
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["new_status"] == "ONLINE"

    # 3. Re-run Fix Agent -> outcome flips to verified!
    res_online = agent.run(
        merchant_id="mer_gupta_electronics",
        query_text="Check SB-DEL-404 now after reboot",
        actor_id="mer_gupta_electronics",
    )
    assert res_online["chip_status"] == "verified"

    # Restore back to OFFLINE
    adapter.flip_device_status("SB-DEL-404", "OFFLINE")


# 10. Voice Chat API Endpoint
def test_voice_chat_api(client, merchant_token):
    response = client.post(
        "/merchant/voice/chat",
        headers={"Authorization": f"Bearer {merchant_token}"},
        json={
            "transcript": "साउंडबॉक्स काम नहीं कर रहा है",
            "language": "hi",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert data["speech_audio_base64"] is not None
    assert "chip_status" in data


# 11. Saathi Brain Orchestrator Routes Accurately
def test_saathi_brain_orchestrator(db):
    brain = SaathiBrainOrchestrator(db)

    # Route to Fix
    res_fix = brain.route_and_run(
        merchant_id="mer_sharma_kirana",
        query_text="Soundbox voice is silent and speaker not working",
        actor_id="mer_sharma_kirana",
    )
    assert res_fix["agent"] == "FIX"

    # Route to Resolve
    res_resolve = brain.route_and_run(
        merchant_id="mer_sharma_kirana",
        query_text="Customer says ₹250 UPI payment failed",
        actor_id="mer_sharma_kirana",
    )
    assert res_resolve["agent"] == "RESOLVE"

    # Greeting
    res_greet = brain.route_and_run(
        merchant_id="mer_sharma_kirana",
        query_text="Namaste Saathi",
        actor_id="mer_sharma_kirana",
    )
    assert res_greet["agent"] == "ORCHESTRATOR"
    assert "Namaste" in res_greet["reply"]


# 12. Employee Dashboard Cases and Timeline Reflects Technician Visit
def test_employee_cases_and_timeline_shows_technician_task(client, employee_token, db):
    # Book a technician task
    adapter = MockDeviceAdapter(db)
    tools = FixTools(adapter=adapter, db=db)
    res = tools.create_technician_task(
        merchant_id="mer_gupta_electronics",
        device_ref="SB-DEL-404",
        slot_str="Tomorrow 10:00 AM - 12:00 PM",
        issue_description="Soundbox power cycling failed",
        execution_id="exec_timeline_01",
        actor_id="mer_gupta_electronics",
    )
    task_id = res["task_id"]

    # Verify task in /employee/cases
    cases_resp = client.get(
        "/employee/cases?bucket=needs_human",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert cases_resp.status_code == 200
    cases_data = cases_resp.json()["cases"]
    matching_case = next((c for c in cases_data if c["id"] == task_id), None)
    assert matching_case is not None
    assert "Soundbox" in matching_case["title"] or "SB-DEL-404" in matching_case["title"]
    assert matching_case["bucket"] == "needs_human"

    # Verify timeline in /employee/cases/{id}/timeline
    timeline_resp = client.get(
        f"/employee/cases/{task_id}/timeline",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert timeline_resp.status_code == 200
    timeline_events = timeline_resp.json()["events"]
    assert len(timeline_events) > 0
    technician_event = next(
        (ev for ev in timeline_events if ev["action"] == "CREATE_TECHNICIAN_TASK"),
        None,
    )
    assert technician_event is not None
    assert technician_event["result"] == "CONFIRMED"
