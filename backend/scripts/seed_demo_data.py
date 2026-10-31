import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
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
    TransactionFee,
    Chargeback,
    Settlement,
    MerchantActivityMetric,
    MerchantFollowup,
    MerchantDocument,
)
from app.core.security import hash_password

def seed_demo_data():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # 1. Tenant
        tenant = db.query(Tenant).filter_by(id="tenant_paytm_demo").first()
        if not tenant:
            tenant = Tenant(
                id="tenant_paytm_demo",
                name="Paytm Saathi Demo Tenant",
            )
            db.add(tenant)
            db.flush()

        # 2. Employees (Multiple Roles)
        employees_data = [
            ("emp_support_01", "support@paytm.demo", "Rajesh Sharma", EmployeeRole.SUPPORT_AGENT),
            ("emp_manager_01", "manager@paytm.demo", "Pooja Malhotra", EmployeeRole.MANAGER),
            ("emp_sales_01", "sales@paytm.demo", "Amit Verma", EmployeeRole.SALES_REP),
            ("emp_admin_01", "admin@paytm.demo", "Vikram Batra", EmployeeRole.ADMIN),
        ]

        for emp_id, email, name, role in employees_data:
            existing = db.query(Employee).filter_by(email=email).first()
            if not existing:
                db.add(
                    Employee(
                        id=emp_id,
                        tenant_id=tenant.id,
                        email=email,
                        name=name,
                        role=role,
                        hashed_password=hash_password("Demo@1234"),
                        is_synthetic=True,
                        environment="DEMO",
                    )
                )

        # 3. Merchants & Devices
        # Merchant 1: Sharma Kirana Store (Jaipur) - Active, Online Soundbox
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

            # Device: Online Soundbox with fresh telemetry
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
                    last_heartbeat=now - timedelta(minutes=2),
                    signal_strength_dbm=-65,
                    firmware_version="v3.4.1",
                    reboot_in_progress=False,
                    technician_visit_booked=False,
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

            # Scenario Transactions for Resolve Agent
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

            # Phase 6: Settlements & Line Items
            # (1) Normal Day (2026-10-28, Yesterday) - Reconciles perfectly to 0 discrepancy
            d_norm = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)
            db.add(
                Transaction(
                    id="txn_sharma_norm_01",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    amount=600000,  # ₹6,000.00
                    currency="INR",
                    status="SUCCESS",
                    payment_rail="UPI",
                    utr_or_ref="UPI_SHARMA_28_01",
                    customer_name="Rohan Verma",
                    bank_response_code="00_SUCCESS",
                    reversal_status="NONE",
                    payer_vpa="rohan@okaxis",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=d_norm,
                )
            )
            db.add(
                Transaction(
                    id="txn_sharma_norm_02",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    amount=400000,  # ₹4,000.00
                    currency="INR",
                    status="SUCCESS",
                    payment_rail="UPI",
                    utr_or_ref="UPI_SHARMA_28_02",
                    customer_name="Kavita Mehta",
                    bank_response_code="00_SUCCESS",
                    reversal_status="NONE",
                    payer_vpa="kavita@okhdfcbank",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=d_norm,
                )
            )
            db.add(
                Transaction(
                    id="txn_sharma_norm_ref",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    amount=50000,  # ₹500.00
                    currency="INR",
                    status="REVERSED",
                    payment_rail="UPI",
                    utr_or_ref="UPI_SHARMA_28_REF",
                    customer_name="Alok Jain",
                    bank_response_code="00_SUCCESS",
                    reversal_status="COMPLETED",
                    payer_vpa="alok@paytm",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=d_norm,
                )
            )
            db.add(
                TransactionFee(
                    id="fee_sharma_norm_01",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    transaction_id="txn_sharma_norm_01",
                    amount=5000,  # ₹50.00 MDR
                    fee_type="MDR",
                    description="MDR fee (0.5% UPI volume)",
                    settlement_date="2026-10-28",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=d_norm,
                )
            )
            db.add(
                TransactionFee(
                    id="fee_sharma_norm_02",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    transaction_id=None,
                    amount=25000,  # ₹250.00
                    fee_type="SOUNDBOX_RENTAL",
                    description="Soundbox 4G Pro monthly subscription",
                    settlement_date="2026-10-28",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=d_norm,
                )
            )
            db.add(
                Settlement(
                    id="sett_sharma_20261028",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    settlement_date="2026-10-28",
                    gross_sales=1000000,  # ₹10,000.00
                    refunds=50000,        # ₹500.00
                    fees=30000,           # ₹300.00
                    chargebacks=0,        # ₹0.00
                    net_expected=920000,  # ₹9,200.00
                    net_settled=920000,   # ₹9,200.00
                    discrepancy=0,        # ₹0.00 (Fully Reconciled)
                    status="RECONCILED",
                    bank_utr="ICICINODAL99281028",
                    nodal_account="ICICI_NODAL_0192",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=d_norm,
                )
            )

            # (2) Anomalous Day (2026-10-27) - ₹1,200 (120,000 paise) shortfall discrepancy
            d_anom = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
            db.add(
                Transaction(
                    id="txn_sharma_anom_01",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    amount=900000,  # ₹9,000.00
                    currency="INR",
                    status="SUCCESS",
                    payment_rail="UPI",
                    utr_or_ref="UPI_SHARMA_27_01",
                    customer_name="Suresh Agarwal",
                    bank_response_code="00_SUCCESS",
                    reversal_status="NONE",
                    payer_vpa="suresh@okaxis",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=d_anom,
                )
            )
            db.add(
                Transaction(
                    id="txn_sharma_anom_02",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    amount=600000,  # ₹6,000.00
                    currency="INR",
                    status="SUCCESS",
                    payment_rail="UPI",
                    utr_or_ref="UPI_SHARMA_27_02",
                    customer_name="Neha Sharma",
                    bank_response_code="00_SUCCESS",
                    reversal_status="NONE",
                    payer_vpa="neha@icici",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=d_anom,
                )
            )
            db.add(
                Transaction(
                    id="txn_sharma_anom_ref",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    amount=100000,  # ₹1,000.00
                    currency="INR",
                    status="REVERSED",
                    payment_rail="UPI",
                    utr_or_ref="UPI_SHARMA_27_REF",
                    customer_name="Vikram Singh",
                    bank_response_code="00_SUCCESS",
                    reversal_status="COMPLETED",
                    payer_vpa="vikram@paytm",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=d_anom,
                )
            )
            db.add(
                TransactionFee(
                    id="fee_sharma_anom_01",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    transaction_id="txn_sharma_anom_01",
                    amount=45000,  # ₹450.00
                    fee_type="MDR",
                    description="MDR and payment gateway processing fee",
                    settlement_date="2026-10-27",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=d_anom,
                )
            )
            db.add(
                Chargeback(
                    id="cb_sharma_anom_01",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    transaction_id="txn_sharma_anom_02",
                    amount=55000,  # ₹550.00
                    status="PROCESSED",
                    reason="CUSTOMER_FRAUD_CLAIM",
                    dispute_ref="CB_ICICI_99812",
                    evidence_notes="Customer claimed card clone / unauthorized UPI intent debit",
                    settlement_date="2026-10-27",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=d_anom,
                )
            )
            db.add(
                Settlement(
                    id="sett_sharma_20261027",
                    tenant_id=tenant.id,
                    merchant_id=m1.id,
                    settlement_date="2026-10-27",
                    gross_sales=1500000,   # ₹15,000.00
                    refunds=100000,        # ₹1,000.00
                    fees=45000,            # ₹450.00
                    chargebacks=55000,      # ₹550.00
                    net_expected=1300000,  # ₹13,000.00
                    net_settled=1180000,   # ₹11,800.00
                    discrepancy=-120000,   # -₹1,200.00 Shortfall
                    status="DISPUTED",
                    bank_utr="ICICINODAL99271027",
                    nodal_account="ICICI_NODAL_0192",
                    evidence_attached="ICICI Nodal Batch statement #BATCH-20261027-01 shows payout of ₹11,800.00 vs expected net ₹13,000.00 (Shortfall: ₹1,200.00).",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=d_anom,
                )
            )

        # Merchant 2: Suresh Verma (Kanpur) - Degraded Soundbox 2.0 (Low Battery & Weak Signal)
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
                    battery_level=85,
                    status="ONLINE",
                    last_heartbeat=now - timedelta(minutes=10),
                    signal_strength_dbm=-68,
                    firmware_version="v2.1.0",
                    reboot_in_progress=False,
                    technician_visit_booked=False,
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
                device_id="dev_soundbox_202",
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

            # Phase 6: Settlements for Verma Sweets
            db.add(
                Settlement(
                    id="sett_verma_20261028",
                    tenant_id=tenant.id,
                    merchant_id=m2.id,
                    settlement_date="2026-10-28",
                    gross_sales=800000,
                    refunds=40000,
                    fees=24000,
                    chargebacks=0,
                    net_expected=736000,
                    net_settled=736000,
                    discrepancy=0,
                    status="RECONCILED",
                    bank_utr="ICICINODAL88281028",
                    nodal_account="ICICI_NODAL_0192",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc),
                )
            )
            db.add(
                Settlement(
                    id="sett_verma_20261027",
                    tenant_id=tenant.id,
                    merchant_id=m2.id,
                    settlement_date="2026-10-27",
                    gross_sales=1200000,
                    refunds=80000,
                    fees=36000,
                    chargebacks=40000,
                    net_expected=1044000,
                    net_settled=950000,
                    discrepancy=-94000,  # Shortfall: -₹940.00
                    status="DISCREPANCY",
                    bank_utr="ICICINODAL88271027",
                    nodal_account="ICICI_NODAL_0192",
                    evidence_attached="ICICI Nodal Batch statement mismatch: Credited ₹9,500.00 vs expected net ₹10,440.00 (Shortfall: ₹940.00).",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc),
                )
            )

        # Merchant 3: Neha Gupta (Delhi) - Offline Device stuck in firmware boot loop
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

            db.add(
                Device(
                    id="dev_soundbox_404",
                    tenant_id=tenant.id,
                    merchant_id=m3.id,
                    device_type="Soundbox 4G Pro",
                    serial_number="SB-DEL-404",
                    sim_number="8991007788990011",
                    battery_level=76,
                    status="OFFLINE",
                    last_heartbeat=now - timedelta(hours=2),
                    signal_strength_dbm=-85,
                    firmware_version="v3.4.0",
                    reboot_in_progress=False,
                    technician_visit_booked=False,
                    is_synthetic=True,
                    environment="DEMO",
                )
            )

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

            # Phase 6: Settlements for Gupta Electronics
            db.add(
                Settlement(
                    id="sett_gupta_20261028",
                    tenant_id=tenant.id,
                    merchant_id=m3.id,
                    settlement_date="2026-10-28",
                    gross_sales=2000000,
                    refunds=100000,
                    fees=60000,
                    chargebacks=0,
                    net_expected=1840000,
                    net_settled=1840000,
                    discrepancy=0,
                    status="RECONCILED",
                    bank_utr="ICICINODAL77281028",
                    nodal_account="ICICI_NODAL_0192",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc),
                )
            )
            db.add(
                Settlement(
                    id="sett_gupta_20261027",
                    tenant_id=tenant.id,
                    merchant_id=m3.id,
                    settlement_date="2026-10-27",
                    gross_sales=2500000,
                    refunds=150000,
                    fees=75000,
                    chargebacks=125000,
                    net_expected=2150000,
                    net_settled=1950000,
                    discrepancy=-200000,  # Shortfall: -₹2,000.00
                    status="DISCREPANCY",
                    bank_utr="ICICINODAL77271027",
                    nodal_account="ICICI_NODAL_0192",
                    evidence_attached="ICICI Nodal Batch statement mismatch: Credited ₹19,500.00 vs expected net ₹21,500.00 (Shortfall: ₹2,000.00).",
                    is_synthetic=True,
                    environment="DEMO",
                    created_at=datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc),
                )
            )

        # Merchant 4: Dinesh Yadav (Lucknow) - Dormant & Discharged Soundbox 3.0
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
                    last_heartbeat=now - timedelta(days=22),
                    signal_strength_dbm=-115,
                    firmware_version="v3.0.2",
                    reboot_in_progress=False,
                    technician_visit_booked=False,
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
                device_id="dev_soundbox_303",
                title="Evaluate merchant dormant recovery outreach",
                description="Zero transactions in last 21 days. Soundbox discharged. Field visit candidate.",
                bucket=TaskBucket.PENDING,
                priority="MEDIUM",
                assigned_to="Saathi Revive Agent",
                is_synthetic=True,
                environment="DEMO",
            )
            db.add(t_pending)

        # -------------------------------------------------------------
        # Phase 7: Seeded Activity Metrics & Retention Follow-ups
        # -------------------------------------------------------------
        # (1) Gupta Electronics: Volume drop caused by OFFLINE device
        db.add(
            MerchantActivityMetric(
                id="metric_gupta_dormancy",
                tenant_id=tenant.id,
                merchant_id="mer_gupta_electronics",
                baseline_daily_tx_count=50,
                baseline_daily_volume_paise=2000000,  # ₹20,000.00
                recent_daily_tx_count=4,
                recent_daily_volume_paise=160000,    # ₹1,600.00
                drop_percentage=92,
                health_status="AT_RISK",
                diagnosed_cause="DEVICE_ISSUE",
                revival_stage="AT_RISK",
                last_scanned_at=now,
                is_synthetic=True,
                environment="DEMO",
            )
        )

        # (2) Verma Sweets: Volume drop caused by UNRESOLVED settlement discrepancy
        db.add(
            MerchantActivityMetric(
                id="metric_verma_dormancy",
                tenant_id=tenant.id,
                merchant_id="mer_verma_sweets",
                baseline_daily_tx_count=35,
                baseline_daily_volume_paise=1200000,  # ₹12,000.00
                recent_daily_tx_count=8,
                recent_daily_volume_paise=250000,    # ₹2,500.00
                drop_percentage=79,
                health_status="AT_RISK",
                diagnosed_cause="SETTLEMENT_ISSUE",
                revival_stage="AT_RISK",
                last_scanned_at=now,
                is_synthetic=True,
                environment="DEMO",
            )
        )

        # (3) Sharma Kirana: Non-technical drop (Hardware & Settlements healthy -> Competitor / Disengagement)
        db.add(
            MerchantActivityMetric(
                id="metric_sharma_dormancy",
                tenant_id=tenant.id,
                merchant_id="mer_sharma_kirana",
                baseline_daily_tx_count=30,
                baseline_daily_volume_paise=950000,  # ₹9,500.00
                recent_daily_tx_count=9,
                recent_daily_volume_paise=285000,   # ₹2,850.00
                drop_percentage=70,
                health_status="AT_RISK",
                diagnosed_cause="COMPETITOR_OR_DISENGAGEMENT",
                revival_stage="FOLLOWUP_SENT",
                last_scanned_at=now,
                is_synthetic=True,
                environment="DEMO",
            )
        )

        # Active Follow-up delivered to Sharma Kirana
        db.add(
            MerchantFollowup(
                id="fol_sharma_revive_01",
                tenant_id=tenant.id,
                merchant_id="mer_sharma_kirana",
                cause_type="COMPETITOR_OR_DISENGAGEMENT",
                message_title="Special Kirana Growth Offer from Paytm Saathi",
                message_body="Namaste Sharma ji! We noticed a slowdown in your Soundbox announcements recently. To support your shop, we've unlocked the Kirana Booster: 0% MDR on your next 100 UPI transactions and ₹100 Soundbox cash rebate.",
                offer_code="KIRANA_BOOSTER_0MDR",
                offer_details="0% MDR on next 100 UPI transactions + ₹100 Soundbox rent rebate",
                status="DELIVERED",
                handed_off_to=None,
                delivered_at=now,
                is_synthetic=True,
                environment="DEMO",
            )
        )

        # -------------------------------------------------------------
        # Phase 8: Seeded KYC Applications & Incomplete Onboardings
        # -------------------------------------------------------------
        # Merchant 5: Rajesh Singh (Jaipur) - Missing Bank Proof
        m5 = db.query(Merchant).filter_by(id="mer_singh_automobiles").first()
        if not m5:
            m5 = Merchant(
                id="mer_singh_automobiles",
                tenant_id=tenant.id,
                store_name="Singh Automobiles & Spares",
                merchant_name="Rajesh Singh",
                phone="+919811223344",
                city="Jaipur",
                status="PENDING",
                onboarding_status="PENDING_DOCUMENTATION",
                kyc_status="DOCUMENTS_REQUIRED",
                is_synthetic=True,
                environment="DEMO",
            )
            db.add(m5)
            db.flush()

        # Merchant 6: Priya Sharma (Lucknow) - Missing Shop Photo
        m6 = db.query(Merchant).filter_by(id="mer_shree_radhe_bakery").first()
        if not m6:
            m6 = Merchant(
                id="mer_shree_radhe_bakery",
                tenant_id=tenant.id,
                store_name="Radhe Krishna Bakery",
                merchant_name="Priya Sharma",
                phone="+919822334455",
                city="Lucknow",
                status="PENDING",
                onboarding_status="PENDING_DOCUMENTATION",
                kyc_status="DOCUMENTS_REQUIRED",
                is_synthetic=True,
                environment="DEMO",
            )
            db.add(m6)
            db.flush()

        # Merchant 7: Sunil Verma (Mumbai) - Full-pass applicant ready for authorized verification
        m7 = db.query(Merchant).filter_by(id="mer_apex_retail").first()
        if not m7:
            m7 = Merchant(
                id="mer_apex_retail",
                tenant_id=tenant.id,
                store_name="Apex Fresh Mart",
                merchant_name="Sunil Verma",
                phone="+919833445566",
                city="Mumbai",
                status="PENDING",
                onboarding_status="UNDER_REVIEW",
                kyc_status="IN_VERIFICATION",
                is_synthetic=True,
                environment="DEMO",
            )
            db.add(m7)
            db.flush()

        # Seed Documents for Applications
        # 1. Sharma Kirana (Fully Active & Verified)
        docs_sharma = [
            MerchantDocument(
                id="doc_sharma_pan",
                tenant_id=tenant.id,
                merchant_id="mer_sharma_kirana",
                document_type="PAN_CARD",
                status="VERIFIED",
                file_name="pan_sharma.jpg",
                file_url="https://paytm-saathi.demo/docs/pan_sharma.jpg",
                ocr_quality_flag="CLEAR",
                ocr_candidate_fields='{"pan_number": "AJLPS1928K", "name": "RAMESH SHARMA", "untrusted": true}',
                ocr_confidence=0.98,
                is_ocr_passed=True,
                authorized_verification_status="VERIFIED",
                verified_at=now - timedelta(days=60),
                is_synthetic=True,
                environment="DEMO",
            ),
            MerchantDocument(
                id="doc_sharma_bank",
                tenant_id=tenant.id,
                merchant_id="mer_sharma_kirana",
                document_type="BANK_PROOF",
                status="VERIFIED",
                file_name="cheque_sharma.jpg",
                file_url="https://paytm-saathi.demo/docs/cheque_sharma.jpg",
                ocr_quality_flag="CLEAR",
                ocr_candidate_fields='{"account_no": "910283719283", "ifsc": "PYTM0123456", "untrusted": true}',
                ocr_confidence=0.95,
                is_ocr_passed=True,
                authorized_verification_status="VERIFIED",
                verified_at=now - timedelta(days=60),
                is_synthetic=True,
                environment="DEMO",
            ),
            MerchantDocument(
                id="doc_sharma_photo",
                tenant_id=tenant.id,
                merchant_id="mer_sharma_kirana",
                document_type="SHOP_PHOTO",
                status="VERIFIED",
                file_name="storefront_sharma.jpg",
                file_url="https://paytm-saathi.demo/docs/storefront_sharma.jpg",
                ocr_quality_flag="CLEAR",
                ocr_candidate_fields='{"signboard": "Sharma General Store", "untrusted": true}',
                ocr_confidence=0.94,
                is_ocr_passed=True,
                authorized_verification_status="VERIFIED",
                verified_at=now - timedelta(days=60),
                is_synthetic=True,
                environment="DEMO",
            ),
        ]
        for d in docs_sharma:
            db.add(d)

        # 2. Gupta Electronics (PAN is BLURRY -> Needs PAN Resubmission)
        docs_gupta = [
            MerchantDocument(
                id="doc_gupta_pan",
                tenant_id=tenant.id,
                merchant_id="mer_gupta_electronics",
                document_type="PAN_CARD",
                status="OCR_FAILED",
                file_name="pan_gupta_blurry.jpg",
                file_url="https://paytm-saathi.demo/docs/pan_gupta_blurry.jpg",
                ocr_quality_flag="BLURRY",
                ocr_candidate_fields='{"warning": "LOW_CONFIDENCE_UNTRUSTED", "confidence": 0.45}',
                ocr_confidence=0.45,
                is_ocr_passed=False,
                rejection_reason="Your PAN card photo is blurry and illegible. Please resend a sharp, well-lit photo.",
                authorized_verification_status="PENDING",
                is_synthetic=True,
                environment="DEMO",
            ),
            MerchantDocument(
                id="doc_gupta_bank",
                tenant_id=tenant.id,
                merchant_id="mer_gupta_electronics",
                document_type="BANK_PROOF",
                status="OCR_PASSED",
                file_name="passbook_gupta.jpg",
                file_url="https://paytm-saathi.demo/docs/passbook_gupta.jpg",
                ocr_quality_flag="CLEAR",
                ocr_candidate_fields='{"account_no": "501004819281", "ifsc": "HDFC0001234", "untrusted": true}',
                ocr_confidence=0.94,
                is_ocr_passed=True,
                authorized_verification_status="PENDING",
                is_synthetic=True,
                environment="DEMO",
            ),
            MerchantDocument(
                id="doc_gupta_photo",
                tenant_id=tenant.id,
                merchant_id="mer_gupta_electronics",
                document_type="SHOP_PHOTO",
                status="OCR_PASSED",
                file_name="storefront_gupta.jpg",
                file_url="https://paytm-saathi.demo/docs/storefront_gupta.jpg",
                ocr_quality_flag="CLEAR",
                ocr_candidate_fields='{"signboard": "Gupta Electronics", "untrusted": true}',
                ocr_confidence=0.96,
                is_ocr_passed=True,
                authorized_verification_status="PENDING",
                is_synthetic=True,
                environment="DEMO",
            ),
        ]
        for d in docs_gupta:
            db.add(d)

        # 3. Singh Automobiles (Bank Proof MISSING)
        docs_singh = [
            MerchantDocument(
                id="doc_singh_pan",
                tenant_id=tenant.id,
                merchant_id="mer_singh_automobiles",
                document_type="PAN_CARD",
                status="OCR_PASSED",
                file_name="pan_singh.jpg",
                file_url="https://paytm-saathi.demo/docs/pan_singh.jpg",
                ocr_quality_flag="CLEAR",
                ocr_candidate_fields='{"pan_number": "RAJPS9921K", "name": "RAJESH SINGH", "untrusted": true}',
                ocr_confidence=0.97,
                is_ocr_passed=True,
                authorized_verification_status="PENDING",
                is_synthetic=True,
                environment="DEMO",
            ),
            MerchantDocument(
                id="doc_singh_bank",
                tenant_id=tenant.id,
                merchant_id="mer_singh_automobiles",
                document_type="BANK_PROOF",
                status="MISSING",
                ocr_quality_flag=None,
                ocr_candidate_fields=None,
                is_ocr_passed=False,
                rejection_reason="Cancelled cheque or bank passbook statement is missing.",
                authorized_verification_status="PENDING",
                is_synthetic=True,
                environment="DEMO",
            ),
            MerchantDocument(
                id="doc_singh_photo",
                tenant_id=tenant.id,
                merchant_id="mer_singh_automobiles",
                document_type="SHOP_PHOTO",
                status="OCR_PASSED",
                file_name="storefront_singh.jpg",
                file_url="https://paytm-saathi.demo/docs/storefront_singh.jpg",
                ocr_quality_flag="CLEAR",
                ocr_candidate_fields='{"signboard": "Singh Automobiles & Spares", "untrusted": true}',
                ocr_confidence=0.93,
                is_ocr_passed=True,
                authorized_verification_status="PENDING",
                is_synthetic=True,
                environment="DEMO",
            ),
        ]
        for d in docs_singh:
            db.add(d)

        # 4. Radhe Krishna Bakery (Shop Front Photo MISSING)
        docs_radhe = [
            MerchantDocument(
                id="doc_radhe_pan",
                tenant_id=tenant.id,
                merchant_id="mer_shree_radhe_bakery",
                document_type="PAN_CARD",
                status="OCR_PASSED",
                file_name="pan_radhe.jpg",
                file_url="https://paytm-saathi.demo/docs/pan_radhe.jpg",
                ocr_quality_flag="CLEAR",
                ocr_candidate_fields='{"pan_number": "PRYPS8831A", "name": "PRIYA SHARMA", "untrusted": true}',
                ocr_confidence=0.96,
                is_ocr_passed=True,
                authorized_verification_status="PENDING",
                is_synthetic=True,
                environment="DEMO",
            ),
            MerchantDocument(
                id="doc_radhe_bank",
                tenant_id=tenant.id,
                merchant_id="mer_shree_radhe_bakery",
                document_type="BANK_PROOF",
                status="OCR_PASSED",
                file_name="passbook_radhe.jpg",
                file_url="https://paytm-saathi.demo/docs/passbook_radhe.jpg",
                ocr_quality_flag="CLEAR",
                ocr_candidate_fields='{"account_no": "602100829102", "ifsc": "SBIN0001029", "untrusted": true}',
                ocr_confidence=0.95,
                is_ocr_passed=True,
                authorized_verification_status="PENDING",
                is_synthetic=True,
                environment="DEMO",
            ),
            MerchantDocument(
                id="doc_radhe_photo",
                tenant_id=tenant.id,
                merchant_id="mer_shree_radhe_bakery",
                document_type="SHOP_PHOTO",
                status="MISSING",
                ocr_quality_flag=None,
                ocr_candidate_fields=None,
                is_ocr_passed=False,
                rejection_reason="Shop storefront photo with clear business signboard is missing.",
                authorized_verification_status="PENDING",
                is_synthetic=True,
                environment="DEMO",
            ),
        ]
        for d in docs_radhe:
            db.add(d)

        # 5. Apex Fresh Mart (Full-Pass Candidate: All 3 docs clear, ready for authorized verification step)
        docs_apex = [
            MerchantDocument(
                id="doc_apex_pan",
                tenant_id=tenant.id,
                merchant_id="mer_apex_retail",
                document_type="PAN_CARD",
                status="OCR_PASSED",
                file_name="pan_apex.jpg",
                file_url="https://paytm-saathi.demo/docs/pan_apex.jpg",
                ocr_quality_flag="CLEAR",
                ocr_candidate_fields='{"pan_number": "SNLV99120M", "name": "SUNIL VERMA", "untrusted": true}',
                ocr_confidence=0.98,
                is_ocr_passed=True,
                authorized_verification_status="PENDING",
                is_synthetic=True,
                environment="DEMO",
            ),
            MerchantDocument(
                id="doc_apex_bank",
                tenant_id=tenant.id,
                merchant_id="mer_apex_retail",
                document_type="BANK_PROOF",
                status="OCR_PASSED",
                file_name="passbook_apex.jpg",
                file_url="https://paytm-saathi.demo/docs/passbook_apex.jpg",
                ocr_quality_flag="CLEAR",
                ocr_candidate_fields='{"account_no": "001201928374", "ifsc": "ICIC0000012", "untrusted": true}',
                ocr_confidence=0.97,
                is_ocr_passed=True,
                authorized_verification_status="PENDING",
                is_synthetic=True,
                environment="DEMO",
            ),
            MerchantDocument(
                id="doc_apex_photo",
                tenant_id=tenant.id,
                merchant_id="mer_apex_retail",
                document_type="SHOP_PHOTO",
                status="OCR_PASSED",
                file_name="storefront_apex.jpg",
                file_url="https://paytm-saathi.demo/docs/storefront_apex.jpg",
                ocr_quality_flag="CLEAR",
                ocr_candidate_fields='{"signboard": "Apex Fresh Mart", "untrusted": true}',
                ocr_confidence=0.95,
                is_ocr_passed=True,
                authorized_verification_status="PENDING",
                is_synthetic=True,
                environment="DEMO",
            ),
        ]
        for d in docs_apex:
            db.add(d)

        # Initial audit log
        audit_event = AuditEvent(
            id="audit_initial_seed",
            tenant_id=tenant.id,
            actor="system_seeder",
            action="SEED_DEMO_DATA",
            target="database_tables",
            policy_decision_id="dec_system_seed",
            idempotency_key="idemp_seed_phase5",
            result="SUCCESS",
            is_synthetic=True,
            environment="DEMO",
        )
        db.add(audit_event)

        db.commit()
        print("Demo data successfully seeded with Phase 5 device telemetry.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding demo data: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_demo_data()
