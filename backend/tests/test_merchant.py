import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.db.models import AuditEvent

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def merchant_token(client):
    # Log in as demo merchant
    phone = "+919876543210"
    client.post("/auth/merchant/request-otp", json={"phone": phone})
    res = client.post("/auth/merchant/verify-otp", json={"phone": phone, "otp": "123456"})
    return res.json()["access_token"]

def test_merchant_summary_authenticated(client, merchant_token):
    res = client.get("/merchant/me/summary", headers={"Authorization": f"Bearer {merchant_token}"})
    assert res.status_code == 200
    data = res.json()

    # Store info from seeded rows
    assert data["store_name"] == "Sharma Kirana Store"
    assert data["city"] == "Jaipur"
    assert data["status"] == "ACTIVE"

    # Device card data from seeded rows
    assert data["device"] is not None
    assert data["device"]["device_type"] == "Soundbox 4G Pro"
    assert data["device"]["serial_number"] == "SB-JAI-101"
    assert data["device"]["status"] == "ONLINE"
    assert data["device"]["chip_status"] == "verified"
    assert data["device"]["battery_level"] == 88

    # Payment summary from seeded transactions (15000 + 45000 + 32000 confirmed = 92000 paise)
    payments = data["payments"]
    assert payments["today_total_paise"] == 92000
    assert "₹920.00" in payments["today_total_formatted"]
    assert payments["today_count"] == 3
    assert payments["chip_status"] == "verified"
    assert len(payments["recent_transactions"]) >= 3

    # Dues summary from seeded receivables
    dues = data["dues"]
    assert dues["total_dues_paise"] == 85000  # 850.00 INR
    assert "₹850.00" in dues["total_dues_formatted"]
    assert dues["pending_count"] == 1
    assert dues["chip_status"] == "awaiting_approval"
    assert len(dues["receivables"]) >= 1
    assert dues["receivables"][0]["customer_name"] == "Vikram Singh"

def test_merchant_summary_unauthenticated_rejected(client):
    res = client.get("/merchant/me/summary")
    assert res.status_code == 401
    assert "Authorization header" in res.json()["detail"]

def test_merchant_chat_message_roundtrip(client, merchant_token):
    msg = "Customer Alok ₹250 auto reversal status check"
    res = client.post(
        "/merchant/chat/message",
        headers={"Authorization": f"Bearer {merchant_token}"},
        json={"message": msg},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["sender"] == "saathi"
    assert data["branch"] == "A_AUTO_REVERSAL"
    assert data["chip_status"] == "verified"
    assert "24–48 banking hours" in data["reply"]
    assert data["is_synthetic"] is True

    # Verify audit event logged
    db = SessionLocal()
    try:
        audit = (
            db.query(AuditEvent)
            .filter_by(action="MERCHANT_CHAT_MESSAGE_RECEIVED")
            .order_by(AuditEvent.created_at.desc())
            .first()
        )
        assert audit is not None
        assert audit.result == "RECEIVED"
    finally:
        db.close()
