from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from app.db.models import Transaction

@dataclass
class TransactionRecord:
    id: str
    merchant_id: str
    amount: int  # in paise
    status: str  # SUCCESS, FAILED, PENDING, REVERSED
    currency: str
    payment_rail: str
    utr_or_ref: Optional[str]
    customer_name: Optional[str]
    payer_vpa: Optional[str]
    bank_response_code: Optional[str]
    reversal_status: Optional[str]
    created_at: datetime
    is_synthetic: bool = True
    environment: str = "DEMO"

@dataclass
class PaymentEventRecord:
    event_id: str
    transaction_id: str
    event_type: str
    description: str
    timestamp: datetime
    source: str = "NPCI_SWITCH_SIMULATOR"

class ITransactionAdapter(ABC):
    """
    Typed adapter interface for payment gateway & switch lookups.
    Enables swapping simulated mock adapters for real banking/Paytm APIs seamlessly.
    """

    @abstractmethod
    def get_transaction(self, tx_id: str) -> Optional[TransactionRecord]:
        pass

    @abstractmethod
    def get_transaction_by_ref(self, ref_or_utr: str) -> Optional[TransactionRecord]:
        pass

    @abstractmethod
    def get_related_payment_events(self, tx_id: str) -> List[PaymentEventRecord]:
        pass

    @abstractmethod
    def get_merchant_recent_transactions(
        self, merchant_id: str, limit: int = 10
    ) -> List[TransactionRecord]:
        pass

class MockTransactionAdapter(ITransactionAdapter):
    """
    Authoritative database-backed mock adapter for payment lookups.
    """

    def __init__(self, db: Session):
        self.db = db

    def _to_record(self, tx: Transaction) -> TransactionRecord:
        return TransactionRecord(
            id=tx.id,
            merchant_id=tx.merchant_id,
            amount=tx.amount,
            status=tx.status,
            currency=tx.currency,
            payment_rail=tx.payment_rail,
            utr_or_ref=tx.utr_or_ref,
            customer_name=tx.customer_name,
            payer_vpa=tx.payer_vpa,
            bank_response_code=tx.bank_response_code,
            reversal_status=tx.reversal_status,
            created_at=tx.created_at,
            is_synthetic=tx.is_synthetic,
            environment=tx.environment,
        )

    def get_transaction(self, tx_id: str) -> Optional[TransactionRecord]:
        tx = self.db.query(Transaction).filter_by(id=tx_id).first()
        return self._to_record(tx) if tx else None

    def get_transaction_by_ref(self, ref_or_utr: str) -> Optional[TransactionRecord]:
        clean_ref = ref_or_utr.strip()
        tx = self.db.query(Transaction).filter(
            (Transaction.utr_or_ref == clean_ref) |
            (Transaction.id == clean_ref)
        ).first()
        return self._to_record(tx) if tx else None

    def get_merchant_recent_transactions(
        self, merchant_id: str, limit: int = 10
    ) -> List[TransactionRecord]:
        txs = (
            self.db.query(Transaction)
            .filter_by(merchant_id=merchant_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_record(tx) for tx in txs]

    def get_related_payment_events(self, tx_id: str) -> List[PaymentEventRecord]:
        tx = self.get_transaction(tx_id)
        if not tx:
            return []

        events: List[PaymentEventRecord] = []
        base_time = tx.created_at

        # Event 1: Initiation
        events.append(
            PaymentEventRecord(
                event_id=f"evt_{tx.id}_01",
                transaction_id=tx.id,
                event_type="UPI_INTENT_RECEIVED",
                description=f"Incoming UPI debit request from {tx.payer_vpa or 'payer'} for {tx.amount / 100} INR",
                timestamp=base_time,
            )
        )

        # Event 2 based on bank response code
        if tx.bank_response_code == "00_SUCCESS":
            events.append(
                PaymentEventRecord(
                    event_id=f"evt_{tx.id}_02",
                    transaction_id=tx.id,
                    event_type="CREDIT_CONFIRMED",
                    description=f"Beneficiary nodal bank confirmed credit with UTR {tx.utr_or_ref}",
                    timestamp=base_time + timedelta(seconds=2),
                )
            )
        elif tx.bank_response_code == "U30_AUTO_REVERSAL":
            events.append(
                PaymentEventRecord(
                    event_id=f"evt_{tx.id}_02",
                    transaction_id=tx.id,
                    event_type="SWITCH_DEBIT_TIMEOUT",
                    description="Remitter bank debited but merchant PSP timed out. Auto-reversal scheduled by NPCI switch.",
                    timestamp=base_time + timedelta(seconds=15),
                )
            )
            events.append(
                PaymentEventRecord(
                    event_id=f"evt_{tx.id}_03",
                    transaction_id=tx.id,
                    event_type="AUTO_REVERSAL_IN_PROGRESS",
                    description="NPCI clearing cycle batch generated. Expected reversal window: 24 to 48 banking hours.",
                    timestamp=base_time + timedelta(minutes=5),
                )
            )
        elif tx.bank_response_code == "U69_REVERSAL_STUCK":
            events.append(
                PaymentEventRecord(
                    event_id=f"evt_{tx.id}_02",
                    transaction_id=tx.id,
                    event_type="REVERSAL_TIMEOUT_EXCEEDED",
                    description="Auto-reversal cycle failed remitter bank acknowledgement. SLA 48h exceeded. Manual refund review required.",
                    timestamp=base_time + timedelta(hours=48),
                )
            )
        elif tx.bank_response_code == "ZA_SECURITY_HOLD":
            events.append(
                PaymentEventRecord(
                    event_id=f"evt_{tx.id}_02",
                    transaction_id=tx.id,
                    event_type="SUSPECTED_TAMPERING_FLAG",
                    description="Multiple contradictory claims with mismatching terminal identifiers. Blocked by automated risk heuristics.",
                    timestamp=base_time + timedelta(seconds=4),
                )
            )

        return events
