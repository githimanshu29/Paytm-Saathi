import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    Text,
    Index,
)
from sqlalchemy.orm import relationship
from app.db.base import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class EmployeeRole(str, enum.Enum):
    SUPPORT_AGENT = "support_agent"
    MANAGER = "manager"
    SALES_REP = "sales_rep"
    ADMIN = "admin"

class TaskBucket(str, enum.Enum):
    VERIFIED = "verified"
    EXECUTED = "executed"
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    NEEDS_HUMAN = "needs_human"

class ApprovalDecision(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class TransactionStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"
    REVERSED = "REVERSED"

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchants = relationship("Merchant", back_populates="tenant")
    employees = relationship("Employee", back_populates="tenant")

class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False)
    store_name = Column(String(255), nullable=False)
    merchant_name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False)
    city = Column(String(100), nullable=False)
    status = Column(String(50), default="ACTIVE", nullable=False)
    onboarding_status = Column(String(50), default="COMPLETED", nullable=False)
    kyc_status = Column(String(50), default="VERIFIED", nullable=False)
    
    # Safety and synthetic governance
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="merchants")
    devices = relationship("Device", back_populates="merchant")
    transactions = relationship("Transaction", back_populates="merchant")
    customers = relationship("Customer", back_populates="merchant")
    receivables = relationship("Receivable", back_populates="merchant")
    tasks = relationship("Task", back_populates="merchant")
    settlements = relationship("Settlement", back_populates="merchant")
    fees = relationship("TransactionFee", back_populates="merchant")
    chargebacks = relationship("Chargeback", back_populates="merchant")
    activity_metrics = relationship("MerchantActivityMetric", back_populates="merchant")
    followups = relationship("MerchantFollowup", back_populates="merchant")
    documents = relationship("MerchantDocument", back_populates="merchant", cascade="all, delete-orphan")

class Employee(Base):
    __tablename__ = "employees"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    role = Column(SQLEnum(EmployeeRole), nullable=False)
    
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="employees")

class Device(Base):
    __tablename__ = "devices"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False)
    merchant_id = Column(String(64), ForeignKey("merchants.id"), nullable=False)
    device_type = Column(String(100), default="Soundbox", nullable=False)
    serial_number = Column(String(100), unique=True, nullable=False)
    sim_number = Column(String(50), nullable=True)
    battery_level = Column(Integer, default=100, nullable=False)
    status = Column(String(50), default="ONLINE", nullable=False)
    
    # Extended telemetry fields for Fix Agent (Phase 5)
    last_heartbeat = Column(DateTime, nullable=True)
    signal_strength_dbm = Column(Integer, default=-70, nullable=True)
    firmware_version = Column(String(50), default="v3.4.1", nullable=True)
    reboot_in_progress = Column(Boolean, default=False, nullable=False)
    technician_visit_booked = Column(Boolean, default=False, nullable=False)
    technician_slot = Column(String(100), nullable=True)
    
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="devices")

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False)
    merchant_id = Column(String(64), ForeignKey("merchants.id"), nullable=False)
    # Integer minor units (paise) - e.g. 10000 paise = 100.00 INR
    amount = Column(Integer, nullable=False)
    currency = Column(String(10), default="INR", nullable=False)
    status = Column(String(50), default="SUCCESS", nullable=False)
    payment_rail = Column(String(50), default="UPI", nullable=False)
    utr_or_ref = Column(String(100), nullable=True)
    customer_name = Column(String(255), nullable=True)
    
    # Extended payment status fields
    bank_response_code = Column(String(50), nullable=True)
    reversal_status = Column(String(50), nullable=True)
    payer_vpa = Column(String(100), nullable=True)
    
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="transactions")
    fees = relationship("TransactionFee", back_populates="transaction")
    chargebacks = relationship("Chargeback", back_populates="transaction")

class Customer(Base):
    __tablename__ = "customers"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False)
    merchant_id = Column(String(64), ForeignKey("merchants.id"), nullable=False)
    name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False)
    notes = Column(Text, nullable=True)
    
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="customers")
    receivables = relationship("Receivable", back_populates="customer")

class Receivable(Base):
    __tablename__ = "receivables"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False)
    merchant_id = Column(String(64), ForeignKey("merchants.id"), nullable=False)
    customer_id = Column(String(64), ForeignKey("customers.id"), nullable=False)
    # Stored in minor units (paise)
    amount = Column(Integer, nullable=False)
    due_date = Column(DateTime, nullable=True)
    status = Column(String(50), default="PENDING", nullable=False)
    notes = Column(Text, nullable=True)
    
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="receivables")
    customer = relationship("Customer", back_populates="receivables")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False)
    merchant_id = Column(String(64), ForeignKey("merchants.id"), nullable=False)
    device_id = Column(String(64), ForeignKey("devices.id"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    bucket = Column(SQLEnum(TaskBucket), default=TaskBucket.PENDING, nullable=False)
    priority = Column(String(32), default="MEDIUM", nullable=False)
    assigned_to = Column(String(255), nullable=True)
    evidence_notes = Column(Text, nullable=True)
    evidence_url = Column(String(255), nullable=True)
    dispute_amount = Column(Integer, nullable=True)
    
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="tasks")
    approvals = relationship("ActionApproval", back_populates="task")

class ActionApproval(Base):
    __tablename__ = "action_approvals"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False)
    task_id = Column(String(64), ForeignKey("tasks.id"), nullable=True)
    approver = Column(String(255), nullable=True)
    decision = Column(SQLEnum(ApprovalDecision), default=ApprovalDecision.PENDING, nullable=False)
    reason = Column(Text, nullable=True)
    risk_tier = Column(String(10), default="R2", nullable=False)
    proposal_hash = Column(String(128), nullable=False)
    expires_at = Column(DateTime, nullable=True)
    
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    task = relationship("Task", back_populates="approvals")

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=True)
    actor = Column(String(255), nullable=False)
    action = Column(String(255), nullable=False)
    target = Column(String(255), nullable=False)
    policy_decision_id = Column(String(64), nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    result = Column(String(255), nullable=False)
    
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_audit_events_actor", "actor"),
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_idempotency_key", "idempotency_key"),
    )

class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=True)
    job_type = Column(String(64), nullable=False)  # e.g. "DEVICE_RECHECK"
    target_id = Column(String(64), nullable=False)  # e.g. device serial or ID
    run_at = Column(DateTime, nullable=False)
    status = Column(String(32), default="SCHEDULED", nullable=False)  # SCHEDULED | RUNNING | COMPLETED | FAILED
    idempotency_key = Column(String(128), unique=True, nullable=False)
    payload_json = Column(Text, nullable=True)
    
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class TransactionFee(Base):
    __tablename__ = "transaction_fees"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False)
    merchant_id = Column(String(64), ForeignKey("merchants.id"), nullable=False)
    transaction_id = Column(String(64), ForeignKey("transactions.id"), nullable=True)
    # Integer minor units (paise)
    amount = Column(Integer, nullable=False)
    fee_type = Column(String(50), default="MDR", nullable=False)  # MDR | GST | SOUNDBOX_RENTAL | PLATFORM_FEE
    description = Column(String(255), nullable=True)
    settlement_date = Column(String(20), nullable=True)  # YYYY-MM-DD
    
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="fees")
    transaction = relationship("Transaction", back_populates="fees")

class Chargeback(Base):
    __tablename__ = "chargebacks"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False)
    merchant_id = Column(String(64), ForeignKey("merchants.id"), nullable=False)
    transaction_id = Column(String(64), ForeignKey("transactions.id"), nullable=True)
    # Integer minor units (paise)
    amount = Column(Integer, nullable=False)
    status = Column(String(50), default="PROCESSED", nullable=False)  # OPEN | PROCESSED | DISPUTED | REVERSED
    reason = Column(String(255), nullable=False)  # CUSTOMER_DISPUTE | DUPLICATE_DEBIT | FRAUD_CLAIM
    dispute_ref = Column(String(100), nullable=True)
    evidence_notes = Column(Text, nullable=True)
    settlement_date = Column(String(20), nullable=True)  # YYYY-MM-DD
    
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="chargebacks")
    transaction = relationship("Transaction", back_populates="chargebacks")

class Settlement(Base):
    __tablename__ = "settlements"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False)
    merchant_id = Column(String(64), ForeignKey("merchants.id"), nullable=False)
    settlement_date = Column(String(20), nullable=False)  # YYYY-MM-DD
    
    # Deterministic integer minor units (paise) - never floats
    gross_sales = Column(Integer, default=0, nullable=False)
    refunds = Column(Integer, default=0, nullable=False)
    fees = Column(Integer, default=0, nullable=False)
    chargebacks = Column(Integer, default=0, nullable=False)
    net_expected = Column(Integer, default=0, nullable=False)
    net_settled = Column(Integer, default=0, nullable=False)
    discrepancy = Column(Integer, default=0, nullable=False)
    
    status = Column(String(50), default="RECONCILED", nullable=False)  # RECONCILED | DISCREPANCY | DISPUTED
    bank_utr = Column(String(100), nullable=True)
    nodal_account = Column(String(100), default="ICICI_NODAL_0192", nullable=True)
    dispute_case_id = Column(String(64), nullable=True)
    evidence_attached = Column(Text, nullable=True)
    
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="settlements")


class MerchantActivityMetric(Base):
    __tablename__ = "merchant_activity_metrics"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False)
    merchant_id = Column(String(64), ForeignKey("merchants.id"), nullable=False)

    baseline_daily_tx_count = Column(Integer, default=30, nullable=False)
    baseline_daily_volume_paise = Column(Integer, default=1000000, nullable=False)  # in paise
    recent_daily_tx_count = Column(Integer, default=10, nullable=False)
    recent_daily_volume_paise = Column(Integer, default=300000, nullable=False)  # in paise
    drop_percentage = Column(Integer, default=70, nullable=False)  # integer percentage drop

    health_status = Column(String(50), default="AT_RISK", nullable=False)  # HEALTHY | AT_RISK | DORMANT
    diagnosed_cause = Column(String(50), nullable=True)  # DEVICE_ISSUE | SETTLEMENT_ISSUE | COMPETITOR_OR_DISENGAGEMENT
    revival_stage = Column(String(50), default="AT_RISK", nullable=False)  # AT_RISK | FOLLOWUP_SENT | WARM_LEAD | REVIVED

    last_scanned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    recovered_at = Column(DateTime, nullable=True)

    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="activity_metrics")


class MerchantFollowup(Base):
    __tablename__ = "merchant_followups"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False)
    merchant_id = Column(String(64), ForeignKey("merchants.id"), nullable=False)

    cause_type = Column(String(50), nullable=False)  # DEVICE_ISSUE | SETTLEMENT_ISSUE | COMPETITOR_OR_DISENGAGEMENT
    message_title = Column(String(255), nullable=False)
    message_body = Column(Text, nullable=False)
    offer_code = Column(String(100), nullable=True)
    offer_details = Column(Text, nullable=True)

    status = Column(String(50), default="DELIVERED", nullable=False)  # PENDING | DELIVERED | ACCEPTED | DISMISSED | REVIVED
    handed_off_to = Column(String(50), nullable=True)  # FIX | RECONCILE | FIELDMATE_SALES_REP
    task_id = Column(String(64), nullable=True)

    delivered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    responded_at = Column(DateTime, nullable=True)
    merchant_response = Column(String(50), nullable=True)  # ACCEPTED | DISMISSED

    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="followups")


class MerchantDocument(Base):
    __tablename__ = "merchant_documents"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False)
    merchant_id = Column(String(64), ForeignKey("merchants.id"), nullable=False)

    document_type = Column(String(50), nullable=False)  # PAN_CARD | BANK_PROOF | SHOP_PHOTO
    status = Column(String(50), default="MISSING", nullable=False)  # MISSING | UPLOADED | OCR_FAILED | OCR_PASSED | VERIFIED | REJECTED

    file_url = Column(String(512), nullable=True)
    file_name = Column(String(255), nullable=True)

    # Candidate OCR extraction (Explicitly untrusted until separate verification)
    ocr_quality_flag = Column(String(50), nullable=True)  # CLEAR | BLURRY | CROPPED | GLARE
    ocr_candidate_fields = Column(Text, nullable=True)  # JSON string of candidate fields
    ocr_confidence = Column(Float, nullable=True)
    is_ocr_passed = Column(Boolean, default=False, nullable=False)
    rejection_reason = Column(String(255), nullable=True)

    # Simulated authorized verification step (NSDL / Penny Drop / Geolocation check)
    authorized_verification_status = Column(String(50), default="PENDING", nullable=False)  # PENDING | VERIFIED | FAILED
    verified_at = Column(DateTime, nullable=True)

    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="documents")
