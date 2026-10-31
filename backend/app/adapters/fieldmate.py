from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from typing import Any, Dict, List, Optional, Protocol
from sqlalchemy.orm import Session

from app.db.models import (
    Merchant,
    MerchantVisit,
    MerchantDocument,
    Device,
    MerchantActivityMetric,
    Settlement,
    AuditEvent,
    Employee,
)


def calculate_haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in km."""
    R = 6371.0  # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)


class ConcurrencyConflictError(Exception):
    """Raised when an optimistic lock version check fails."""
    pass


class RepPolicyViolationError(Exception):
    """Raised when a rep attempts a disallowed CRM action."""
    pass


@dataclass
class MerchantRouteItem:
    visit_id: str
    merchant_id: str
    store_name: str
    merchant_name: str
    phone: str
    city: str
    latitude: float
    longitude: float
    distance_km: float
    priority: str
    planned_order: int
    visit_status: str
    evidence_backed_brief: str
    brief_cause_type: str
    lead_status: str
    is_confirmed_by_rep: bool
    version: int


@dataclass
class MerchantBriefDetail:
    merchant_id: str
    store_name: str
    merchant_name: str
    phone: str
    city: str
    latitude: float
    longitude: float
    distance_km: float
    priority: str
    one_line_brief: str
    brief_cause_type: str
    evidence_breakdown: Dict[str, Any]
    talking_points: List[str]
    recommended_pitch: str
    visit_id: Optional[str]
    version: int


@dataclass
class VoiceNoteCandidateDraft:
    visit_id: str
    merchant_id: str
    raw_transcript: str
    extracted_candidate_fields: Dict[str, Any]
    proposed_lead_interest: Optional[str]
    requires_rep_confirmation: bool = True
    disclaimer: str = "Voice note extraction is an UNCONFIRMED draft. Rep must review and confirm before CRM persistence."
    version: int = 1


@dataclass
class ConfirmedVisitNoteResult:
    visit_id: str
    merchant_id: str
    is_confirmed: bool
    confirmed_notes: str
    lead_interest: Optional[str]
    new_version: int
    audit_event_id: str
    message: str


@dataclass
class ManagerRepSummary:
    sales_rep_id: str
    rep_name: str
    total_assigned_merchants: int
    planned_visits_today: int
    completed_visits_today: int
    completion_rate_pct: int
    leads_generated_today: int
    confirmed_visits: List[Dict[str, Any]]


class IFieldMateAdapter(Protocol):
    def get_assigned_merchants(
        self, sales_rep_id: str, rep_lat: float, rep_lon: float
    ) -> List[MerchantRouteItem]: ...

    def suggest_visit_order(
        self, sales_rep_id: str, rep_lat: float, rep_lon: float
    ) -> List[MerchantRouteItem]: ...

    def get_merchant_brief(
        self, merchant_id: str, rep_lat: float, rep_lon: float
    ) -> Optional[MerchantBriefDetail]: ...

    def extract_voice_note_draft(
        self, visit_id: str, raw_transcript: str, sales_rep_id: str
    ) -> VoiceNoteCandidateDraft: ...

    def confirm_and_save_visit_note(
        self,
        visit_id: str,
        expected_version: int,
        confirmed_notes: str,
        lead_interest: Optional[str],
        sales_rep_id: str,
    ) -> ConfirmedVisitNoteResult: ...

    def get_manager_rep_summary(self, sales_rep_id: str) -> ManagerRepSummary: ...


class MockFieldMateAdapter:
    """
    Authoritative adapter for Field Sales Reps.
    Enforces:
    - Truthful briefs constructed only from real DB state.
    - Zero auto-saves without explicit rep review and confirmation.
    - Optimistic concurrency control via version counter.
    - Strict boundary protection (reps cannot edit unassigned merchants or approve loans).
    """

    def __init__(self, db: Session):
        self.db = db

    def get_assigned_merchants(
        self, sales_rep_id: str, rep_lat: float = 26.9150, rep_lon: float = 75.8150
    ) -> List[MerchantRouteItem]:
        """Fetch all visits and merchants assigned to the sales rep."""
        visits = (
            self.db.query(MerchantVisit)
            .filter(MerchantVisit.sales_rep_id == sales_rep_id)
            .order_by(MerchantVisit.planned_order.asc())
            .all()
        )

        results = []
        for v in visits:
            m = v.merchant
            lat = m.latitude or 26.9150
            lon = m.longitude or 75.8150
            dist = calculate_haversine_km(rep_lat, rep_lon, lat, lon)

            results.append(
                MerchantRouteItem(
                    visit_id=v.id,
                    merchant_id=m.id,
                    store_name=m.store_name,
                    merchant_name=m.merchant_name,
                    phone=m.phone,
                    city=m.city,
                    latitude=lat,
                    longitude=lon,
                    distance_km=dist,
                    priority=v.priority,
                    planned_order=v.planned_order,
                    visit_status=v.visit_status,
                    evidence_backed_brief=v.evidence_backed_brief,
                    brief_cause_type=v.brief_cause_type,
                    lead_status=m.lead_status or "PROSPECT",
                    is_confirmed_by_rep=v.is_confirmed_by_rep,
                    version=v.version,
                )
            )
        return results

    def suggest_visit_order(
        self, sales_rep_id: str, rep_lat: float = 26.9150, rep_lon: float = 75.8150
    ) -> List[MerchantRouteItem]:
        """
        Suggests a visit order balancing urgency priority and proximity.
        Explicitly a recommendation heuristic, not a guaranteed-optimal route.
        Priority: HIGH (100) > MEDIUM (50) > LOW (10), sorted then by distance.
        """
        items = self.get_assigned_merchants(sales_rep_id, rep_lat, rep_lon)

        priority_weight = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

        # Sort: SCHEDULED first, then priority (HIGH first), then distance (closest first)
        def sort_key(item: MerchantRouteItem):
            status_order = 0 if item.visit_status == "SCHEDULED" else 1
            p_order = priority_weight.get(item.priority, 1)
            return (status_order, p_order, item.distance_km)

        sorted_items = sorted(items, key=sort_key)

        # Update planned_order numbers in memory
        for idx, item in enumerate(sorted_items, start=1):
            item.planned_order = idx

        return sorted_items

    def get_merchant_brief(
        self, merchant_id: str, rep_lat: float = 26.9150, rep_lon: float = 75.8150
    ) -> Optional[MerchantBriefDetail]:
        """
        Constructs an evidence-backed brief using ONLY authoritative records from DB:
        - Device telemetry
        - KYC documents state
        - Activity metrics / volume trends
        - Settlement status
        Never invents facts or hallucinates briefs.
        """
        m = self.db.query(Merchant).filter(Merchant.id == merchant_id).first()
        if not m:
            return None

        # Check existing visit
        visit = (
            self.db.query(MerchantVisit)
            .filter(MerchantVisit.merchant_id == merchant_id)
            .order_by(MerchantVisit.created_at.desc())
            .first()
        )

        lat = m.latitude or 26.9150
        lon = m.longitude or 75.8150
        distance = calculate_haversine_km(rep_lat, rep_lon, lat, lon)

        # 1. Device Telemetry Check
        device = (
            self.db.query(Device)
            .filter(Device.merchant_id == merchant_id)
            .first()
        )
        device_offline = device is not None and device.status == "OFFLINE"
        low_battery = device is not None and device.battery_level < 25

        # 2. KYC Document Status Check
        docs = (
            self.db.query(MerchantDocument)
            .filter(MerchantDocument.merchant_id == merchant_id)
            .all()
        )
        missing_docs = [d.document_type for d in docs if d.status == "MISSING"]
        blurry_docs = [
            d.document_type
            for d in docs
            if d.ocr_quality_flag == "BLURRY" or d.status == "OCR_FAILED"
        ]
        all_passed = (
            len(docs) >= 3
            and all(d.is_ocr_passed and d.status == "OCR_PASSED" for d in docs)
        )

        # 3. Activity Metric Check
        metric = (
            self.db.query(MerchantActivityMetric)
            .filter(MerchantActivityMetric.merchant_id == merchant_id)
            .first()
        )
        has_volume_drop = metric is not None and metric.drop_percentage >= 40

        # 4. Settlement Discrepancy Check
        disputed_settlement = (
            self.db.query(Settlement)
            .filter(
                Settlement.merchant_id == merchant_id,
                Settlement.status.in_(["DISPUTED", "DISCREPANCY"]),
            )
            .first()
        )

        # Deterministic brief and priority deduction
        priority = "MEDIUM"
        cause_type = "GENERAL_CHECKIN"
        talking_points: List[str] = []
        recommended_pitch = "Inquire about store performance and introduce latest Paytm merchant offerings."

        if device_offline and missing_docs:
            priority = "HIGH"
            cause_type = "HARDWARE_AND_KYC"
            one_line_brief = (
                f"Soundbox offline ({device.battery_level}% battery) & {', '.join(missing_docs)} missing — replace adapter, collect physical cheque."
            )
            talking_points = [
                f"Inspect Soundbox {device.serial_number} power adapter and battery.",
                f"Collect physical copy/photo of {', '.join(missing_docs)} for merchant KYC.",
                "Ensure merchant is informed that onboarding completes once document is approved.",
            ]
            recommended_pitch = "Deliver replacement power cable and assist with bank document collection on the spot."

        elif blurry_docs:
            priority = "HIGH"
            cause_type = "KYC_ISSUE"
            one_line_brief = (
                f"{', '.join(blurry_docs)} photo is blurry — collect physical paper copy for re-verification."
            )
            talking_points = [
                f"Explain that {', '.join(blurry_docs)} photo failed OCR due to low clarity.",
                "Capture a sharp, glare-free photo under good shop lighting.",
                "Submit document directly through field portal for instant authorized verification.",
            ]
            recommended_pitch = "Offer instant physical document scan to unblock settlement payouts."

        elif missing_docs:
            priority = "MEDIUM"
            cause_type = "KYC_MISSING_DOC"
            one_line_brief = (
                f"{', '.join(missing_docs)} is missing — collect physical photo/copy to complete onboarding."
            )
            talking_points = [
                f"Explain that onboarding cannot be approved without {', '.join(missing_docs)}.",
                "Assist merchant with capturing or uploading required proof on the spot.",
                "Explain that Soundbox and daily settlements activate immediately upon document verification.",
            ]
            recommended_pitch = "Help merchant complete final document step to activate Paytm Soundbox and QR."

        elif has_volume_drop:
            priority = "MEDIUM"
            cause_type = "DORMANCY_RETENTION"
            one_line_brief = (
                f"Sales dropped {metric.drop_percentage}% ({metric.diagnosed_cause}) — check competitor presence, pitch Kirana Booster offer."
            )
            talking_points = [
                f"Acknowledge {metric.drop_percentage}% transaction dip over recent scan window.",
                "Present Kirana Booster package: 0% MDR on next 100 transactions.",
                "Check if merchant is using competitor Soundbox or QR code.",
            ]
            recommended_pitch = "Activate Kirana Booster 0% MDR incentive to win back daily checkout volume."

        elif all_passed:
            priority = "LOW"
            cause_type = "PHYSICAL_VERIFICATION"
            one_line_brief = (
                "All KYC docs passed OCR — perform physical store check and signboard confirmation."
            )
            talking_points = [
                "Verify storefront matches shop name in registered application.",
                "Affix official Paytm QR sticker at checkout counter.",
                "Demonstrate Soundbox voice confirmation feature to merchant.",
            ]
            recommended_pitch = "Complete in-person verification to enable immediate daily settlements."

        else:
            priority = "MEDIUM"
            cause_type = "UPSELL_LOAN"
            one_line_brief = (
                "Daily volume healthy and consistent — pitch Merchant Growth Loan and Soundbox upgrade."
            )
            talking_points = [
                "Congratulate merchant on consistent UPI payment volume.",
                "Introduce collateral-free Merchant Growth Loan up to ₹1,00,000.",
                "Offer upgrade to high-volume Soundbox 4G Pro with regional language support.",
            ]
            recommended_pitch = "Propose ₹50,000 merchant inventory loan repaid seamlessly via daily settlement deductions."

        evidence_breakdown = {
            "device": {
                "exists": device is not None,
                "status": device.status if device else None,
                "battery": device.battery_level if device else None,
            },
            "kyc": {
                "onboarding_status": m.onboarding_status,
                "missing_docs": missing_docs,
                "blurry_docs": blurry_docs,
                "all_passed": all_passed,
            },
            "activity": {
                "drop_percentage": metric.drop_percentage if metric else 0,
                "health_status": metric.health_status if metric else "HEALTHY",
            },
            "settlements": {
                "disputed": disputed_settlement is not None,
                "last_discrepancy": disputed_settlement.discrepancy if disputed_settlement else 0,
            },
        }

        return MerchantBriefDetail(
            merchant_id=m.id,
            store_name=m.store_name,
            merchant_name=m.merchant_name,
            phone=m.phone,
            city=m.city,
            latitude=lat,
            longitude=lon,
            distance_km=distance,
            priority=priority,
            one_line_brief=one_line_brief,
            brief_cause_type=cause_type,
            evidence_breakdown=evidence_breakdown,
            talking_points=talking_points,
            recommended_pitch=recommended_pitch,
            visit_id=visit.id if visit else None,
            version=visit.version if visit else 1,
        )

    def extract_voice_note_draft(
        self, visit_id: str, raw_transcript: str, sales_rep_id: str
    ) -> VoiceNoteCandidateDraft:
        """
        Parses raw rep voice note into candidate structured CRM fields.
        CORE INVARIANT: This returns an UNCONFIRMED DRAFT.
        Nothing is written to the persistent CRM visit note until the rep explicitly confirms it.
        """
        visit = self.db.query(MerchantVisit).filter(MerchantVisit.id == visit_id).first()
        if not visit:
            raise ValueError(f"Visit {visit_id} not found")

        # Disallow access to unassigned visits
        if visit.sales_rep_id != sales_rep_id:
            raise RepPolicyViolationError("Access denied: You cannot process notes for another rep's merchant.")

        # Deterministic extraction based on natural language keywords in transcript
        t_lower = raw_transcript.lower()

        # Sentiment
        if any(w in t_lower for w in ["interested", "keen", "proceed", "positive", "agreed", "ready"]):
            sentiment = "POSITIVE"
        elif any(w in t_lower for w in ["refused", "declined", "angry", "not interested", "reject"]):
            sentiment = "NEGATIVE"
        elif any(w in t_lower for w in ["thinking", "discuss with partner", "call next week", "hesitant"]):
            sentiment = "CAUTIOUS"
        else:
            sentiment = "NEUTRAL"

        # Product discussed
        product = "GENERAL_RELATIONSHIP"
        if "loan" in t_lower or "credit" in t_lower or "50,000" in t_lower or "50000" in t_lower:
            product = "MERCHANT_LOAN"
        elif "soundbox" in t_lower or "battery" in t_lower or "speaker" in t_lower:
            product = "SOUNDBOX_HARDWARE"
        elif "pan" in t_lower or "cheque" in t_lower or "doc" in t_lower or "kyc" in t_lower:
            product = "KYC_DOCUMENTATION"
        elif "booster" in t_lower or "mdr" in t_lower or "offer" in t_lower:
            product = "KIRANA_BOOSTER"

        # Lead interest category
        proposed_interest = None
        if sentiment == "POSITIVE":
            if product == "MERCHANT_LOAN":
                proposed_interest = "INTERESTED_MERCHANT_LOAN"
            elif product == "SOUNDBOX_HARDWARE":
                proposed_interest = "INTERESTED_SOUNDBOX_UPGRADE"
            else:
                proposed_interest = "INTERESTED_FOLLOWUP"
        elif sentiment == "NEGATIVE":
            proposed_interest = "NOT_INTERESTED"

        # Structured candidate fields
        extracted = {
            "merchant_sentiment": sentiment,
            "product_discussed": product,
            "proposed_lead_interest": proposed_interest,
            "transcript_summary": raw_transcript.strip(),
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "requires_rep_confirmation": True,
        }

        # Store in visit's temporary candidate fields, but do NOT set is_confirmed_by_rep
        visit.raw_transcript = raw_transcript
        visit.extracted_candidate_fields = json.dumps(extracted)
        self.db.commit()

        return VoiceNoteCandidateDraft(
            visit_id=visit.id,
            merchant_id=visit.merchant_id,
            raw_transcript=raw_transcript,
            extracted_candidate_fields=extracted,
            proposed_lead_interest=proposed_interest,
            requires_rep_confirmation=True,
            version=visit.version,
        )

    def confirm_and_save_visit_note(
        self,
        visit_id: str,
        expected_version: int,
        confirmed_notes: str,
        lead_interest: Optional[str],
        sales_rep_id: str,
    ) -> ConfirmedVisitNoteResult:
        """
        Persists confirmed note to CRM with optimistic concurrency control.
        - Checks expected_version vs actual DB version.
        - Rejects stale writes with ConcurrencyConflictError (HTTP 409).
        - Blocks loan approval / terms commitment (policy violation).
        - Emits CRM_VISIT_NOTE_SAVED audit event.
        """
        visit = self.db.query(MerchantVisit).filter(MerchantVisit.id == visit_id).first()
        if not visit:
            raise ValueError(f"Visit {visit_id} not found")

        # Rep boundary check
        if visit.sales_rep_id != sales_rep_id:
            raise RepPolicyViolationError("Access denied: You cannot confirm notes for another rep's merchant.")

        # Concurrency check (Optimistic Locking)
        if visit.version != expected_version:
            raise ConcurrencyConflictError(
                f"Conflict: Visit was modified by another session (expected version {expected_version}, found {visit.version}). Please refresh."
            )

        # Policy guard: Sales reps cannot auto-approve loans or commit credit terms
        notes_lower = confirmed_notes.lower()
        if "loan approved" in notes_lower or "sanctioned" in notes_lower or "credit guaranteed" in notes_lower:
            raise RepPolicyViolationError(
                "Policy Violation: Sales reps are strictly prohibited from approving loans or guaranteeing financing. Lending terms require risk underwriting."
            )

        # Persist confirmed state
        now = datetime.now(timezone.utc)
        visit.confirmed_notes = confirmed_notes.strip()
        visit.lead_interest = lead_interest
        visit.is_confirmed_by_rep = True
        visit.confirmed_at = now
        visit.visit_status = "COMPLETED"
        visit.version += 1  # Increment version on successful write

        # Update merchant lead status
        m = visit.merchant
        if lead_interest and "INTERESTED" in lead_interest:
            m.lead_status = "INTERESTED"
        elif lead_interest == "NOT_INTERESTED":
            m.lead_status = "NOT_INTERESTED"
        else:
            m.lead_status = "CONTACTED"

        # Emit audit event
        audit_event = AuditEvent(
            tenant_id=visit.tenant_id,
            actor=sales_rep_id,
            action="CRM_VISIT_NOTE_SAVED",
            target=f"merchant_visits:{visit.id}",
            policy_decision_id="dec_sales_rep_confirmed_note",
            idempotency_key=f"idemp_visit_note_{visit.id}_v{visit.version}",
            result="SUCCESS",
            is_synthetic=True,
            environment="DEMO",
            created_at=now,
        )
        self.db.add(audit_event)
        self.db.commit()

        return ConfirmedVisitNoteResult(
            visit_id=visit.id,
            merchant_id=visit.merchant_id,
            is_confirmed=True,
            confirmed_notes=visit.confirmed_notes,
            lead_interest=visit.lead_interest,
            new_version=visit.version,
            audit_event_id=audit_event.id,
            message="Visit note reviewed and confirmed into CRM successfully.",
        )

    def get_manager_rep_summary(self, sales_rep_id: str) -> ManagerRepSummary:
        """
        Manager end-of-day summary reflecting real completed visits and confirmed transcripts.
        """
        rep = self.db.query(Employee).filter(Employee.id == sales_rep_id).first()
        rep_name = rep.name if rep else "Sales Rep"

        visits = (
            self.db.query(MerchantVisit)
            .filter(MerchantVisit.sales_rep_id == sales_rep_id)
            .all()
        )

        total = len(visits)
        completed = [v for v in visits if v.is_confirmed_by_rep and v.visit_status == "COMPLETED"]
        leads = [v for v in completed if v.lead_interest and "INTERESTED" in v.lead_interest]

        completion_rate = int((len(completed) / total * 100)) if total > 0 else 0

        confirmed_list = [
            {
                "visit_id": v.id,
                "merchant_id": v.merchant_id,
                "store_name": v.merchant.store_name,
                "merchant_name": v.merchant.merchant_name,
                "confirmed_notes": v.confirmed_notes,
                "lead_interest": v.lead_interest,
                "confirmed_at": v.confirmed_at.isoformat() if v.confirmed_at else None,
                "version": v.version,
            }
            for v in completed
        ]

        return ManagerRepSummary(
            sales_rep_id=sales_rep_id,
            rep_name=rep_name,
            total_assigned_merchants=total,
            planned_visits_today=total,
            completed_visits_today=len(completed),
            completion_rate_pct=completion_rate,
            leads_generated_today=len(leads),
            confirmed_visits=confirmed_list,
        )
