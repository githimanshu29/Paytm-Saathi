# Phase 10: The Vasooli Agent (Receivable Reminders) - Implementation & Architecture

## 1. Architectural Overview
Phase 10 implements **Vasooli**, an autonomous, ethical, and conversational store credit copilot for Paytm merchants. Designed under strict non-coercive boundaries, Vasooli transforms informal paper-based *khata* books into a transparent, digital receivable ledger while protecting customer dignity and adhering strictly to consent guidelines.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        MERCHANT MOBILE APP                             │
│   • Free-text udhaar recording: "Vikram ko ₹850 udhaar diya"          │
│   • Polite reminder approval card with Hindi/English preview           │
│   • Simulated UPI payment link generator                               │
│   • Home screen ledger: Outstanding vs Recovered (₹14,500 vs ₹650)     │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │ REST / Chat API
┌────────────────────────────────────▼───────────────────────────────────┐
│                      VASOOLI SPECIALIST AGENT                          │
│                                                                        │
│   • LangGraph Workflow (Analyzer -> Recorder -> Drafter -> Gate)       │
│   • Anti-Coercion Filter: 14 Banned Phrasing Regex Rules (R4 Block)    │
│   • Consent Verifier: Mandatory customer contact permission gate       │
│   • Dispute Freeze: Auto-pauses reminders on contested bills          │
│   • Auto-Stop Invariant: Authoritative payment cancels pending alerts  │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │ Authoritative DB Checks
┌────────────────────────────────────▼───────────────────────────────────┐
│                    PAYTM SAATHI POSTGRESQL / SQLITE                    │
│   • customers (contact_permission, permission_status)                  │
│   • receivables (status, reminder_count, is_disputed, paid_amount)     │
│   • action_approvals (receivable_id FK, proposal_hash, decision)       │
│   • audit_events (VASOOLI_REMINDER_SENT, VASOOLI_PAYMENT_VERIFIED)     │
└────────────────────────────────────────────────────────────────────────┘
```

## 2. Database Schema Extensions & Migration (`0008`)
The database models in `backend/app/db/models.py` were extended via Alembic migration `0008_add_vasooli_receivables_consent.py`:

1. **`Customer` Model**:
   - `contact_permission`: Boolean flag indicating active messaging authorization.
   - `permission_status`: Granular status (`"ALLOWED"`, `"REVOKED"`, `"OPTED_OUT"`).
   - `permission_updated_at`: Timestamp of latest consent grant or withdrawal.

2. **`Receivable` Model**:
   - `is_disputed`: Boolean flag indicating customer billing dispute.
   - `dispute_reason`: Text explaining customer dispute (e.g., *"Item returned / bill amount mismatch"*).
   - `reminder_count`: Integer tracking outreach attempts (capped at 3).
   - `last_reminder_sent_at`: Timestamp of most recent dispatch.
   - `paid_amount`: Minor units (paise) received toward total.
   - `settled_at`: Timestamp when settlement reached 100%.
   - `settlement_verification_status`: Status enum (`"PENDING"`, `"VERIFIED_PAID"`, `"MANUAL_REVIEW"`).
   - `payment_reference`: Bank/UPI transaction UTR reference code.
   - `payment_link_url`: Simulated digital payment URL.
   - `negotiated_installments`: JSON dictionary storing partial installment schedules.

3. **`ActionApproval` Model**:
   - `receivable_id`: Foreign key link to `receivables.id` enabling automatic lookup and auto-cancellation upon payment arrival.
   - `receivable`: SQLAlchemy relationship mapping `Receivable` $\leftrightarrow$ `ActionApproval`.

## 3. Seeded Test Dataset (`mer_sharma_kirana`)
To rigorously demonstrate the policy gates and edge cases, 5 distinct customer personas were seeded:

| Customer | Phone | Amount | Status | Consent | Dispute | Test Scenario |
|----------|-------|--------|--------|---------|---------|---------------|
| **Vikram Singh** (`cust_vikram_singh`) | `+919811122233` | ₹850 (`85000` paise) | `PENDING` | `ALLOWED` | `False` | Consensual drafting, reminder dispatch, approval gate. |
| **Manish Gupta** (`cust_manish_gupta`) | `+919822233344` | ₹1,200 (`120000` paise) | `PENDING` | `ALLOWED` | `True` (`"Item returned"`) | **Visibly refuses** outreach due to active dispute. |
| **Sunita Devi** (`cust_sunita_devi`) | `+919833344455` | ₹450 (`45000` paise) | `PENDING` | `REVOKED` | `False` | **Visibly refuses** outreach due to revoked contact consent. |
| **Amit Shukla** (`cust_amit_shukla`) | `+919844455566` | ₹2,400 (`240000` paise) | `PENDING` | `ALLOWED` | `False` | 2-part installment split negotiation (₹1,200 x 2). |
| **Deepak Patel** (`cust_deepak_patel`) | `+919855566677` | ₹650 (`65000` paise) | `PAID` | `ALLOWED` | `False` | Seeded verified paid; populates merchant & employee recovered KPI. |

## 4. Policy Guardrails & Anti-Coercion Engine (`MockVasooliAdapter`)
The core domain logic is isolated behind `IVasooliAdapter` in `backend/app/adapters/vasooli.py`:

- **Anti-Coercion String Detection**:
  ```python
  BANNED_PHRASES = [
      "police", "jail", "arrest", "court", "legal notice",
      "threat", "defaulter", "penalty fee", "seize",
      "recovery agent", "blacklisted", "final warning",
      "giraftari", "kanooni karwayi",
  ]
  ```
  Any draft or external text containing these tokens immediately raises `VasooliPolicyViolationError` (`R4_COERCIVE_LANGUAGE_BLOCKED`).
- **Communication Consent Check**:
  Queries customer consent status. If not `ALLOWED`, raises `CommunicationPermissionRevokedError`.
- **Dispute Check**:
  Verifies `is_disputed == False`. If contested, raises `ReceivableDisputedError`.
- **Three-Attempt Outreach Ceiling**:
  Tracks `reminder_count`. If $\ge 3$, blocks further dispatches with error: *"Maximum reminder limit (3 attempts) reached for this receivable."*
- **Polite Template Generator**:
  Generates courteous, culturally respectful reminder drafts:
  > *"Namaste Vikram Singh ji, Sharma Kirana Store ki taraf se vinamra anurodh hai ki aapka ₹850 ka baki hisab purn kar lein. Aasan bhugtan ke liye link: https://paytm.demo/pay/rec_vikram_850"*
- **Authoritative Payment Verification & Auto-Stop**:
  When a webhook or payment event is received with `is_authoritative = True`:
  1. Sets receivable status to `PAID`, `settlement_verification_status = "VERIFIED_PAID"`, and records bank reference.
  2. Queries all pending `ActionApproval` records for this `receivable_id`.
  3. Updates decision to `REJECTED` and appends reason: `"AUTO_CANCELLED: Payment arrived before reminder was sent."`.
  4. Emits `VASOOLI_PAYMENT_VERIFIED` to `audit_events`.

## 5. LangGraph State Machine (`VasooliAgent`)
The agent workflow in `backend/app/agents/vasooli.py` orchestrates merchant intentions across 5 nodes:
- `entry_analyzer`: Classifies user input into `record_udhaar`, `draft_reminder`, `send_reminder`, `negotiate_split`, `record_payment`, or `query`.
- `udhaar_recorder`: Parses free-text store credit transactions and persists new receivables.
- `reminder_drafter`: Evaluates consent and dispute status, applies anti-coercion filtering, creates a demo payment link, and produces an approval card.
- `reminder_sender`: Gated dispatch requiring explicit merchant authorization.
- `split_negotiator`: Calculates integer split installments and builds an `ActionApproval` for merchant sign-off.
- `payment_recorder`: Records authoritative payment arrivals and triggers auto-stop.

## 6. Frontend Experiences

### A. Merchant Mobile (`apps/merchant-mobile`)
- **Natural Language Chat**: Allows kirana owners to record udhaar in Hindi or English (e.g., *"Vikram Singh ko ₹850 udhaar diya"* or *"Vikram ko reminder bhejo"*).
- **Inline Vasooli Approval Card**: Displays polite message preview, customer phone, simulated UPI payment link, anti-coercion disclaimer, and prominent **"Approve & Send Reminder"** button.
- **Visible Refusal Banner**: When a customer has revoked consent or disputed a bill, the card prominently displays a red alert banner stating the refusal reason.
- **Home Screen Udhaar Widget**: Shows live split between Total Outstanding (₹14,500) and Total Recovered (₹650), with real customer records and instant shortcuts to Saathi chat.

### B. Employee Web Control Tower (`apps/employee-web`)
- **6th KPI Card**: Added *"₹ Recovered (Udhaar)"* card to the top-level Control Tower dashboard, showing real verified recovered store credit (`total_vasooli_recovered_formatted`).
- **Dedicated Vasooli Tab (`Coins` icon)**:
  - 5 Status Metric Cards: Total Outstanding, Total Recovered, Consensual Customers, Disputes Paused, Revoked Permissions.
  - Receivables Ledger Table: Real-time display of all customer receivables, contact consent badges, dispute indicators, reminder attempt counts, and settlement states.
  - **Live Demonstration Tool**: *"⚡ Simulate Payment Received"* button sends an authoritative webhook (`POST /demo/vasooli/payment-event`), immediately verifying settlement, auto-cancelling pending approval cards, and incrementing recovered totals without a page reload.

## 7. REST API Endpoints
- `POST /merchant/vasooli/record`: Creates new merchant receivable.
- `POST /merchant/vasooli/draft-reminder`: Drafts polite reminder with consent and dispute pre-checks.
- `POST /merchant/vasooli/send-reminder`: Authorizes and dispatches reminder with idempotency key.
- `POST /merchant/vasooli/negotiate-split`: Creates partial installment split plan and approval request.
- `POST /demo/vasooli/payment-event`: Authoritative payment webhook simulator that executes auto-stop.
- `GET /employee/vasooli/overview`: Backs the employee Control Tower Vasooli console.
