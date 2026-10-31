import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def employee_token(client):
    res = client.post(
        "/auth/employee/login",
        json={"email": "support@paytm.demo", "password": "Demo@1234"},
    )
    assert res.status_code == 200
    return res.json()["access_token"]

@pytest.fixture
def merchant_token(client):
    phone = "+919876543210"
    client.post("/auth/merchant/request-otp", json={"phone": phone})
    res = client.post("/auth/merchant/verify-otp", json={"phone": phone, "otp": "123456"})
    assert res.status_code == 200
    return res.json()["access_token"]

def test_employee_dashboard_summary(client, employee_token):
    res = client.get(
        "/employee/dashboard/summary",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert res.status_code == 200
    data = res.json()

    # Confirms real numbers from seeded data
    assert data["total_merchants"] == 4
    assert data["active_devices"] >= 1
    assert data["total_devices"] >= 3
    assert data["pending_approvals"] >= 1
    assert data["needs_human_cases"] >= 1
    assert data["total_tasks"] >= 4
    assert data["total_transactions_paise"] > 0
    assert "₹" in data["total_transactions_formatted"]

def test_employee_audit_log_live_source(client, employee_token):
    # 1. Trigger health check to create a fresh audit_events row
    health_res = client.get("/health")
    assert health_res.status_code == 200
    health_data = health_res.json()
    new_event_id = health_data["audit_event_id"]

    # 2. Query audit log
    log_res = client.get(
        "/employee/audit-log?limit=20",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert log_res.status_code == 200
    log_data = log_res.json()

    assert log_data["total"] > 0
    event_ids = [ev["id"] for ev in log_data["events"]]
    assert new_event_id in event_ids, "Newly created audit event must appear in live audit log"

    # Verify event structure
    target_event = next(ev for ev in log_data["events"] if ev["id"] == new_event_id)
    assert target_event["actor"] == "system"
    assert target_event["action"] == "HEALTH_CHECK"
    assert target_event["target"] == "backend_service"
    assert target_event["result"] == "SUCCESS"
    assert target_event["environment"] == "DEMO"

def test_employee_cases_unified_view(client, employee_token):
    res = client.get(
        "/employee/cases",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["total"] >= 4
    buckets = {c["bucket"] for c in data["cases"]}
    assert "verified" in buckets
    assert "awaiting_approval" in buckets
    assert "needs_human" in buckets

    # Confirm approval linkage for task_verma_001
    awaiting_case = next((c for c in data["cases"] if c["bucket"] == "awaiting_approval"), None)
    assert awaiting_case is not None
    assert awaiting_case["approval"] is not None
    assert awaiting_case["approval"]["decision"] == "PENDING"
    assert awaiting_case["approval"]["risk_tier"] == "R2"

def test_employee_case_timeline(client, employee_token):
    # Fetch cases
    cases_res = client.get("/employee/cases", headers={"Authorization": f"Bearer {employee_token}"})
    case_id = cases_res.json()["cases"][0]["id"]

    res = client.get(
        f"/employee/cases/{case_id}/timeline",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == case_id
    assert len(data["events"]) > 0
    assert "actor" in data["events"][0]
    assert "action" in data["events"][0]

def test_employee_endpoints_reject_merchant_token(client, merchant_token):
    res = client.get(
        "/employee/dashboard/summary",
        headers={"Authorization": f"Bearer {merchant_token}"},
    )
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]
