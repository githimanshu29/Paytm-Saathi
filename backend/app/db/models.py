import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Enum as SQLEnum,
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
    
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

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
    
    is_synthetic = Column(Boolean, default=True, nullable=False)
    environment = Column(String(32), default="DEMO", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="transactions")

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
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    bucket = Column(SQLEnum(TaskBucket), default=TaskBucket.PENDING, nullable=False)
    priority = Column(String(32), default="MEDIUM", nullable=False)
    assigned_to = Column(String(255), nullable=True)
    
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
