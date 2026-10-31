# Paytm Saathi — End-to-End Demo Script & Presentation Guide

This guide provides step-by-step instructions to showcase all **7 Specialist Agents** and the **Phase 11 Autonomous Multi-Agent Cross-Handoff** in Paytm Saathi across **Merchant Mobile** (`localhost:8081` / Expo) and **Employee Web Control Tower** (`localhost:5173` / Vite).

---

## 🚀 Quick Setup & Service Startup

### 1. Database & Backend
```bash
# In Paytm-Saathi/backend
uv run python scripts/seed_demo_data.py
uv run uvicorn app.main:app --reload --port 8000
```
- **Backend API & Swagger Docs**: `http://localhost:8000/docs`

### 2. Employee Web Portal
```bash
# In Paytm-Saathi/apps/employee-web
pnpm dev
```
- Open `http://localhost:5173` in Chrome/Edge.
- **Login Credentials**:
  - Email: `support@paytm.demo` (or `sales@paytm.demo` / `manager@paytm.demo`)
  - Password: `Demo@1234`

### 3. Merchant Mobile App
```bash
# In Paytm-Saathi/apps/merchant-mobile
pnpm start
# Press 'w' for web browser mode or scan QR in Expo Go app
```
- **Login**:
  - Phone: `9876543210`
  - Demo OTP: `123456`

---

## 🎭 Live Agent Demonstration Scenarios

---

### Demo 1: Resolve Agent (Payment Reversals & Stuck Refund Governance)
*Goal: Prove that PENDING transactions never auto-refund, while stuck bank reversals create structured approval cards.*

1. **Auto-Reversal In-Progress (Branch A)**:
   - In **Merchant Mobile** Chat, type:
     > *"Customer Alok says ₹250 failed, did money get deducted?"*
   - **Observe**:
     - Chip displays `VERIFIED` (#0B8457).
     - Agent explains NPCI U30 24–48 banking hours rule.
     - Warning: *"Do NOT provide goods on credit until status confirms."*

2. **Stuck Bank Reversal (Branch B & R2 Approval Gate)**:
   - In **Merchant Mobile** Chat, type:
     > *"Deepak Verma payment of ₹500 is stuck for 3 days"*
   - **Observe**:
     - Chip displays `AWAITING_APPROVAL` (#B45309).
     - Concrete preview card appears showing UTR `PAYTM_STUCK_881920`, ₹500.00, and explanation: *"Initiating bank review does NOT deduct from your settlement balance."*
     - Click **"Approve Refund Review"**.
     - Status updates instantly to `EXECUTED` (#0077A8).
   - In **Employee Web**, click **Cases & Tasks**:
     - New task appears: *"Refund Review Request: ₹500.00 (PAYTM_STUCK_881920)"*.

---

### Demo 2: Fix Agent (Soundbox Telemetry & Field Service Dispatch)
*Goal: Prove that live device re-checks gate recovery, and unreachable hardware triggers automated technician booking.*

1. **Remote Recovery Re-Check Gate**:
   - In **Merchant Mobile** Chat, type:
     > *"Soundbox SB-JAI-101 is not speaking chime, red light is on"*
   - **Observe**:
     - Remote reboot packet dispatched over-the-air.
     - Live telemetry re-check runs: device remains `OFFLINE`.
     - Agent immediately switches from auto-recovery to **Technician Visit Booked**:
       - Slot: Tomorrow 10:00 AM – 12:00 PM.
       - Case ID: `case_tech_...` with chip `NEEDS_HUMAN` (#DC2626).
   - In **Employee Web**, navigate to **Fix & Devices** tab:
     - View Soundbox `SB-JAI-101` telemetry: Battery 88%, Signal -65 dBm, Status `OFFLINE`.
     - Notice technician visit task logged under `needs_human`.

---

### Demo 3: Reconcile Agent (Settlement Audit & Discrepancy Dispute)
*Goal: Prove that arithmetic is computed in minor units (paise) by code, never by LLM hallucination.*

1. **Daily Settlement Breakdown**:
   - In **Merchant Mobile** Chat, type:
     > *"Why was yesterday's payout short?"*
   - Or in **Employee Web**, open **Reconcile & Settlement** tab:
     - Date: `2026-10-27` (Store: `mer_gupta_electronics` or `mer_verma_sweets`).
     - **Mathematical Breakdown**:
       - Gross Sales: ₹25,000.00 (2,500,000 paise)
       - Refunds: -₹1,500.00
       - MDR Fees: -₹750.00
       - Chargebacks: -₹1,250.00
       - Net Expected: ₹21,500.00 vs Net Settled: ₹19,500.00
       - **Discrepancy**: **-₹2,000.00 (SHORTFALL)**
     - Chip displays `AWAITING_APPROVAL`.
     - Click **"⚡ File Dispute & Escalate"**: creates a high-priority nodal bank investigation task.

---

### Demo 4: Revive Agent (Dormancy Detection & Honest Recovery Tracking)
*Goal: Prove that "Follow-up sent" is never counted as "Merchant revived" without real transaction proof.*

1. **Dormancy Diagnostics**:
   - In **Employee Web**, open **Revive & Retention** tab:
     - Review merchant health table:
       - `Singh Automobiles`: 86% drop (Root Cause: Soundbox Offline).
       - `Verma Sweets`: 79% drop (Root Cause: Settlement Issue).
       - `Sharma Kirana`: 70% drop (Root Cause: Competitor / Disengagement).
2. **Follow-up Sent vs. Verified Revived**:
   - Click **"Send Retention Offer"** on `Sharma Kirana`:
     - Stage updates to `FOLLOWUP_SENT` (Chip: `awaiting_approval`).
     - Revival metric remains `False` (Honest tracking!).
   - In **Merchant Mobile**, open the top notification to view the unlocked Kirana Booster 0% MDR offer.

---

### Demo 5: Onboard Agent (KYC Closer & Untrusted OCR Sandbox)
*Goal: Prove that candidate OCR fields are untrusted, blurry uploads are rejected with specific guidance, and only authorized verification activates merchants.*

1. **Blurry Document Handling**:
   - In **Employee Web**, open **Onboarding Pipeline** tab:
     - Select `Gupta Electronics` (`BLURRY` filter).
     - Click **"Inspect OCR"**:
       - PAN Card: Quality `BLURRY`, Confidence 45%.
       - Specific Reason: *"Your PAN photo is blurry and illegible. Please resend a sharp, well-lit photo."*
2. **Full-Pass Verification Gate**:
   - Switch filter to **"Ready for Verification"** (`Apex Fresh Mart`):
     - PAN, Bank Proof, and Storefront Photo all have green checkmarks.
     - Click **"⚡ Verify & Activate"**:
       - Calls simulated authorized verification system.
       - Status transitions to `ACTIVE / VERIFIED` (Chip: `verified`).

---

### Demo 6: FieldMate Agent (Sales Rep Route & CRM Review Gate)
*Goal: Prove that sales briefs are evidence-backed, routes are prioritized by revenue impact, and voice notes require rep confirmation.*

1. **Prioritized Daily Route**:
   - In **Employee Web**, log in as `sales@paytm.demo` (or switch to **Field Sales Copilot** tab):
     - View prioritized merchant visit queue:
       1. `Singh Automobiles` (3.3 km) — *"Soundbox offline 3 days & bank proof missing — fix hardware & collect cheque."*
       2. `Gupta Electronics` (2.8 km) — *"PAN photo blurry — collect physical PAN card."*
       3. `Radhe Krishna Bakery` (1.5 km) — *"Shop photo missing & sales down 70%."*
2. **Voice Note Confirmation Gate**:
   - Click **"Dictate / Play Voice Note"** on `Singh Automobiles`:
     - Listen/view transcription: *"Spoke with Rajesh ji, adapter replaced, Soundbox powered on."*
     - Candidate extracted fields shown in **DRAFT** status (zero CRM write).
     - Click **"Confirm & Save to CRM"**:
       - Version increments from 1 to 2.
       - Record marked `CONFIRMED` and persisted in CRM.

---

### Demo 7: Vasooli Agent (Consensual Udhaar Reminders)
*Goal: Prove that Vasooli respects customer consent, strictly halts on disputes/revocations, and auto-stops upon payment.*

1. **Permission Check & Polite Reminders**:
   - In **Merchant Mobile**, scroll to **Customer Udhaar (Dues)**:
     - Tap **Vikram Singh** (₹850.00, Consent: `ALLOWED`):
       - Polite bilingual WhatsApp message previewed (Zero threats, zero legal shaming).
       - Tap **"Approve & Send Reminder"**.
       - Reminder counter increments (1/3).
2. **Revocation & Dispute Boundaries**:
   - Tap **Sunita Devi** (₹1,400.00, Consent: `REVOKED`):
     - Card displays: *"Outreach Refused: Customer has revoked contact permission."* Button is disabled.
   - Tap **Manish Gupta** (₹420.00, Dispute: `ACTIVE`):
     - Card displays: *"Outreach Refused: Active dispute reported on goods received."*
3. **Authoritative Auto-Stop**:
   - In **Employee Web** under **Vasooli Receivables**, click **"⚡ Simulate Payment Received"** on Vikram Singh:
     - Payment recorded as `VERIFIED_PAID`.
     - In **Merchant Mobile**, reminder card instantly disappears with status updated to `Auto-Stopped`.

---

### Demo 8: Multi-Agent Cross-Handoff Demo (The Masterpiece)
*Goal: Demonstrate autonomous handoffs across Revive ➔ Fix ➔ FieldMate ➔ Revive without human coordination.*

1. In **Employee Web**, open the **Multi-Agent Handoff** tab.
2. Click **"⚡ Run Full 6-Step Chain"**:
   - **Step 1 (Revive)**: Scans APScheduler metrics ➔ Flags `Singh Automobiles` (-86% drop).
   - **Step 2 (Revive ➔ Fix)**: Detects hardware cause ➔ Hands off telemetry to Fix Agent.
   - **Step 3 (Fix)**: Dispatches remote reboot ➔ Live re-check confirms device is still offline.
   - **Step 4 (Fix ➔ FieldMate)**: Books technician slot ➔ Injects urgent stop into Field Sales route.
   - **Step 5 (FieldMate)**: Rep replaces adapter on-site ➔ Device comes ONLINE (Battery 95%).
   - **Step 6 (FieldMate ➔ Revive)**: Revive verifies fresh volume recovery (₹17,500/day) ➔ Marks merchant `RECOVERING`.
3. Scroll down to the **Handoff Audit Trail Timeline**:
   - Live stream sourced directly from SQLite `audit_events` with color-coded actor badges.

---

## 🛡️ Security & Invariance Verification Summary

| Invariant | Protection Mechanism | Test Result |
|---|---|:---:|
| **Pending Reversals** | R3 Direct refund locked; 24-48h SLA enforced | ✅ Verified |
| **Fix Hardware Gate** | Authoritative telemetry re-check required before "fixed" claim | ✅ Verified |
| **Settlement Math** | Integer minor unit (paise) arithmetic in code; zero LLM math | ✅ Verified |
| **Honest Revival** | Separate tracking for followup sent vs. verified volume recovery | ✅ Verified |
| **KYC / OCR Gate** | Candidate OCR fields untrusted; authorized verification step required | ✅ Verified |
| **CRM Voice Notes** | Draft state requires explicit rep review and confirmation | ✅ Verified |
| **Udhaar Governance** | Anti-coercion regex; hard block on revoked consent or active disputes | ✅ Verified |
| **Idempotency** | SHA-256 parameter hash prevents duplicate side-effects | ✅ Verified |
| **Bounded Loops** | Max 12 tools / 5 planner loops; ceiling breaches escalate to human review | ✅ Verified |
| **Prompt Injection** | Adversarial chat prompts route to `NEEDS_HUMAN` without tool execution | ✅ Verified |
| **Simulated Markers** | All demo side-effects clearly labeled `SIMULATED` / `DEMO` | ✅ Verified |
