from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Merchant
from app.api.auth import get_current_user
from app.adapters.onboard import MockOnboardAdapter
from app.schemas.onboard import (
    OnboardingChecklistResponse,
    DocumentItemSchema,
    DocumentUploadRequest,
    DocumentUploadResponse,
    VerificationSubmitRequest,
    VerificationSubmitResponse,
    PipelineResponse,
)
from app.policy.audit import audit_log

onboard_router = APIRouter(tags=["Onboarding & KYC"])

@onboard_router.get("/merchant/onboarding/checklist", response_model=OnboardingChecklistResponse)
def get_merchant_onboarding_checklist(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    merchant_id = user.get("sub", "mer_sharma_kirana")
    adapter = MockOnboardAdapter(db)
    chk = adapter.get_onboarding_checklist(merchant_id)

    if not chk:
        # Fallback to first merchant if not found
        first_merchant = db.query(Merchant).first()
        if first_merchant:
            chk = adapter.get_onboarding_checklist(first_merchant.id)

    if not chk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No onboarding application found for merchant {merchant_id}.",
        )

    return OnboardingChecklistResponse(
        found=True,
        merchant_id=chk.merchant_id,
        store_name=chk.store_name,
        city=chk.city,
        phone=chk.phone,
        onboarding_status=chk.onboarding_status,
        kyc_status=chk.kyc_status,
        current_step=chk.current_step,
        documents=[
            DocumentItemSchema(
                id=d.id,
                document_type=d.document_type,
                status=d.status,
                file_name=d.file_name,
                file_url=d.file_url,
                ocr_quality_flag=d.ocr_quality_flag,
                ocr_candidate_fields=d.ocr_candidate_fields,
                ocr_confidence=d.ocr_confidence,
                is_ocr_passed=d.is_ocr_passed,
                rejection_reason=d.rejection_reason,
                authorized_verification_status=d.authorized_verification_status,
                verified_at=d.verified_at,
            )
            for d in chk.documents
        ],
        missing_documents=chk.missing_documents,
        blurry_documents=chk.blurry_documents,
        can_submit_for_verification=chk.can_submit_for_verification,
        is_fully_verified=chk.is_fully_verified,
    )

@onboard_router.post("/merchant/onboarding/upload", response_model=DocumentUploadResponse)
def upload_merchant_document(
    req: DocumentUploadRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    merchant_id = req.merchant_id or user.get("sub", "mer_sharma_kirana")
    adapter = MockOnboardAdapter(db)

    quality_override = "BLURRY" if req.simulate_blur else None
    doc_record = adapter.upload_document(
        merchant_id=merchant_id,
        document_type=req.document_type.upper(),
        file_name=req.file_name,
        quality_override=quality_override,
    )

    if not doc_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Merchant {merchant_id} not found.",
        )

    updated_chk = adapter.get_onboarding_checklist(merchant_id)
    chk_dict = {
        "can_submit_for_verification": updated_chk.can_submit_for_verification if updated_chk else False,
        "current_step": updated_chk.current_step if updated_chk else "UNKNOWN",
        "missing_documents": updated_chk.missing_documents if updated_chk else [],
        "blurry_documents": updated_chk.blurry_documents if updated_chk else [],
    }

    if doc_record.status == "OCR_FAILED":
        msg = f"{req.document_type} rejected: {doc_record.rejection_reason}"
    else:
        msg = f"{req.document_type} uploaded and passed OCR. Candidate fields extracted (untrusted). Ready for verification."

    return DocumentUploadResponse(
        success=doc_record.status == "OCR_PASSED",
        merchant_id=merchant_id,
        document_type=doc_record.document_type,
        status=doc_record.status,
        ocr_quality_flag=doc_record.ocr_quality_flag or "UNKNOWN",
        is_ocr_passed=doc_record.is_ocr_passed,
        candidate_fields=doc_record.ocr_candidate_fields or {},
        untrusted=True,
        rejection_reason=doc_record.rejection_reason,
        checklist=chk_dict,
        message=msg,
    )

@onboard_router.post("/merchant/onboarding/submit-verification", response_model=VerificationSubmitResponse)
def submit_onboarding_verification(
    req: VerificationSubmitRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    merchant_id = req.merchant_id or user.get("sub", "mer_sharma_kirana")
    adapter = MockOnboardAdapter(db)
    res = adapter.submit_for_authorized_verification(merchant_id)

    if not res.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.message,
        )

    return VerificationSubmitResponse(
        success=res.success,
        merchant_id=res.merchant_id,
        application_status=res.application_status,
        kyc_status=res.kyc_status,
        message=res.message,
        verified_documents=res.verified_documents,
        audit_event_id=res.audit_event_id,
    )

@onboard_router.get("/employee/onboarding/pipeline", response_model=PipelineResponse)
def get_onboarding_pipeline(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    adapter = MockOnboardAdapter(db)
    pipeline_data = adapter.get_pipeline_applications()

    formatted_apps = []
    for chk in pipeline_data["applications"]:
        formatted_apps.append(
            OnboardingChecklistResponse(
                found=True,
                merchant_id=chk.merchant_id,
                store_name=chk.store_name,
                city=chk.city,
                phone=chk.phone,
                onboarding_status=chk.onboarding_status,
                kyc_status=chk.kyc_status,
                current_step=chk.current_step,
                documents=[
                    DocumentItemSchema(
                        id=d.id,
                        document_type=d.document_type,
                        status=d.status,
                        file_name=d.file_name,
                        file_url=d.file_url,
                        ocr_quality_flag=d.ocr_quality_flag,
                        ocr_candidate_fields=d.ocr_candidate_fields,
                        ocr_confidence=d.ocr_confidence,
                        is_ocr_passed=d.is_ocr_passed,
                        rejection_reason=d.rejection_reason,
                        authorized_verification_status=d.authorized_verification_status,
                        verified_at=d.verified_at,
                    )
                    for d in chk.documents
                ],
                missing_documents=chk.missing_documents,
                blurry_documents=chk.blurry_documents,
                can_submit_for_verification=chk.can_submit_for_verification,
                is_fully_verified=chk.is_fully_verified,
            )
        )

    return PipelineResponse(
        total_applications=pipeline_data["total_applications"],
        pending_applications=pipeline_data["pending_applications"],
        verified_applications=pipeline_data["verified_applications"],
        blurry_count=pipeline_data["blurry_count"],
        applications=formatted_apps,
    )

@onboard_router.post("/employee/onboarding/verify/{merchant_id}", response_model=VerificationSubmitResponse)
def employee_verify_merchant(
    merchant_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    adapter = MockOnboardAdapter(db)
    res = adapter.submit_for_authorized_verification(merchant_id)

    if not res.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.message,
        )

    return VerificationSubmitResponse(
        success=res.success,
        merchant_id=res.merchant_id,
        application_status=res.application_status,
        kyc_status=res.kyc_status,
        message=res.message,
        verified_documents=res.verified_documents,
        audit_event_id=res.audit_event_id,
    )
