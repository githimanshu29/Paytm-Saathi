from typing import List, Optional, Protocol
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db.models import MerchantActivityMetric, MerchantFollowup, Merchant


class MerchantMetricsRecord(BaseModel):
    id: str
    merchant_id: str
    store_name: str
    city: str
    baseline_daily_tx_count: int
    baseline_daily_volume_paise: int
    baseline_daily_volume_inr: str
    recent_daily_tx_count: int
    recent_daily_volume_paise: int
    recent_daily_volume_inr: str
    drop_percentage: int
    health_status: str  # HEALTHY | AT_RISK | DORMANT
    diagnosed_cause: Optional[str] = None  # DEVICE_ISSUE | SETTLEMENT_ISSUE | COMPETITOR_OR_DISENGAGEMENT
    revival_stage: str  # AT_RISK | FOLLOWUP_SENT | WARM_LEAD | REVIVED
    last_scanned_at: str
    recovered_at: Optional[str] = None


class MerchantFollowupRecord(BaseModel):
    id: str
    merchant_id: str
    store_name: Optional[str] = None
    cause_type: str  # DEVICE_ISSUE | SETTLEMENT_ISSUE | COMPETITOR_OR_DISENGAGEMENT
    message_title: str
    message_body: str
    offer_code: Optional[str] = None
    offer_details: Optional[str] = None
    status: str  # PENDING | DELIVERED | ACCEPTED | DISMISSED | REVIVED
    handed_off_to: Optional[str] = None  # FIX | RECONCILE | FIELDMATE_SALES_REP
    task_id: Optional[str] = None
    delivered_at: str
    responded_at: Optional[str] = None
    merchant_response: Optional[str] = None


class IReviveAdapter(Protocol):
    def get_merchant_metrics(self, merchant_id: str) -> Optional[MerchantMetricsRecord]:
        ...

    def list_at_risk_merchants(self, threshold_drop_percentage: int = 40) -> List[MerchantMetricsRecord]:
        ...

    def get_active_followup(self, merchant_id: str) -> Optional[MerchantFollowupRecord]:
        ...

    def create_followup(
        self,
        merchant_id: str,
        cause_type: str,
        message_title: str,
        message_body: str,
        offer_code: Optional[str] = None,
        offer_details: Optional[str] = None,
        handed_off_to: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> MerchantFollowupRecord:
        ...

    def respond_to_followup(self, followup_id: str, decision: str) -> Optional[MerchantFollowupRecord]:
        ...

    def record_merchant_recovery(
        self,
        merchant_id: str,
        new_daily_volume_paise: int,
        new_daily_tx_count: int,
    ) -> Optional[MerchantMetricsRecord]:
        ...


class MockReviveAdapter:
    """
    Adapter implementation reading real seeded rows from merchant_activity_metrics
    and merchant_followups, calculating deterministic period comparisons.
    """

    def __init__(self, db: Session):
        self.db = db

    def _to_record(self, metric: MerchantActivityMetric, merchant: Optional[Merchant] = None) -> MerchantMetricsRecord:
        store = merchant.store_name if merchant else (metric.merchant.store_name if metric.merchant else "Kirana Store")
        city = merchant.city if merchant else (metric.merchant.city if metric.merchant else "Jaipur")
        return MerchantMetricsRecord(
            id=metric.id,
            merchant_id=metric.merchant_id,
            store_name=store,
            city=city,
            baseline_daily_tx_count=metric.baseline_daily_tx_count,
            baseline_daily_volume_paise=metric.baseline_daily_volume_paise,
            baseline_daily_volume_inr=f"₹{metric.baseline_daily_volume_paise / 100:,.2f}",
            recent_daily_tx_count=metric.recent_daily_tx_count,
            recent_daily_volume_paise=metric.recent_daily_volume_paise,
            recent_daily_volume_inr=f"₹{metric.recent_daily_volume_paise / 100:,.2f}",
            drop_percentage=metric.drop_percentage,
            health_status=metric.health_status,
            diagnosed_cause=metric.diagnosed_cause,
            revival_stage=metric.revival_stage,
            last_scanned_at=metric.last_scanned_at.strftime("%Y-%m-%d %H:%M:%S") if metric.last_scanned_at else "Today",
            recovered_at=metric.recovered_at.strftime("%Y-%m-%d %H:%M:%S") if metric.recovered_at else None,
        )

    def _to_followup_record(self, fol: MerchantFollowup) -> MerchantFollowupRecord:
        store = fol.merchant.store_name if fol.merchant else "Kirana Store"
        return MerchantFollowupRecord(
            id=fol.id,
            merchant_id=fol.merchant_id,
            store_name=store,
            cause_type=fol.cause_type,
            message_title=fol.message_title,
            message_body=fol.message_body,
            offer_code=fol.offer_code,
            offer_details=fol.offer_details,
            status=fol.status,
            handed_off_to=fol.handed_off_to,
            task_id=fol.task_id,
            delivered_at=fol.delivered_at.strftime("%Y-%m-%d %H:%M:%S") if fol.delivered_at else "Today",
            responded_at=fol.responded_at.strftime("%Y-%m-%d %H:%M:%S") if fol.responded_at else None,
            merchant_response=fol.merchant_response,
        )

    def get_merchant_metrics(self, merchant_id: str) -> Optional[MerchantMetricsRecord]:
        metric = self.db.query(MerchantActivityMetric).filter_by(merchant_id=merchant_id).first()
        if not metric:
            return None
        return self._to_record(metric)

    def list_at_risk_merchants(self, threshold_drop_percentage: int = 40) -> List[MerchantMetricsRecord]:
        metrics = (
            self.db.query(MerchantActivityMetric)
            .join(Merchant, MerchantActivityMetric.merchant_id == Merchant.id)
            .filter(MerchantActivityMetric.drop_percentage >= threshold_drop_percentage)
            .order_by(MerchantActivityMetric.drop_percentage.desc())
            .all()
        )
        return [self._to_record(m) for m in metrics]

    def get_active_followup(self, merchant_id: str) -> Optional[MerchantFollowupRecord]:
        fol = (
            self.db.query(MerchantFollowup)
            .filter(
                (MerchantFollowup.merchant_id == merchant_id)
                & (MerchantFollowup.status.in_(["DELIVERED", "ACCEPTED", "PENDING"]))
            )
            .order_by(MerchantFollowup.delivered_at.desc())
            .first()
        )
        if not fol:
            return None
        return self._to_followup_record(fol)

    def create_followup(
        self,
        merchant_id: str,
        cause_type: str,
        message_title: str,
        message_body: str,
        offer_code: Optional[str] = None,
        offer_details: Optional[str] = None,
        handed_off_to: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> MerchantFollowupRecord:
        merchant = self.db.query(Merchant).filter_by(id=merchant_id).first()
        tenant_id = merchant.tenant_id if merchant else "tenant_paytm_demo"

        fol = MerchantFollowup(
            tenant_id=tenant_id,
            merchant_id=merchant_id,
            cause_type=cause_type,
            message_title=message_title,
            message_body=message_body,
            offer_code=offer_code,
            offer_details=offer_details,
            status="DELIVERED",
            handed_off_to=handed_off_to,
            task_id=task_id,
            delivered_at=datetime.now(timezone.utc),
            is_synthetic=True,
            environment="DEMO",
        )
        self.db.add(fol)

        # Update metric stage
        metric = self.db.query(MerchantActivityMetric).filter_by(merchant_id=merchant_id).first()
        if metric:
            metric.revival_stage = "FOLLOWUP_SENT"
            metric.diagnosed_cause = cause_type
            metric.last_scanned_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(fol)
        return self._to_followup_record(fol)

    def respond_to_followup(self, followup_id: str, decision: str) -> Optional[MerchantFollowupRecord]:
        fol = self.db.query(MerchantFollowup).filter_by(id=followup_id).first()
        if not fol:
            return None

        decision_upper = decision.upper()
        fol.status = "ACCEPTED" if decision_upper == "ACCEPT" else "DISMISSED"
        fol.merchant_response = fol.status
        fol.responded_at = datetime.now(timezone.utc)

        metric = self.db.query(MerchantActivityMetric).filter_by(merchant_id=fol.merchant_id).first()
        if metric and fol.status == "ACCEPTED":
            metric.revival_stage = "WARM_LEAD"

        self.db.commit()
        self.db.refresh(fol)
        return self._to_followup_record(fol)

    def record_merchant_recovery(
        self,
        merchant_id: str,
        new_daily_volume_paise: int,
        new_daily_tx_count: int,
    ) -> Optional[MerchantMetricsRecord]:
        metric = self.db.query(MerchantActivityMetric).filter_by(merchant_id=merchant_id).first()
        if not metric:
            return None

        metric.recent_daily_volume_paise = new_daily_volume_paise
        metric.recent_daily_tx_count = new_daily_tx_count

        # Code-based deterministic decline calculation
        if metric.baseline_daily_volume_paise > 0:
            diff = metric.baseline_daily_volume_paise - new_daily_volume_paise
            if diff <= 0:
                metric.drop_percentage = 0
            else:
                metric.drop_percentage = int((diff / metric.baseline_daily_volume_paise) * 100)

        # Invariant: Only mark REVIVED if fresh volume is >= 80% of baseline!
        if metric.recent_daily_volume_paise >= int(metric.baseline_daily_volume_paise * 0.8):
            metric.health_status = "HEALTHY"
            metric.revival_stage = "REVIVED"
            metric.recovered_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(metric)
        return self._to_record(metric)
