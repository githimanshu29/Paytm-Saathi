from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class DocumentItemSchema(BaseModel):
    id: str
    document_type: str
    status: str  # MISSING | OCR_PASSED | OCR_FAILED | VERIFIED
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    ocr_quality_flag: Optional[str] = None  # CLEAR | BLURRY | CROPPED | GLARE
    ocr_candidate_fields: Optional[Dict[str, Any]] = None  # Candidate fields only, untrusted
    ocr_confidence: Optional[float] = None
    is_ocr_passed: bool = False
    rejection_reason: Optional[str] = None
    authorized_verification_status: str = "PENDING"
    verified_at: Optional[str] = None

class OnboardingChecklistResponse(BaseModel):
    found: bool = True
    merchant_id: str
    store_name: str
    city: str
    phone: str
    onboarding_status: str
    kyc_status: str
    current_step: str
    documents: List[DocumentItemSchema]
    missing_documents: List[str]
    blurry_documents: List[str]
    can_submit_for_verification: bool
    is_fully_verified: bool

class DocumentUploadRequest(BaseModel):
    merchant_id: Optional[str] = None
    document_type: str = Field(..., description="PAN_CARD, BANK_PROOF, or SHOP_PHOTO")
    file_name: str
    file_base64: Optional[str] = None
    simulate_blur: bool = False

class DocumentUploadResponse(BaseModel):
    success: bool
    merchant_id: str
    document_type: str
    status: str
    ocr_quality_flag: str
    is_ocr_passed: bool
    candidate_fields: Dict[str, Any]
    untrusted: bool = True
    rejection_reason: Optional[str] = None
    checklist: Optional[Dict[str, Any]] = None
    message: str

class VerificationSubmitRequest(BaseModel):
    merchant_id: Optional[str] = None

class VerificationSubmitResponse(BaseModel):
    success: bool
    merchant_id: str
    application_status: str
    kyc_status: str
    message: str
    verified_documents: List[str]
    audit_event_id: Optional[str] = None

class PipelineResponse(BaseModel):
    total_applications: int
    pending_applications: int
    verified_applications: int
    blurry_count: int
    applications: List[OnboardingChecklistResponse]
