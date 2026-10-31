import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token

@pytest.fixture
def client():
    return TestClient(app)

def test_merchant_otp_request_and_verify_flow(client):
    phone = "+919876543210"
    
    # 1. Request OTP
    req_resp = client.post("/auth/merchant/request-otp", json={"phone": phone})
    assert req_resp.status_code == 200
    req_data = req_resp.json()
    assert "123456" in req_data["message"]
    assert req_data["phone"] == phone

    # 2. Verify with valid OTP
    verify_resp = client.post("/auth/merchant/verify-otp", json={"phone": phone, "otp": "123456"})
    assert verify_resp.status_code == 200
    token_data = verify_resp.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["user_type"] == "merchant"
    assert token_data["user"]["store_name"] == "Sharma Kirana Store"

    # 3. Access protected /auth/me endpoint
    token = token_data["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["role"] == "merchant"
    assert me_data["store_name"] == "Sharma Kirana Store"

def test_merchant_otp_verify_invalid_code(client):
    resp = client.post("/auth/merchant/verify-otp", json={"phone": "+919876543210", "otp": "999999"})
    assert resp.status_code == 401
    assert "Invalid or expired OTP" in resp.json()["detail"]

def test_employee_login_all_seeded_roles(client):
    test_accounts = [
        ("support@paytm.demo", "support_agent"),
        ("manager@paytm.demo", "manager"),
        ("sales@paytm.demo", "sales_rep"),
        ("admin@paytm.demo", "admin"),
    ]

    for email, expected_role in test_accounts:
        resp = client.post("/auth/employee/login", json={"email": email, "password": "Demo@1234"})
        assert resp.status_code == 200, f"Failed for {email}: {resp.text}"
        data = resp.json()
        assert data["token_type"] == "bearer"
        assert data["user_type"] == "employee"
        assert data["user"]["role"] == expected_role
        
        # Test protected /auth/me endpoint
        token = data["access_token"]
        me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["role"] == expected_role
        assert me_data["email"] == email

def test_employee_login_invalid_password(client):
    resp = client.post("/auth/employee/login", json={"email": "support@paytm.demo", "password": "WrongPassword"})
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.json()["detail"]

def test_employee_login_nonexistent_email(client):
    resp = client.post("/auth/employee/login", json={"email": "ghost@paytm.demo", "password": "Demo@1234"})
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.json()["detail"]

def test_protected_route_rejects_missing_token(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert "Missing or malformed Authorization header" in resp.json()["detail"]

def test_protected_route_rejects_invalid_token(client):
    resp = client.get("/auth/me", headers={"Authorization": "Bearer gibberish_token_12345"})
    assert resp.status_code == 401
    assert "Invalid token" in resp.json()["detail"]

def test_protected_route_rejects_expired_token(client):
    # Create expired token
    expired_token = create_access_token(
        {"sub": "emp_support_01", "user_type": "employee", "role": "support_agent"},
        expires_delta=timedelta(seconds=-10)
    )
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401
    assert "Token has expired" in resp.json()["detail"]
