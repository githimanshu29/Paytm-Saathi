from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import (
    Merchant,
    Device,
    Transaction,
    Receivable,
    Customer,
    Task,
    TaskBucket,
    ActionApproval,
    ApprovalDecision,
)
from app.api.auth import get_current_user
from app.policy.audit import audit_log
from app.agents.orchestrator import SaathiBrainOrchestrator
from app.adapters.device import MockDeviceAdapter
from app.adapters.speech import get_speech_adapter
from app.schemas.merchant import (
    MerchantSummaryResponse,
    DeviceSummary,
    PaymentSummary,
    TransactionItem,
    DuesSummary,
    ReceivableItem,
    ChatMessageRequest,
    ChatMessageResponse,
    VoiceChatRequest,
    ApprovalCardData,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    DeviceToggleResponse,
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
        hb_str = device_row.last_heartbeat.strftime("%I:%M %p") if device_row.last_heartbeat else "Just now"
        device_summary = DeviceSummary(
            device_type=device_row.device_type,
            serial_number=device_row.serial_number,
            battery_level=device_row.battery_level,
            status=device_row.status,
            chip_status=map_device_status_to_chip(device_row.status),
            last_heartbeat=hb_str,
            signal_strength_dbm=device_row.signal_strength_dbm or -70,
            technician_visit_booked=device_row.technician_visit_booked,
            technician_slot=device_row.technician_slot,
        )

    # 2. Payments & Transactions Summary (filter today's real-time checkout sales)
    transactions = (
        db.query(Transaction)
        .filter_by(merchant_id=merchant.id)
        .order_by(Transaction.created_at.desc())
        .limit(10)
        .all()
    )

    today_date = datetime.utcnow().date()
    today_success_txs = [
        tx for tx in transactions
        if tx.status.upper() == "SUCCESS"
        and not tx.id.startswith("tx_set_")
        and (not tx.created_at or tx.created_at.date() == today_date)
    ]
    today_success_paise = sum(tx.amount for tx in today_success_txs)
    today_count = len(today_success_txs)

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
        rec.amount - rec.paid_amount for rec, _ in receivables if rec.status.upper() != "PAID"
    )
    total_recovered_paise = sum(
        rec.paid_amount for rec, _ in receivables
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
        total_recovered_paise=total_recovered_paise,
        total_recovered_formatted=format_paise_to_inr(total_recovered_paise),
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
        onboarding_status=merchant.onboarding_status or "COMPLETED",
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
    merchant_id = user.get("sub", "mer_sharma_kirana")
    
    # Audit incoming message
    audit_log(
        db=db,
        actor=merchant_id,
        action="MERCHANT_CHAT_MESSAGE_RECEIVED",
        target="saathi_brain_orchestrator",
        result="RECEIVED",
        policy_decision_id="dec_chat_orchestrator_route",
    )

    # Route via SaathiBrainOrchestrator to Resolve or Fix
    merchant = db.query(Merchant).filter_by(id=merchant_id).first()
    city = merchant.city if merchant else "Jaipur"

    history_list = [h.model_dump() for h in (req.history or [])]
    orchestrator = SaathiBrainOrchestrator(db)
    result = orchestrator.route_and_run(
        merchant_id=merchant_id,
        query_text=req.message,
        city=city,
        actor_id=merchant_id,
        history=history_list,
    )

    approval_card_data = None
    vasooli_card_data = result.get("vasooli_card")
    if result.get("agent") == "VASOOLI" and not vasooli_card_data:
        vasooli_card_data = result.get("approval_card")

    if result.get("approval_card") and result.get("agent") != "VASOOLI":
        approval_card_data = ApprovalCardData(**result["approval_card"])

    return ChatMessageResponse(
        reply=result["reply"],
        sender="saathi",
        timestamp=datetime.now(timezone.utc).strftime("%I:%M %p"),
        agent=result.get("agent", "ORCHESTRATOR"),
        branch=result.get("branch"),
        step=result.get("step"),
        chip_status=result.get("chip_status"),
        explanation_en=result.get("explanation_en"),
        explanation_hi=result.get("explanation_hi"),
        tx_ref=result.get("tx_ref"),
        case_id=result.get("case_id"),
        technician_booked=result.get("technician_booked", False),
        technician_slot=result.get("technician_slot"),
        action_card=result.get("action_card"),
        breakdown_card=result.get("breakdown_card"),
        checkin_card=result.get("checkin_card"),
        missing_item_card=result.get("missing_item_card"),
        vasooli_card=vasooli_card_data,
        checklist=result.get("checklist"),
        verification_result=result.get("verification_result"),
        settlement_date=result.get("settlement_date"),
        approval_card=approval_card_data,
        speech_audio_base64=result.get("speech_audio_base64"),
        speech_duration_seconds=result.get("speech_duration_seconds"),
        is_synthetic=True,
    )

@merchant_router.post("/voice/chat", response_model=ChatMessageResponse)
def send_voice_chat(
    req: VoiceChatRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    merchant_id = user.get("sub", "mer_sharma_kirana")
    speech_adapter = get_speech_adapter()

    # Transcribe speech
    transcript = req.transcript
    if not transcript and req.audio_base64:
        import base64
        try:
            raw_audio = base64.b64decode(req.audio_base64)
            tr_res = speech_adapter.transcribe(raw_audio, language_hint=req.language)
            transcript = tr_res.text
        except Exception:
            transcript = "Soundbox not working"

    if not transcript:
        transcript = "Soundbox light is red and silent"

    merchant = db.query(Merchant).filter_by(id=merchant_id).first()
    city = merchant.city if merchant else "Jaipur"

    orchestrator = SaathiBrainOrchestrator(db)
    result = orchestrator.route_and_run(
        merchant_id=merchant_id,
        query_text=transcript,
        city=city,
        actor_id=merchant_id,
    )

    approval_card_data = None
    vasooli_card_data = result.get("vasooli_card")
    if result.get("agent") == "VASOOLI" and not vasooli_card_data:
        vasooli_card_data = result.get("approval_card")

    if result.get("approval_card") and result.get("agent") != "VASOOLI":
        approval_card_data = ApprovalCardData(**result["approval_card"])

    return ChatMessageResponse(
        reply=result["reply"],
        sender="saathi",
        timestamp=datetime.now(timezone.utc).strftime("%I:%M %p"),
        agent=result.get("agent", "ORCHESTRATOR"),
        branch=result.get("branch"),
        step=result.get("step"),
        chip_status=result.get("chip_status"),
        explanation_en=result.get("explanation_en"),
        explanation_hi=result.get("explanation_hi"),
        tx_ref=result.get("tx_ref"),
        case_id=result.get("case_id"),
        technician_booked=result.get("technician_booked", False),
        technician_slot=result.get("technician_slot"),
        action_card=result.get("action_card"),
        breakdown_card=result.get("breakdown_card"),
        checkin_card=result.get("checkin_card"),
        missing_item_card=result.get("missing_item_card"),
        vasooli_card=vasooli_card_data,
        checklist=result.get("checklist"),
        verification_result=result.get("verification_result"),
        settlement_date=result.get("settlement_date"),
        approval_card=approval_card_data,
        speech_audio_base64=result.get("speech_audio_base64"),
        speech_duration_seconds=result.get("speech_duration_seconds"),
        is_synthetic=True,
    )

@merchant_router.post("/approvals/{approval_id}/decide", response_model=ApprovalDecisionResponse)
def decide_approval(
    approval_id: str,
    req: ApprovalDecisionRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    merchant_id = user.get("sub", "mer_sharma_kirana")

    approval = db.query(ActionApproval).filter_by(id=approval_id).first()
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request {approval_id} not found.",
        )

    decision_norm = req.decision.upper()
    if decision_norm not in ("APPROVED", "REJECTED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decision must be either 'APPROVED' or 'REJECTED'.",
        )

    approval.decision = ApprovalDecision[decision_norm]
    
    # Update linked task state
    task_id = approval.task_id or ""
    chip_status = "executed" if decision_norm == "APPROVED" else "needs_human"
    
    if approval.task_id:
        task = db.query(Task).filter_by(id=approval.task_id).first()
        if task:
            if decision_norm == "APPROVED":
                task.bucket = TaskBucket.EXECUTED
                task.description = f"{task.description} [Approved by merchant on {datetime.now(timezone.utc).strftime('%d %b %H:%M')}]"
            else:
                task.bucket = TaskBucket.NEEDS_HUMAN
                task.description = f"{task.description} [Rejected by merchant: {req.reason or 'Dismissed'}]"

    # Audit merchant decision
    audit_log(
        db=db,
        actor=merchant_id,
        action="MERCHANT_APPROVAL_DECISION",
        target=approval.id,
        result=decision_norm,
        policy_decision_id="dec_approval_merchant_action",
    )

    db.commit()

    return ApprovalDecisionResponse(
        approval_id=approval.id,
        task_id=task_id,
        decision=decision_norm,
        chip_status=chip_status,
        message=f"Action successfully {decision_norm.lower()} by merchant.",
    )

@merchant_router.post("/device/{device_ref}/toggle-status", response_model=DeviceToggleResponse)
def toggle_device_status(
    device_ref: str,
    target_status: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Demo Toggle: Flips a device between ONLINE and OFFLINE / ERROR for test and live demonstration.
    """
    merchant_id = user.get("sub", "mer_sharma_kirana")
    adapter = MockDeviceAdapter(db)
    dev = adapter.get_device_by_serial(device_ref)
    if not dev:
        dev = adapter.get_device_by_id(device_ref)
    if not dev:
        dev = adapter.get_device_by_merchant(merchant_id)

    if not dev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {device_ref} not found.",
        )

    new_st = target_status.upper() if target_status else ("OFFLINE" if dev.status == "ONLINE" else "ONLINE")
    adapter.flip_device_status(dev.serial_number, new_st)

    audit_log(
        db=db,
        actor=merchant_id,
        action="DEMO_DEVICE_STATUS_TOGGLED",
        target=dev.serial_number,
        result=new_st,
        policy_decision_id="dec_demo_toggle",
    )

    return DeviceToggleResponse(
        success=True,
        device_id=dev.id,
        serial_number=dev.serial_number,
        new_status=new_st,
        message=f"Soundbox {dev.serial_number} status flipped to {new_st} (Demo Toggle).",
    )
