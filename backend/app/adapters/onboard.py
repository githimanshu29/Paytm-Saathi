from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional, Protocol
from sqlalchemy.orm import Session

from app.db.models import Merchant, MerchantDocument, Task, TaskBucket, AuditEvent


@dataclass
class DocumentItemRecord:
    id: str
    document_type: str
    status: str
    file_name: Optional[str]
    file_url: Optional[str]
    ocr_quality_flag: Optional[str]
    ocr_candidate_fields: Optional[Dict[str, Any]]
    ocr_confidence: Optional[float]
    is_ocr_passed: bool
    rejection_reason: Optional[str]
    authorized_verification_status: str
    verified_at: Optional[str]


@dataclass
class OnboardingChecklistRecord:
    merchant_id: str
    store_name: str
    city: str
    phone: str
    onboarding_status: str
    kyc_status: str
    current_step: str
    documents: List[DocumentItemRecord]
    missing_documents: List[str]
    blurry_documents: List[str]
    can_submit_for_verification: bool
    is_fully_verified: bool


@dataclass
class OCRResultRecord:
    document_type: str
    file_name: str
    ocr_quality_flag: str  # CLEAR | BLURRY | CROPPED | GLARE
    is_ocr_passed: bool
    confidence: float
    candidate_fields: Dict[str, Any]  # Explicitly untrusted candidate fields
    rejection_reason: Optional[str]
    disclaimer: str = "Candidate OCR fields are explicitly UNTRUSTED until authorized verification."


@dataclass
class VerificationSubmissionRecord:
    success: bool
    merchant_id: str
    application_status: str
    kyc_status: str
    message: str
    verified_documents: List[str]
    audit_event_id: Optional[str] = None


class IOnboardAdapter(Protocol):
    def get_onboarding_checklist(self, merchant_id: str) -> Optional[OnboardingChecklistRecord]: ...
    def extract_document_fields(
        self,
        document_type: str,
        file_name: str,
        quality_override: Optional[str] = None,
    ) -> OCRResultRecord: ...
    def upload_document(
        self,
        merchant_id: str,
        document_type: str,
        file_name: str,
        quality_override: Optional[str] = None,
    ) -> Optional[DocumentItemRecord]: ...
    def submit_for_authorized_verification(self, merchant_id: str) -> VerificationSubmissionRecord: ...


class MockOnboardAdapter:
    """
    Deterministic mock OCR & KYC verification adapter.
    Core Invariants:
    1. OCR outputs are explicitly UNTRUSTED candidate fields with quality flags (e.g. 'BLURRY').
    2. OCR alone NEVER marks an application as verified or active.
    3. An application ONLY reaches 'ACTIVE' / 'VERIFIED' through the simulated authorized verification step.
    """

    MANDATORY_DOCUMENTS = ["PAN_CARD", "BANK_PROOF", "SHOP_PHOTO"]

    def __init__(self, db: Session):
        self.db = db

    def extract_document_fields(
        self,
        document_type: str,
        file_name: str,
        quality_override: Optional[str] = None,
    ) -> OCRResultRecord:
        """
        Deterministic mock OCR extraction.
        Returns candidate fields and quality flag — NEVER makes a final verification decision.
        """
        lower_name = file_name.lower()
        is_blurry = (
            quality_override == "BLURRY"
            or "blurry" in lower_name
            or "blur" in lower_name
            or "dark" in lower_name
        )
        is_cropped = quality_override == "CROPPED" or "crop" in lower_name

        if is_blurry:
            quality_flag = "BLURRY"
            is_passed = False
            confidence = 0.42
            rejection_reason = (
                f"Your {document_type.replace('_', ' ').title()} photo is blurry and illegible. "
                f"Please resend a sharp, well-lit photo."
            )
            candidate_fields = {
                "warning": "LOW_CONFIDENCE_UNTRUSTED_OCR",
                "confidence": confidence,
                "untrusted": True,
            }
        elif is_cropped:
            quality_flag = "CROPPED"
            is_passed = False
            confidence = 0.55
            rejection_reason = (
                f"Your {document_type.replace('_', ' ').title()} photo is cropped at the edges. "
                f"Please capture the entire document."
            )
            candidate_fields = {
                "warning": "PARTIAL_CROP_UNTRUSTED",
                "confidence": confidence,
                "untrusted": True,
            }
        else:
            quality_flag = "CLEAR"
            is_passed = True
            confidence = 0.96
            rejection_reason = None

            if document_type == "PAN_CARD":
                candidate_fields = {
                    "candidate_pan": "ABCDE1234F",
                    "candidate_name": "Applicant Store Owner",
                    "date_of_birth": "1988-04-12",
                    "confidence": confidence,
                    "untrusted": True,
                }
            elif document_type == "BANK_PROOF":
                candidate_fields = {
                    "candidate_account_no": "••••••••9821",
                    "candidate_ifsc": "PYTM0123456",
                    "bank_name": "Paytm Payments Bank / Partner Bank",
                    "account_holder": "Applicant Store Owner",
                    "confidence": confidence,
                    "untrusted": True,
                }
            elif document_type == "SHOP_PHOTO":
                candidate_fields = {
                    "signboard_text_detected": "Kirana & General Store",
                    "storefront_verified": True,
                    "gps_geofence_match": True,
                    "confidence": confidence,
                    "untrusted": True,
                }
            else:
                candidate_fields = {
                    "raw_text": "Extracted document text",
                    "confidence": confidence,
                    "untrusted": True,
                }

        return OCRResultRecord(
            document_type=document_type,
            file_name=file_name,
            ocr_quality_flag=quality_flag,
            is_ocr_passed=is_passed,
            confidence=confidence,
            candidate_fields=candidate_fields,
            rejection_reason=rejection_reason,
        )

    def get_onboarding_checklist(self, merchant_id: str) -> Optional[OnboardingChecklistRecord]:
        merchant = self.db.query(Merchant).filter_by(id=merchant_id).first()
        if not merchant:
            return None

        docs = self.db.query(MerchantDocument).filter_by(merchant_id=merchant_id).all()
        doc_map = {d.document_type: d for d in docs}

        doc_items: List[DocumentItemRecord] = []
        missing_docs: List[str] = []
        blurry_docs: List[str] = []
        all_ocr_passed = True

        for req_type in self.MANDATORY_DOCUMENTS:
            d = doc_map.get(req_type)
            if not d or d.status == "MISSING":
                missing_docs.append(req_type)
                all_ocr_passed = False
                doc_items.append(
                    DocumentItemRecord(
                        id=f"missing_{req_type.lower()}",
                        document_type=req_type,
                        status="MISSING",
                        file_name=None,
                        file_url=None,
                        ocr_quality_flag=None,
                        ocr_candidate_fields=None,
                        ocr_confidence=None,
                        is_ocr_passed=False,
                        rejection_reason=d.rejection_reason if d else f"{req_type.replace('_', ' ').title()} is missing.",
                        authorized_verification_status="PENDING",
                        verified_at=None,
                    )
                )
            else:
                if d.ocr_quality_flag == "BLURRY" or d.status == "OCR_FAILED":
                    blurry_docs.append(req_type)
                    all_ocr_passed = False
                elif not d.is_ocr_passed:
                    all_ocr_passed = False

                fields_dict = None
                if d.ocr_candidate_fields:
                    try:
                        fields_dict = json.loads(d.ocr_candidate_fields)
                    except Exception:
                        fields_dict = {"raw": d.ocr_candidate_fields}

                doc_items.append(
                    DocumentItemRecord(
                        id=d.id,
                        document_type=d.document_type,
                        status=d.status,
                        file_name=d.file_name,
                        file_url=d.file_url,
                        ocr_quality_flag=d.ocr_quality_flag,
                        ocr_candidate_fields=fields_dict,
                        ocr_confidence=d.ocr_confidence,
                        is_ocr_passed=d.is_ocr_passed,
                        rejection_reason=d.rejection_reason,
                        authorized_verification_status=d.authorized_verification_status,
                        verified_at=d.verified_at.strftime("%Y-%m-%d %H:%M:%S") if d.verified_at else None,
                    )
                )

        # Determine current step
        if merchant.status == "ACTIVE" and merchant.kyc_status == "VERIFIED":
            current_step = "COMPLETED"
        elif all_ocr_passed:
            current_step = "READY_FOR_AUTHORIZED_VERIFICATION"
        elif "PAN_CARD" in blurry_docs or "PAN_CARD" in missing_docs:
            current_step = "PAN_RESUBMISSION_REQUIRED"
        elif "BANK_PROOF" in missing_docs or "BANK_PROOF" in blurry_docs:
            current_step = "BANK_PROOF_REQUIRED"
        elif "SHOP_PHOTO" in missing_docs or "SHOP_PHOTO" in blurry_docs:
            current_step = "SHOP_PHOTO_REQUIRED"
        else:
            current_step = "DOCUMENTS_UNDER_REVIEW"

        return OnboardingChecklistRecord(
            merchant_id=merchant.id,
            store_name=merchant.store_name,
            city=merchant.city,
            phone=merchant.phone,
            onboarding_status=merchant.onboarding_status,
            kyc_status=merchant.kyc_status,
            current_step=current_step,
            documents=doc_items,
            missing_documents=missing_docs,
            blurry_documents=blurry_docs,
            can_submit_for_verification=all_ocr_passed and merchant.kyc_status != "VERIFIED",
            is_fully_verified=merchant.kyc_status == "VERIFIED",
        )

    def upload_document(
        self,
        merchant_id: str,
        document_type: str,
        file_name: str,
        quality_override: Optional[str] = None,
    ) -> Optional[DocumentItemRecord]:
        """
        Uploads a document, runs mock OCR, and records candidate fields and quality flag.
        INVARIANT: Sets status to OCR_PASSED or OCR_FAILED. Never marks KYC verified.
        """
        merchant = self.db.query(Merchant).filter_by(id=merchant_id).first()
        if not merchant:
            return None

        ocr_res = self.extract_document_fields(document_type, file_name, quality_override)

        doc = self.db.query(MerchantDocument).filter_by(
            merchant_id=merchant_id, document_type=document_type
        ).first()

        now = datetime.now(timezone.utc)
        if not doc:
            doc = MerchantDocument(
                merchant_id=merchant_id,
                tenant_id=merchant.tenant_id,
                document_type=document_type,
                status="OCR_PASSED" if ocr_res.is_ocr_passed else "OCR_FAILED",
                file_name=file_name,
                file_url=f"https://paytm-saathi.demo/uploads/{file_name}",
                ocr_quality_flag=ocr_res.ocr_quality_flag,
                ocr_candidate_fields=json.dumps(ocr_res.candidate_fields),
                ocr_confidence=ocr_res.confidence,
                is_ocr_passed=ocr_res.is_ocr_passed,
                rejection_reason=ocr_res.rejection_reason,
                authorized_verification_status="PENDING",
                created_at=now,
                updated_at=now,
            )
            self.db.add(doc)
        else:
            doc.file_name = file_name
            doc.file_url = f"https://paytm-saathi.demo/uploads/{file_name}"
            doc.ocr_quality_flag = ocr_res.ocr_quality_flag
            doc.ocr_candidate_fields = json.dumps(ocr_res.candidate_fields)
            doc.ocr_confidence = ocr_res.confidence
            doc.is_ocr_passed = ocr_res.is_ocr_passed
            doc.rejection_reason = ocr_res.rejection_reason
            doc.status = "OCR_PASSED" if ocr_res.is_ocr_passed else "OCR_FAILED"
            doc.updated_at = now

        # Update merchant status to UNDER_REVIEW if not already active
        if merchant.status != "ACTIVE":
            merchant.onboarding_status = "UNDER_REVIEW"
            merchant.kyc_status = "IN_VERIFICATION"

        self.db.commit()
        self.db.refresh(doc)

        fields_dict = None
        if doc.ocr_candidate_fields:
            try:
                fields_dict = json.loads(doc.ocr_candidate_fields)
            except Exception:
                fields_dict = {"raw": doc.ocr_candidate_fields}

        return DocumentItemRecord(
            id=doc.id,
            document_type=doc.document_type,
            status=doc.status,
            file_name=doc.file_name,
            file_url=doc.file_url,
            ocr_quality_flag=doc.ocr_quality_flag,
            ocr_candidate_fields=fields_dict,
            ocr_confidence=doc.ocr_confidence,
            is_ocr_passed=doc.is_ocr_passed,
            rejection_reason=doc.rejection_reason,
            authorized_verification_status=doc.authorized_verification_status,
            verified_at=doc.verified_at.strftime("%Y-%m-%d %H:%M:%S") if doc.verified_at else None,
        )

    def submit_for_authorized_verification(self, merchant_id: str) -> VerificationSubmissionRecord:
        """
        Simulates the external authorized verification step (NSDL / Bank Penny Drop / Location check).
        Only when this step succeeds are merchant status marked ACTIVE and kyc_status VERIFIED.
        """
        merchant = self.db.query(Merchant).filter_by(id=merchant_id).first()
        if not merchant:
            return VerificationSubmissionRecord(
                success=False,
                merchant_id=merchant_id,
                application_status="UNKNOWN",
                kyc_status="UNKNOWN",
                message="Merchant application not found.",
                verified_documents=[],
            )

        checklist = self.get_onboarding_checklist(merchant_id)
        if not checklist or not checklist.can_submit_for_verification:
            failed_reasons = []
            if checklist:
                if checklist.missing_documents:
                    failed_reasons.append(f"Missing items: {', '.join(checklist.missing_documents)}")
                if checklist.blurry_documents:
                    failed_reasons.append(f"Blurry/unreadable items: {', '.join(checklist.blurry_documents)}")
            msg = f"Cannot submit for verification. {' | '.join(failed_reasons)}"
            return VerificationSubmissionRecord(
                success=False,
                merchant_id=merchant_id,
                application_status=merchant.status,
                kyc_status=merchant.kyc_status,
                message=msg,
                verified_documents=[],
            )

        # Execute simulated authorized verification step
        now = datetime.now(timezone.utc)
        docs = self.db.query(MerchantDocument).filter_by(merchant_id=merchant_id).all()
        verified_names = []
        for d in docs:
            d.authorized_verification_status = "VERIFIED"
            d.status = "VERIFIED"
            d.verified_at = now
            verified_names.append(d.document_type)

        merchant.onboarding_status = "COMPLETED"
        merchant.kyc_status = "VERIFIED"
        merchant.status = "ACTIVE"

        audit_ev = AuditEvent(
            tenant_id=merchant.tenant_id,
            actor="authorized_kyc_verification_engine",
            action="AUTHORIZED_KYC_VERIFICATION_COMPLETED",
            target=merchant.id,
            result="SUCCESS",
            policy_decision_id="dec_authorized_kyc_gate",
            is_synthetic=True,
            environment="DEMO",
            created_at=now,
        )
        self.db.add(audit_ev)

        self.db.commit()

        return VerificationSubmissionRecord(
            success=True,
            merchant_id=merchant.id,
            application_status="ACTIVE",
            kyc_status="VERIFIED",
            message="Authorized external KYC verification completed successfully. Merchant account is now ACTIVE.",
            verified_documents=verified_names,
            audit_event_id=audit_ev.id,
        )

    def get_pipeline_applications(self) -> Dict[str, Any]:
        """
        Retrieves all merchant onboarding applications for the Employee Pipeline view.
        """
        merchants = self.db.query(Merchant).order_by(Merchant.created_at.desc()).all()
        applications = []
        blurry_count = 0
        pending_count = 0
        verified_count = 0

        for m in merchants:
            chk = self.get_onboarding_checklist(m.id)
            if not chk:
                continue
            if chk.is_fully_verified:
                verified_count += 1
            else:
                pending_count += 1
            if chk.blurry_documents:
                blurry_count += 1

            applications.append(chk)

        return {
            "total_applications": len(applications),
            "pending_applications": pending_count,
            "verified_applications": verified_count,
            "blurry_count": blurry_count,
            "applications": applications,
        }
