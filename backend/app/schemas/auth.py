from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class MerchantOTPRequest(BaseModel):
    phone: str = Field(..., description="10-digit Indian phone number or prefixed with +91")

class MerchantOTPResponse(BaseModel):
    message: str
    phone: str
    expires_in_seconds: int = 300

class MerchantOTPVerify(BaseModel):
    phone: str = Field(..., description="Phone number used for OTP request")
    otp: str = Field(..., description="6-digit OTP code")

class EmployeeLoginRequest(BaseModel):
    email: str = Field(..., description="Corporate employee email")
    password: str = Field(..., description="Account password")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_type: str  # "merchant" or "employee"
    user: Dict[str, Any]

class UserMeResponse(BaseModel):
    id: str
    user_type: str
    role: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    store_name: Optional[str] = None
    tenant_id: Optional[str] = None
    environment: str = "DEMO"
