import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.db.models import AuditEvent

@pytest.fixture
def client():
    return TestClient(app)

def test_health_returns_200_and_logs_audit_event(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["environment"] == "DEMO"
    assert data["service"] == "Paytm Saathi Backend"
    assert "audit_event_id" in data
    assert data["audit_event_id"] is not None

    # Verify that the audit row exists in the database
    db = SessionLocal()
    try:
        audit_row = db.query(AuditEvent).filter_by(id=data["audit_event_id"]).first()
        assert audit_row is not None
        assert audit_row.actor == "system"
        assert audit_row.action == "HEALTH_CHECK"
        assert audit_row.target == "backend_service"
        assert audit_row.result == "SUCCESS"
        assert audit_row.is_synthetic is True
        assert audit_row.environment == "DEMO"
    finally:
        db.close()
