from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Merchant, Device, Transaction, Receivable, Customer
from app.api.auth import get_current_user
from app.policy.audit import audit_log
from app.schemas.merchant import (
    MerchantSummaryResponse,
    DeviceSummary,
    PaymentSummary,
    TransactionItem,
    DuesSummary,
    ReceivableItem,
    ChatMessageRequest,
    ChatMessageResponse,
)

merchant_router = APIRouter(prefix="/merchant", tags=["Merchant Operations"])

def format_paise_to_inr(paise: int) -> str:
    return f"₹{paise / 100:,.2f}"

def map_device_status_to_chip(status_str: str) -> str:
    status_upper = status_str.upper()
    if status_upper == "ONLINE":
        return "verified"
    elif status_upper == "ERROR":
        return "needs_human"
    elif status_upper == "OFFLINE":
        return "awaiting_approval"
    return "pending"

def map_tx_status_to_chip(status_str: str) -> str:
    status_upper = status_str.upper()
    if status_upper == "SUCCESS":
        return "verified"
    elif status_upper in ("FAILED", "DISPUTED"):
        return "needs_human"
    elif status_upper == "PENDING":
        return "pending"
    return "executed"

def map_receivable_status_to_chip(status_str: str) -> str:
    status_upper = status_str.upper()
    if status_upper == "PAID":
        return "verified"
    elif status_upper == "OVERDUE":
        return "needs_human"
    elif status_upper == "PENDING":
        return "awaiting_approval"
    return "pending"

@merchant_router.get("/me/summary", response_model=MerchantSummaryResponse)
def get_merchant_summary(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    merchant_id = user.get("sub")
    user_type = user.get("user_type")

    # If employee inspects, fallback to merchant_id if passed or primary merchant
    merchant = db.query(Merchant).filter_by(id=merchant_id).first()
    if not merchant:
        # Fallback to first seeded merchant for demo stability
        merchant = db.query(Merchant).first()
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Merchant account not found. Please seed demo data.",
            )

    # 1. Device Summary
    device_row = db.query(Device).filter_by(merchant_id=merchant.id).first()
    device_summary: Optional[DeviceSummary] = None
    if device_row:
        device_summary = DeviceSummary(
            device_type=device_row.device_type,
            serial_number=device_row.serial_number,
            battery_level=device_row.battery_level,
            status=device_row.status,
            chip_status=map_device_status_to_chip(device_row.status),
        )

    # 2. Payments & Transactions Summary
    transactions = (
        db.query(Transaction)
        .filter_by(merchant_id=merchant.id)
        .order_by(Transaction.created_at.desc())
        .limit(10)
        .all()
    )

    today_success_paise = sum(
        tx.amount for tx in transactions if tx.status.upper() == "SUCCESS"
    )
    today_count = sum(1 for tx in transactions if tx.status.upper() == "SUCCESS")

    tx_items = [
        TransactionItem(
            id=tx.id,
            amount=tx.amount,
            amount_formatted=format_paise_to_inr(tx.amount),
            customer_name=tx.customer_name or "UPI Customer",
            status=tx.status,
            payment_rail=tx.payment_rail,
            created_at=tx.created_at.strftime("%I:%M %p") if tx.created_at else "Today",
        )
        for tx in transactions
    ]

    payments_summary = PaymentSummary(
        today_total_paise=today_success_paise,
        today_total_formatted=format_paise_to_inr(today_success_paise),
        today_count=today_count,
        chip_status="verified" if today_count > 0 else "pending",
        recent_transactions=tx_items,
    )

    # 3. Dues & Receivables Summary
    receivables = (
        db.query(Receivable, Customer)
        .join(Customer, Receivable.customer_id == Customer.id)
        .filter(Receivable.merchant_id == merchant.id)
        .order_by(Receivable.created_at.desc())
        .all()
    )

    total_dues_paise = sum(
        rec.amount for rec, _ in receivables if rec.status.upper() != "PAID"
    )
    pending_dues_count = sum(
        1 for rec, _ in receivables if rec.status.upper() != "PAID"
    )

    rec_items = [
        ReceivableItem(
            id=rec.id,
            customer_name=cust.name,
            amount=rec.amount,
            amount_formatted=format_paise_to_inr(rec.amount),
            due_date=rec.due_date.strftime("%d %b") if rec.due_date else "Flexible",
            status=rec.status,
        )
        for rec, cust in receivables
    ]

    dues_summary = DuesSummary(
        total_dues_paise=total_dues_paise,
        total_dues_formatted=format_paise_to_inr(total_dues_paise),
        pending_count=pending_dues_count,
        chip_status="awaiting_approval" if pending_dues_count > 0 else "verified",
        receivables=rec_items,
    )

    return MerchantSummaryResponse(
        merchant_id=merchant.id,
        store_name=merchant.store_name,
        merchant_name=merchant.merchant_name,
        phone=merchant.phone,
        city=merchant.city,
        status=merchant.status,
        kyc_status=merchant.kyc_status,
        device=device_summary,
        payments=payments_summary,
        dues=dues_summary,
    )

@merchant_router.post("/chat/message", response_model=ChatMessageResponse)
def send_chat_message(
    req: ChatMessageRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    merchant_id = user.get("sub", "mer_demo")
    store_name = user.get("store_name", "Sharma Kirana")

    # Record message in audit trail
    audit_log(
        db=db,
        actor=merchant_id,
        action="MERCHANT_CHAT_MESSAGE_RECEIVED",
        target="saathi_brain_orchestrator",
        result="RECEIVED",
        policy_decision_id="dec_chat_phase2_canned",
    )

    # Canned clearly-labeled prototype reply confirming end-to-end wiring
    reply_text = (
        f"[Saathi Prototype · Phase 2] Namaste {store_name}! "
        f"I received your message: \"{req.message}\". "
        f"Multi-agent autonomous coordination will activate in the next phases. "
        f"For now, your Soundbox and settlements are active and monitored!"
    )

    return ChatMessageResponse(
        reply=reply_text,
        sender="saathi",
        timestamp=datetime.now(timezone.utc).strftime("%I:%M %p"),
        is_synthetic=True,
    )
