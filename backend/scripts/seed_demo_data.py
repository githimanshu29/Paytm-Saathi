import os
import sys
from datetime import datetime, timedelta, timezone

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.core.security import hash_password
from app.db.models import (
    Tenant,
    Merchant,
    Employee,
    EmployeeRole,
    Device,
    Transaction,
    Customer,
    Receivable,
    Task,
    TaskBucket,
    ActionApproval,
    ApprovalDecision,
    AuditEvent,
)

def seed_demo_data():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # Check if tenant exists
        tenant = db.query(Tenant).filter_by(id="tenant_paytm_demo").first()
        if not tenant:
            tenant = Tenant(
                id="tenant_paytm_demo",
                name="Paytm Retail India",
            )
            db.add(tenant)
            db.flush()

        # Seed Employees with bcrypt hashed password: Demo@1234
        default_pwd_hash = hash_password("Demo@1234")
        employees_data = [
            {
                "id": "emp_support_01",
                "email": "support@paytm.demo",
                "hashed_password": default_pwd_hash,
                "name": "Rajesh Sharma",
                "role": EmployeeRole.SUPPORT_AGENT,
            },
            {
                "id": "emp_manager_01",
                "email": "manager@paytm.demo",
                "hashed_password": default_pwd_hash,
                "name": "Pooja Malhotra",
                "role": EmployeeRole.MANAGER,
            },
            {
                "id": "emp_sales_01",
                "email": "sales@paytm.demo",
                "hashed_password": default_pwd_hash,
                "name": "Amit Verma",
                "role": EmployeeRole.SALES_REP,
            },
            {
                "id": "emp_admin_01",
                "email": "admin@paytm.demo",
                "hashed_password": default_pwd_hash,
                "name": "Sunita Rao",
                "role": EmployeeRole.ADMIN,
            },
        ]

        for emp in employees_data:
            existing = db.query(Employee).filter_by(id=emp["id"]).first()
            if not existing:
                db.add(
                    Employee(
                        id=emp["id"],
                        tenant_id=tenant.id,
                        email=emp["email"],
                        hashed_password=emp["hashed_password"],
                        name=emp["name"],
                        role=emp["role"],
                        is_synthetic=True,
                        environment="DEMO",
                    )
                )
        db.flush()

        # Merchant 1: Ramesh Sharma - Healthy Kirana store with active Soundbox & Udhaar
        m1 = db.query(Merchant).filter_by(id="mer_sharma_kirana").first()
        if not m1:
            m1 = Merchant(
                id="mer_sharma_kirana",
                tenant_id=tenant.id,
                store_name="Sharma Kirana Store",
                merchant_name="Ramesh Sharma",
                phone="+919876543210",
                city="Jaipur",
                status="ACTIVE",
                onboarding_status="COMPLETED",
                kyc_status="VERIFIED",
                is_synthetic=True,
                environment="DEMO",
            )
            db.add(m1)
            db.flush()

            # Device
            db.add(
                Device(
                    id="dev_soundbox_101",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    device_type="Soundbox 4G Pro",
                    serial_number="SB-JAI-101",
                    sim_number="8991001234567890",
                    battery_level=88,
                    status="ONLINE",
                    is_synthetic=True,
                    environment="DEMO",
                )
            )

            # Baseline successful transactions (amounts in paise)
            t1_date = now - timedelta(minutes=45)
            db.add(
                Transaction(
                    id="txn_sharma_001",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    amount=15000,  # 150.00 INR
                    currency="INR",
                    status="SUCCESS",
                    payment_rail="UPI",
                    utr_or_ref="PAYTM_UTR_90812301",
                    customer_name="Pankaj Roy",
                    bank_response_code="00_SUCCESS",
                    reversal_status="NONE",
                    payer_vpa="pankaj@okaxis",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=t1_date,
                )
            )
            db.add(
                Transaction(
                    id="txn_sharma_002",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    amount=45000,  # 450.00 INR
                    currency="INR",
                    status="SUCCESS",
                    payment_rail="UPI",
                    utr_or_ref="PAYTM_UTR_90812302",
                    customer_name="Sneha Patil",
                    bank_response_code="00_SUCCESS",
                    reversal_status="NONE",
                    payer_vpa="sneha@okhdfcbank",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=now - timedelta(hours=2),
                )
            )

            # --- Phase 4 Scenario Transactions for Resolve Agent ---
            # (a) Auto-reversal in progress (NPCI U30: expected timeline T+2 / 24-48 hrs)
            db.add(
                Transaction(
                    id="txn_failed_autoreversal",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    amount=25000,  # 250.00 INR
                    currency="INR",
                    status="FAILED",
                    payment_rail="UPI",
                    utr_or_ref="PAYTM_REV_AUTO_991201",
                    customer_name="Alok Gupta",
                    bank_response_code="U30_AUTO_REVERSAL",
                    reversal_status="IN_PROGRESS",
                    payer_vpa="alok@okhdfcbank",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=now - timedelta(hours=3),
                )
            )

            # (b) Reversal stuck (NPCI U69 timeout, >48h old) -> requires refund review task
            db.add(
                Transaction(
                    id="txn_stuck_reversal",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    amount=50000,  # 500.00 INR
                    currency="INR",
                    status="FAILED",
                    payment_rail="UPI",
                    utr_or_ref="PAYTM_STUCK_881920",
                    customer_name="Deepak Verma",
                    bank_response_code="U69_REVERSAL_STUCK",
                    reversal_status="STUCK",
                    payer_vpa="deepak@paytm",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=now - timedelta(hours=52),
                )
            )

            # (c) Actually succeeded (Bank 00) -> customer claimed failure, but payment was credited
            db.add(
                Transaction(
                    id="txn_success_confirmed",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    amount=32000,  # 320.00 INR
                    currency="INR",
                    status="SUCCESS",
                    payment_rail="UPI",
                    utr_or_ref="PAYTM_SUCC_771829",
                    customer_name="Pooja Chawla",
                    bank_response_code="00_SUCCESS",
                    reversal_status="NONE",
                    payer_vpa="pooja@icici",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=now - timedelta(hours=1),
                )
            )

            # (d) Ambiguous / fraud-flavored (Bank ZA security hold) -> escalates to needs_human
            db.add(
                Transaction(
                    id="txn_fraud_ambiguous",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    amount=120000,  # 1,200.00 INR
                    currency="INR",
                    status="PENDING",
                    payment_rail="UPI",
                    utr_or_ref="PAYTM_FRAUD_661904",
                    customer_name="Unknown Payer",
                    bank_response_code="ZA_SECURITY_HOLD",
                    reversal_status="NONE",
                    payer_vpa="suspicious.vpa.99@ybl",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=now - timedelta(hours=4),
                )
            )

            # Customer & Receivable (Udhaar)
            c1 = Customer(
                id="cust_vikram_singh",
                tenant_id=tenant.id,
                merchant_id=m1.id,
                name="Vikram Singh",
                phone="+919811122233",
                notes="Regular neighbor customer, weekly milk & grains settlement",
                is_synthetic=True,
                environment="DEMO",
            )
            db.add(c1)
            db.flush()

            db.add(
                Receivable(
                    id="rec_sharma_001",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    customer_id=c1.id,
                    amount=85000,  # 850.00 INR
                    due_date=now + timedelta(days=3),
                    status="PENDING",
                    notes="Aata bag and spices bought on credit",
                    is_synthetic=True,
                    environment="DEMO",
                )
            )

            # Task 1: Verified bucket
            t_verified = Task(
                id="task_sharma_001",
                tenant_id=tenant.id,
                merchant_id=m1.id,
                title="Daily settlement reconciliation verified",
                description="Auto-reconciled 42 transactions against ICICI nodal account",
                bucket=TaskBucket.VERIFIED,
                priority="LOW",
                assigned_to="Saathi Reconcile Agent",
                is_synthetic=True,
                environment="DEMO",
            )
            db.add(t_verified)

            # Task 2: Executed bucket
            t_executed = Task(
                id="task_sharma_002",
                tenant_id=tenant.id,
                merchant_id=m1.id,
                title="Soundbox audio announcement language updated to Hindi",
                description="Language preference applied and confirmed by Soundbox telemetry",
                bucket=TaskBucket.EXECUTED,
                priority="LOW",
                assigned_to="Saathi Fix Agent",
                is_synthetic=True,
                environment="DEMO",
            )
            db.add(t_executed)

        # Merchant 2: Suresh Verma (Kanpur)
        m2 = db.query(Merchant).filter_by(id="mer_verma_sweets").first()
        if not m2:
            m2 = Merchant(
                id="mer_verma_sweets",
                tenant_id=tenant.id,
                store_name="Verma Sweets & Chaat",
                merchant_name="Suresh Verma",
                phone="+919812345678",
                city="Kanpur",
                status="ACTIVE",
                onboarding_status="COMPLETED",
                kyc_status="VERIFIED",
                is_synthetic=True,
                environment="DEMO",
            )
            db.add(m2)
            db.flush()

            db.add(
                Device(
                    id="dev_soundbox_202",
                    tenant_id=tenant.id,
                    merchant_id=m2.id,
                    device_type="Soundbox 2.0",
                    serial_number="SB-KNP-202",
                    sim_number="8991009876543210",
                    battery_level=12,
                    status="ERROR",
                    is_synthetic=True,
                    environment="DEMO",
                )
            )

            db.add(
                Transaction(
                    id="txn_verma_001",
                    tenant_id=tenant.id,
                    merchant_id=m2.id,
                    amount=35000,  # 350.00 INR
                    currency="INR",
                    status="FAILED",
                    payment_rail="UPI",
                    utr_or_ref="PAYTM_FAIL_4049182",
                    customer_name="Manoj Tiwari",
                    bank_response_code="U69_REVERSAL_STUCK",
                    reversal_status="STUCK",
                    payer_vpa="manoj@ybl",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=now - timedelta(hours=3),
                )
            )

            # Task: Awaiting approval
            t_awaiting = Task(
                id="task_verma_001",
                tenant_id=tenant.id,
                merchant_id=m2.id,
                title="Soundbox network SIM reset and technician visit dispatch",
                description="Device offline due to cell tower handover fault. Proposing OTA SIM refresh.",
                bucket=TaskBucket.AWAITING_APPROVAL,
                priority="HIGH",
                assigned_to="Saathi Fix Agent",
                is_synthetic=True,
                environment="DEMO",
            )
            db.add(t_awaiting)
            db.flush()

            db.add(
                ActionApproval(
                    id="appr_verma_001",
                    tenant_id=tenant.id,
                    task_id=t_awaiting.id,
                    approver="Suresh Verma (Merchant)",
                    decision=ApprovalDecision.PENDING,
                    reason="Merchant authorization required to restart device remotely or schedule visit",
                    risk_tier="R2",
                    proposal_hash="hash_ota_sim_refresh_verma_202",
                    expires_at=now + timedelta(hours=24),
                    is_synthetic=True,
                    environment="DEMO",
                )
            )

        # Merchant 3: Neha Gupta (Delhi)
        m3 = db.query(Merchant).filter_by(id="mer_gupta_electronics").first()
        if not m3:
            m3 = Merchant(
                id="mer_gupta_electronics",
                tenant_id=tenant.id,
                store_name="Gupta Electronics",
                merchant_name="Neha Gupta",
                phone="+919823456789",
                city="Delhi",
                status="PENDING",
                onboarding_status="PENDING_DOCUMENTATION",
                kyc_status="DOCUMENTS_REQUIRED",
                is_synthetic=True,
                environment="DEMO",
            )
            db.add(m3)
            db.flush()

            # Task: Needs human
            t_needs_human = Task(
                id="task_gupta_001",
                tenant_id=tenant.id,
                merchant_id=m3.id,
                title="KYC bank statement re-upload mismatch review",
                description="Bank passbook account name differs by one letter from PAN card. Requires compliance officer decision.",
                bucket=TaskBucket.NEEDS_HUMAN,
                priority="HIGH",
                assigned_to="Pooja Malhotra (Manager)",
                is_synthetic=True,
                environment="DEMO",
            )
            db.add(t_needs_human)

        # Merchant 4: Dinesh Yadav (Lucknow)
        m4 = db.query(Merchant).filter_by(id="mer_laxmi_dairy").first()
        if not m4:
            m4 = Merchant(
                id="mer_laxmi_dairy",
                tenant_id=tenant.id,
                store_name="Laxmi Dairy & Provisions",
                merchant_name="Dinesh Yadav",
                phone="+919834567890",
                city="Lucknow",
                status="DORMANT",
                onboarding_status="COMPLETED",
                kyc_status="VERIFIED",
                is_synthetic=True,
                environment="DEMO",
            )
            db.add(m4)
            db.flush()

            db.add(
                Device(
                    id="dev_soundbox_303",
                    tenant_id=tenant.id,
                    merchant_id=m4.id,
                    device_type="Soundbox 3.0",
                    serial_number="SB-LKO-303",
                    sim_number="8991005544332211",
                    battery_level=5,
                    status="OFFLINE",
                    is_synthetic=True,
                    environment="DEMO",
                )
            )

            # Historical transaction
            db.add(
                Transaction(
                    id="txn_laxmi_001",
                    tenant_id=tenant.id,
                    merchant_id=m4.id,
                    amount=8000,  # 80.00 INR
                    currency="INR",
                    status="SUCCESS",
                    payment_rail="UPI",
                    utr_or_ref="PAYTM_HIST_109283",
                    customer_name="Ravi Kumar",
                    bank_response_code="00_SUCCESS",
                    reversal_status="NONE",
                    payer_vpa="ravi@okhdfcbank",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=now - timedelta(days=22),
                )
            )

            # Task: Pending bucket
            t_pending = Task(
                id="task_laxmi_001",
                tenant_id=tenant.id,
                merchant_id=m4.id,
                title="Evaluate merchant dormant recovery outreach",
                description="Zero transactions in last 21 days. Soundbox discharged. Field visit candidate.",
                bucket=TaskBucket.PENDING,
                priority="MEDIUM",
                assigned_to="Saathi Revive Agent",
                is_synthetic=True,
                environment="DEMO",
            )
            db.add(t_pending)

        # Initial audit log
        audit_event = AuditEvent(
            id="audit_initial_seed",
            tenant_id=tenant.id,
            actor="system_seeder",
            action="SEED_DEMO_DATA",
            target="database_tables",
            policy_decision_id="dec_system_seed",
            idempotency_key="idemp_seed_20261029",
            result="SUCCESS",
            is_synthetic=True,
            environment="DEMO",
        )
        db.add(audit_event)

        db.commit()
        print("Demo data successfully seeded with Phase 4 scenario transactions.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding demo data: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_demo_data()
