import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Merchant, Employee
from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    verify_password,
)
from app.policy.audit import audit_log
from app.schemas.auth import (
    MerchantOTPRequest,
    MerchantOTPResponse,
    MerchantOTPVerify,
    EmployeeLoginRequest,
    TokenResponse,
    UserMeResponse,
)

logger = logging.getLogger("paytm_saathi.auth")
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])

def normalize_phone(phone: str) -> str:
    cleaned = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
    if not cleaned.startswith("+"):
        if len(cleaned) == 10:
            cleaned = "+91" + cleaned
    return cleaned

def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ")[1].strip()
    payload = decode_access_token(token)
    return payload

@auth_router.post("/merchant/request-otp", response_model=MerchantOTPResponse)
def request_merchant_otp(req: MerchantOTPRequest, db: Session = Depends(get_db)):
    phone = normalize_phone(req.phone)
    if len(phone) < 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid phone number format. Provide a 10-digit mobile number.",
        )

    # In mock demo mode, log the fixed demo OTP to console
    print(f"\n=======================================================")
    print(f" [MOCK OTP SMS] Merchant: {phone} | DEMO OTP: {settings.DEMO_OTP} ")
    print(f"=======================================================\n")
    logger.info(f"Generated mock OTP for {phone}: {settings.DEMO_OTP}")

    audit_log(
        db=db,
        actor=phone,
        action="MERCHANT_OTP_REQUESTED",
        target="sms_gateway_mock",
        result="SUCCESS",
        policy_decision_id="dec_otp_auto",
    )

    return MerchantOTPResponse(
        message=f"OTP sent successfully to {phone}. Use demo OTP: {settings.DEMO_OTP}",
        phone=phone,
        expires_in_seconds=300,
    )

@auth_router.post("/merchant/verify-otp", response_model=TokenResponse)
def verify_merchant_otp(req: MerchantOTPVerify, db: Session = Depends(get_db)):
    phone = normalize_phone(req.phone)
    if req.otp != settings.DEMO_OTP and req.otp != "123456":
        audit_log(
            db=db,
            actor=phone,
            action="MERCHANT_OTP_VERIFY_FAILED",
            target="auth_merchant",
            result="FAILED",
            policy_decision_id="dec_otp_invalid",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP. Please use demo code 123456.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Lookup existing merchant by phone
    merchant = db.query(Merchant).filter(
        (Merchant.phone == phone) | 
        (Merchant.phone == req.phone) |
        (Merchant.phone.endswith(req.phone[-10:] if len(req.phone) >= 10 else req.phone))
    ).first()

    # If phone not found in seeded list, link to primary demo merchant
    if not merchant:
        merchant = db.query(Merchant).first()
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No demo merchant records available. Please run seed_demo_data.py.",
            )

    token_data = {
        "sub": merchant.id,
        "user_type": "merchant",
        "role": "merchant",
        "phone": merchant.phone,
        "store_name": merchant.store_name,
        "tenant_id": merchant.tenant_id,
    }
    access_token = create_access_token(token_data)

    audit_log(
        db=db,
        actor=merchant.id,
        action="MERCHANT_LOGIN_SUCCESS",
        target="auth_session",
        result="SUCCESS",
        policy_decision_id="dec_login_allowed",
        tenant_id=merchant.tenant_id,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_type="merchant",
        user={
            "id": merchant.id,
            "store_name": merchant.store_name,
            "merchant_name": merchant.merchant_name,
            "phone": merchant.phone,
            "city": merchant.city,
            "status": merchant.status,
            "role": "merchant",
        },
    )

@auth_router.post("/employee/login", response_model=TokenResponse)
def employee_login(req: EmployeeLoginRequest, db: Session = Depends(get_db)):
    email_clean = req.email.strip().lower()
    employee = db.query(Employee).filter(Employee.email == email_clean).first()

    if not employee or not verify_password(req.password, employee.hashed_password):
        audit_log(
            db=db,
            actor=email_clean,
            action="EMPLOYEE_LOGIN_FAILED",
            target="auth_employee",
            result="INVALID_CREDENTIALS",
            policy_decision_id="dec_auth_denied",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = {
        "sub": employee.id,
        "user_type": "employee",
        "role": employee.role.value,
        "email": employee.email,
        "name": employee.name,
        "tenant_id": employee.tenant_id,
    }
    access_token = create_access_token(token_data)

    audit_log(
        db=db,
        actor=employee.id,
        action="EMPLOYEE_LOGIN_SUCCESS",
        target="auth_session",
        result="SUCCESS",
        policy_decision_id="dec_login_allowed",
        tenant_id=employee.tenant_id,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_type="employee",
        user={
            "id": employee.id,
            "name": employee.name,
            "email": employee.email,
            "role": employee.role.value,
        },
    )

@auth_router.get("/me", response_model=UserMeResponse)
def get_me(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = user.get("sub")
    user_type = user.get("user_type")

    if user_type == "merchant":
        m = db.query(Merchant).filter_by(id=user_id).first()
        return UserMeResponse(
            id=user_id,
            user_type="merchant",
            role="merchant",
            name=m.merchant_name if m else user.get("store_name", "Merchant"),
            store_name=m.store_name if m else user.get("store_name"),
            phone=m.phone if m else user.get("phone"),
            tenant_id=m.tenant_id if m else user.get("tenant_id"),
            environment=settings.ENVIRONMENT,
        )
    else:
        emp = db.query(Employee).filter_by(id=user_id).first()
        return UserMeResponse(
            id=user_id,
            user_type="employee",
            role=emp.role.value if emp else user.get("role", "support_agent"),
            name=emp.name if emp else user.get("name", "Employee"),
            email=emp.email if emp else user.get("email"),
            tenant_id=emp.tenant_id if emp else user.get("tenant_id"),
            environment=settings.ENVIRONMENT,
        )
