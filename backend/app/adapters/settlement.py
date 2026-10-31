from datetime import datetime, timezone
from typing import List, Optional, Protocol, runtime_checkable
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.models import Settlement, Transaction, TransactionFee, Chargeback


class FeeLineItem(BaseModel):
    id: str
    fee_type: str
    amount: int  # minor units (paise)
    amount_inr: str
    description: Optional[str] = None


class ChargebackLineItem(BaseModel):
    id: str
    amount: int  # minor units (paise)
    amount_inr: str
    reason: str
    dispute_ref: Optional[str] = None
    evidence_notes: Optional[str] = None


class TransactionLineItem(BaseModel):
    id: str
    amount: int  # minor units (paise)
    amount_inr: str
    status: str
    customer_name: Optional[str] = None
    utr: Optional[str] = None


class SettlementRecord(BaseModel):
    id: str
    merchant_id: str
    settlement_date: str  # YYYY-MM-DD
    gross_sales: int  # minor units (paise)
    refunds: int
    fees: int
    chargebacks: int
    net_expected: int
    net_settled: int
    discrepancy: int
    status: str  # RECONCILED | DISCREPANCY | DISPUTED
    bank_utr: Optional[str] = None
    nodal_account: Optional[str] = "ICICI_NODAL_0192"
    dispute_case_id: Optional[str] = None
    evidence_attached: Optional[str] = None

    @property
    def gross_sales_inr(self) -> str:
        return f"₹{self.gross_sales / 100:,.2f}"

    @property
    def refunds_inr(self) -> str:
        return f"₹{self.refunds / 100:,.2f}"

    @property
    def fees_inr(self) -> str:
        return f"₹{self.fees / 100:,.2f}"

    @property
    def chargebacks_inr(self) -> str:
        return f"₹{self.chargebacks / 100:,.2f}"

    @property
    def net_expected_inr(self) -> str:
        return f"₹{self.net_expected / 100:,.2f}"

    @property
    def net_settled_inr(self) -> str:
        return f"₹{self.net_settled / 100:,.2f}"

    @property
    def discrepancy_inr(self) -> str:
        return f"₹{abs(self.discrepancy) / 100:,.2f}"


class SettlementLineItemsRecord(BaseModel):
    settlement_date: str
    merchant_id: str
    sales_transactions: List[TransactionLineItem]
    refund_transactions: List[TransactionLineItem]
    fee_items: List[FeeLineItem]
    chargeback_items: List[ChargebackLineItem]
    total_sales_paise: int
    total_refunds_paise: int
    total_fees_paise: int
    total_chargebacks_paise: int


@runtime_checkable
class ISettlementAdapter(Protocol):
    """
    Authoritative boundary for settlement ledger and nodal bank payout data.
    """

    def get_settlement(self, merchant_id: str, settlement_date: str) -> Optional[SettlementRecord]:
        ...

    def get_settlement_line_items(self, merchant_id: str, settlement_date: str) -> SettlementLineItemsRecord:
        ...

    def list_settlements(self, merchant_id: str, limit: int = 10) -> List[SettlementRecord]:
        ...

    def attach_dispute_case(self, settlement_id: str, case_id: str, evidence: str) -> bool:
        ...


class MockSettlementAdapter:
    """
    Authoritative Database-backed implementation of ISettlementAdapter.
    Swappable for real ICICI / HDFC / Axis nodal settlement APIs in production.
    """

    def __init__(self, db: Session):
        self.db = db

    def _to_record(self, s: Settlement) -> SettlementRecord:
        return SettlementRecord(
            id=s.id,
            merchant_id=s.merchant_id,
            settlement_date=s.settlement_date,
            gross_sales=s.gross_sales,
            refunds=s.refunds,
            fees=s.fees,
            chargebacks=s.chargebacks,
            net_expected=s.net_expected,
            net_settled=s.net_settled,
            discrepancy=s.discrepancy,
            status=s.status,
            bank_utr=s.bank_utr,
            nodal_account=s.nodal_account,
            dispute_case_id=s.dispute_case_id,
            evidence_attached=s.evidence_attached,
        )

    def get_settlement(self, merchant_id: str, settlement_date: str) -> Optional[SettlementRecord]:
        s = (
            self.db.query(Settlement)
            .filter(
                (Settlement.merchant_id == merchant_id)
                & (Settlement.settlement_date == settlement_date)
            )
            .first()
        )
        return self._to_record(s) if s else None

    def get_settlement_line_items(self, merchant_id: str, settlement_date: str) -> SettlementLineItemsRecord:
        # 1. Fees
        fees = (
            self.db.query(TransactionFee)
            .filter(
                (TransactionFee.merchant_id == merchant_id)
                & (TransactionFee.settlement_date == settlement_date)
            )
            .all()
        )
        fee_items = [
            FeeLineItem(
                id=f.id,
                fee_type=f.fee_type,
                amount=f.amount,
                amount_inr=f"₹{f.amount / 100:,.2f}",
                description=f.description,
            )
            for f in fees
        ]
        total_fees = sum(f.amount for f in fees)

        # 2. Chargebacks
        cbs = (
            self.db.query(Chargeback)
            .filter(
                (Chargeback.merchant_id == merchant_id)
                & (Chargeback.settlement_date == settlement_date)
            )
            .all()
        )
        chargeback_items = [
            ChargebackLineItem(
                id=c.id,
                amount=c.amount,
                amount_inr=f"₹{c.amount / 100:,.2f}",
                reason=c.reason,
                dispute_ref=c.dispute_ref,
                evidence_notes=c.evidence_notes,
            )
            for c in cbs
        ]
        total_cbs = sum(c.amount for c in cbs)

        # 3. Transactions on that settlement date
        # Check by settlement_date or date prefix
        txns = (
            self.db.query(Transaction)
            .filter(Transaction.merchant_id == merchant_id)
            .all()
        )
        # Filter matching date
        matching_txns = [
            t for t in txns
            if t.created_at and t.created_at.strftime("%Y-%m-%d") == settlement_date
        ]

        sales = []
        refunds = []
        total_sales = 0
        total_refunds = 0

        for t in matching_txns:
            item = TransactionLineItem(
                id=t.id,
                amount=t.amount,
                amount_inr=f"₹{t.amount / 100:,.2f}",
                status=t.status,
                customer_name=t.customer_name,
                utr=t.utr_or_ref,
            )
            if t.status == "SUCCESS":
                sales.append(item)
                total_sales += t.amount
            elif t.status in ["REVERSED", "REFUNDED", "FAILED"]:
                refunds.append(item)
                total_refunds += t.amount

        # Fallback to settlement summary numbers if transactions table doesn't have individual rows
        settlement = self.get_settlement(merchant_id, settlement_date)
        if settlement:
            if total_sales == 0 and settlement.gross_sales > 0:
                total_sales = settlement.gross_sales
                sales.append(
                    TransactionLineItem(
                        id=f"agg_sales_{settlement_date}",
                        amount=settlement.gross_sales,
                        amount_inr=settlement.gross_sales_inr,
                        status="SUCCESS",
                        customer_name="Aggregate Daily UPI Sales",
                        utr=settlement.bank_utr or f"AGG_UPI_{settlement_date}",
                    )
                )
            if total_refunds == 0 and settlement.refunds > 0:
                total_refunds = settlement.refunds
                refunds.append(
                    TransactionLineItem(
                        id=f"agg_refund_{settlement_date}",
                        amount=settlement.refunds,
                        amount_inr=settlement.refunds_inr,
                        status="REVERSED",
                        customer_name="Auto-Reversal Batch",
                        utr=f"REF_BATCH_{settlement_date}",
                    )
                )
            if total_fees == 0 and settlement.fees > 0:
                total_fees = settlement.fees
                fee_items.append(
                    FeeLineItem(
                        id=f"agg_fee_{settlement_date}",
                        fee_type="MDR_RENTAL",
                        amount=settlement.fees,
                        amount_inr=settlement.fees_inr,
                        description="MDR processing and device monthly rental",
                    )
                )
            if total_cbs == 0 and settlement.chargebacks > 0:
                total_cbs = settlement.chargebacks
                chargeback_items.append(
                    ChargebackLineItem(
                        id=f"agg_cb_{settlement_date}",
                        amount=settlement.chargebacks,
                        amount_inr=settlement.chargebacks_inr,
                        reason="CUSTOMER_DISPUTE",
                        dispute_ref=f"CB_NODAL_{settlement_date}",
                        evidence_notes="Bank chargeback deduction",
                    )
                )

        return SettlementLineItemsRecord(
            settlement_date=settlement_date,
            merchant_id=merchant_id,
            sales_transactions=sales,
            refund_transactions=refunds,
            fee_items=fee_items,
            chargeback_items=chargeback_items,
            total_sales_paise=total_sales,
            total_refunds_paise=total_refunds,
            total_fees_paise=total_fees,
            total_chargebacks_paise=total_cbs,
        )

    def list_settlements(self, merchant_id: str, limit: int = 10) -> List[SettlementRecord]:
        rows = (
            self.db.query(Settlement)
            .filter_by(merchant_id=merchant_id)
            .order_by(Settlement.settlement_date.desc())
            .limit(limit)
            .all()
        )
        return [self._to_record(s) for s in rows]

    def attach_dispute_case(self, settlement_id: str, case_id: str, evidence: str) -> bool:
        s = self.db.query(Settlement).filter_by(id=settlement_id).first()
        if not s:
            return False
        s.dispute_case_id = case_id
        s.status = "DISPUTED"
        s.evidence_attached = evidence
        s.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return True
