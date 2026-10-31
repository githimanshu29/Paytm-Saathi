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

### Demo 1: Resolve Agent (Payment Reversals, Dispute Hub & Stuck Refund Governance)
*Goal: Prove that PENDING transactions never auto-refund, stuck bank reversals create structured approval cards, and merchants receive instant advisory clarity.*

1. **Dispute Overview Hub (Interactive Investigation Queue)**:
   - In **Merchant Mobile** Chat, type:
     > *"Show me all failed payments today"*
   - **Observe**:
     - Chip displays `VERIFIED` (#0B8457).
     - Renders interactive `RESOLVE_DISPUTE_CARD` featuring a 4-pill metric summary (Auto-Reversing, Stuck Reversals, Confirmed, Security Holds).
     - Live queue listing Alok Gupta (₹250), Deepak Verma (₹500), Pooja Chawla (₹320), and Fraud Check (₹1,200).
     - Provides 1-tap quick action buttons for instant follow-up queries.

2. **Auto-Reversal In-Progress (Branch A) & Merchant Advisory**:
   - In **Merchant Mobile** Chat, type:
     > *"Customer Alok says ₹250 failed, did money get deducted?"*
   - **Observe**:
     - Chip displays `VERIFIED` (#0B8457).
     - Agent explains NPCI U30 24–48 banking hours rule.
     - Warning: *"Do NOT provide goods on credit until status confirms."*
   - Follow-up conversational question:
     > *"Should I give goods to Alok?"*
   - **Observe**:
     - Saathi directly and authoritatively advises: *"No, do NOT provide goods on credit! The payment is still with the remitter bank and will auto-reverse."*

3. **Stuck Bank Reversal (Branch B & R2 Approval Gate)**:
   - In **Merchant Mobile** Chat, type:
     > *"Deepak Verma payment of ₹500 is stuck for 3 days"*
   - **Observe**:
     - Chip displays `AWAITING_APPROVAL` (#B45309).
     - Concrete preview card appears showing UTR `PAYTM_STUCK_881920`, ₹500.00, and explanation: *"Initiating bank review does NOT deduct from your settlement balance."*
   - Merchant question:
     > *"Will refund review deduct from my settlement balance?"*
   - **Observe**:
     - Saathi clearly reassures: *"No! Authorizing this review does NOT deduct from your settlement balance. It queues an operations investigation with the remitter bank."*
   - Click **"Approve Refund Review"**.
   - **Observe**:
     - Status updates instantly to `EXECUTED` (#0077A8).
   - In **Employee Web**, click **Cases & Tasks**:
     - New task appears: *"Refund Review Request: ₹500.00 (PAYTM_STUCK_881920)"*.

4. **Payment Confirmed & Goods Release (Branch C)**:
   - In **Merchant Mobile** Chat, type:
     > *"Customer Pooja says ₹320 was debited but Soundbox did not speak, did it go through?"*
   - **Observe**:
     - Saathi verifies UTR `PAYTM_SUCCESS_991823`, confirms the payment was **SUCCESSFUL** and credited to the Paytm settlement balance.
     - Merchant follow-up:
       > *"Can I release goods to Pooja?"*
     - Saathi answers: *"Yes, absolutely! You can safely release the goods to Pooja Chawla."*

---

### Demo 2: Fix Agent (Soundbox Telemetry, Guided Self-Checks & Technician Dispatch)
*Goal: Prove that Saathi acts as a real problem-solver by guiding merchants through self-checks first to prevent unnecessary technician visits, and coordinates authoritative field dispatch when hardware truly fails.*

1. **Step-by-Step Guided Self-Checks in Chat (End-to-End Simulation)**:
   - In **Merchant Mobile** Chat, type:
     > *"Mera soundbox kaam nahi kar raha, koi awaz nahi aayi"* (or *"Soundbox speaker is silent"*).
   - **Observe**:
     - Saathi checks live telemetry from database (Battery: 88%, Signal: GOOD, 4G Pro).
     - Saathi greets the shopkeeper warmly and starts **Step 1: Volume Replay Test**:
       - Explains: *"Technician bulane se pehle aksar volume mute hone se issue hota hai. Kripya '+' button ko 2 second tak dabakar rakhein."*
       - Renders **Step 1 Action Card** with interactive buttons:
         - `[🔊 Haan, Awaaz Aa Gayi]`
         - `[❌ Nahi, Awaaz Nahi Aayi]`

2. **Advancing to Step 2 (Power Cycle & Cable Inspection)**:
   - Click **`[❌ Nahi, Awaaz Nahi Aayi]`** (or type *"Maine '+' button dabaya par awaz nahi aayi"*).
   - **Observe**:
     - System dispatches an OTA Remote Network Reset packet (real Command ID).
     - Instructs **Step 2: Power Cycle**:
       - *"Soundbox ko peeche se 10 second OFF karke ON karein aur orange charger check karein. LED light ka color dekhein."*
       - Renders **Step 2 Action Card** with interactive buttons:
         - `[🟢 Green Light Ho Gayi (Chal Gaya)]`
         - `[🔴 Abhi Bhi Red Hai / Chup Hai]`

3. **Field Technician Dispatch (When Self-Checks Exhausted)**:
   - Click **`[🔴 Abhi Bhi Red Hai / Chup Hai]`** (or type *"Switch off on kiya par abhi bhi red light hai"*).
   - **Observe**:
     - System re-checks live telemetry; device remains unreachable.
     - Saathi immediately books an authorized Field Service Technician:
       - Slot: `Tomorrow 10:00 AM – 12:00 PM`.
       - Case ID: `#case_tech_...` with chip `NEEDS_HUMAN` (#DC2626).
       - Zero-cost SLA replacement guarantee.
     - In **Employee Web**, open **Fix (Devices/Soundbox)** or **Control Tower**:
       - Notice the new task logged in real time with technician slot and audit log trail!

4. **Live Case Tracking & Reassurance**:
   - In chat, ask: *"Mera technician kab aayega?"*
   - Saathi retrieves the scheduled visit, reminds merchant of the exact slot and Case ID, and stays available.

5. **Instant Resolution Confirmation (If Succeeded at Any Step)**:
   - If merchant clicks `[🔊 Haan, Awaaz Aa Gayi]` or `[🟢 Green Light Ho Gayi]`:
   - Saathi verifies live telemetry, marks device as verified ONLINE in DB, and offers collection/khata tools.

---

### Demo 3: Reconcile Agent (Settlement Audit, Fee Explanation & Discrepancy Dispute)
*Goal: Prove that arithmetic is computed in minor units (paise) by code (never LLM hallucination), fee deductions are fully explained, and merchants receive instant advisory clarity.*

1. **Daily Settlement Breakdown (Yesterday / Normal Day)**:
   - In **Merchant Mobile** Chat, type:
     > *"Show settlement breakdown for yesterday"* (or *"Kal ka settlement kitna aaya?"*)
   - **Observe**:
     - Chip displays `VERIFIED` (#0B8457).
     - Renders interactive `SETTLEMENT_BREAKDOWN` card: Gross Sales (₹10,000.00), Refunds (-₹500.00), Fees (-₹300.00), Net Settled (₹9,200.00, Bank UTR: `ICICINODAL99281028`).
     - Agent confirms: *"Settlement for 2026-10-28 reconciles completely to your bank account."*
     - Card features verified service charges and 1-tap quick action buttons.

2. **Fee Explanation & Service Charges**:
   - In **Merchant Mobile** Chat, type:
     > *"Meri fees kyu kati?"* (or *"Why was ₹300 fee deducted?"*)
   - **Observe**:
     - Saathi breaks down the exact ₹300 deduction:
       - **₹250.00**: Soundbox 4G Pro Monthly Subscription (device maintenance, speaker warranty, unlimited 4G SIM).
       - **₹50.00**: Commercial MDR (0.5% gateway fee).
     - Reassures merchant that standard customer UPI payments have **0% MDR**.

3. **Automated Payout Timing & Schedule Advisory**:
   - In **Merchant Mobile** Chat, type:
     > *"When will today's settlement hit my bank account?"* (or *"Settlement kab aayega?"*)
   - **Observe**:
     - Saathi explains the daily schedule: **7:00 AM every morning (T+1 schedule)** directly via ICICI Nodal payout.
     - Explains that today's collections settle tomorrow at 7:00 AM, and points to the 0-fee **Instant Settlement** feature for immediate daytime funds.

4. **Multi-Day Discrepancy Health Scan & Dispute Case (Anomalous Day)**:
   - In **Merchant Mobile** Chat, type:
     > *"Check all my settlements for discrepancy"* (or *"Kahi koi shortfall hai kya?"*)
   - **Observe**:
     - Saathi audits all recent settlements:
       - **28 Oct**: ₹9,200.00 (Reconciled completely).
       - **27 Oct**: Unexplained shortfall of **₹1,200.00** detected (Calculated Net: ₹13,000.00 vs Bank Deposit: ₹11,800.00).
     - Priority dispute review case (Case ID: `#case_disp_...`) is actively queued with Nodal Settlement Operations.
     - Renders `SETTLEMENT_BREAKDOWN` with chip `NEEDS_HUMAN` and 1-tap action button: **"📷 Attach Passbook / Statement Proof"**.
     - Click **"📷 Attach Passbook / Statement Proof"** &mdash; updates to confirmed proof attached.
   - In **Employee Web**, open **Cases & Tasks**:
     - Verify the settlement dispute case is visible in `needs_human` bucket with full audit trail!

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

### Demo 7: Vasooli Agent (Consensual Store Credit / Udhaar Management)
*Goal: Prove that Vasooli provides end-to-end conversational store credit management directly from chat with complete context, top debtor prioritization, anti-coercion policies, and 1-tap interactive action cards.*

1. **Complete Ledger & Top Debtor Discovery**:
   - In **Merchant Mobile** Chat, type:
     > *"give me all details about my udhar"* or *"who owes the most udhar?"*
   - **Observe**:
     - Vasooli Agent responds with natural bilingual intelligence:
       - Total Outstanding: **₹4,000.00** across 4 active accounts; **₹650.00** recovered today.
       - Identifies **#1 Top Debtor: Amit Shukla** (₹1,500.00) and advises a 3-month split plan (₹500/mo).
       - Details all customer statuses (Vikram Singh consensual, Manish Gupta dispute hold, Sunita Devi in-store only).
     - Renders an interactive **`VASOOLI_LEDGER_CARD`** with metrics, status chips, and 1-tap quick action buttons.

2. **Customer Balance Inquiry with Instant Action**:
   - Type in chat:
     > *"Vikram ka udhare kitna hai ??"*
   - **Observe**:
     - Agent matches Vikram Singh, explains the exact balance of **₹850.00** for *"Aata bag and spices bought on credit"*, and confirms consensual contact status (`ALLOWED`).
     - Directly embeds the **`VASOOLI_REMINDER_CARD`** in chat with a polite Hindi SMS/WhatsApp preview and a secure Paytm UPI link.

3. **1-Tap Approval & Reminder Delivery**:
   - In chat or via quick option, type:
     > *"Vikram ko polite reminder bhejo udhari chukane k lie"*
   - **Observe**:
     - Card displays status: `Approval Required` with button **[📤 Approve & Send Reminder]**.
     - Tap **"Approve & Send Reminder"**:
       - Card transitions to `✓ Respectful reminder sent via SMS/WhatsApp. Auto-stop active on UPI arrival.`
       - Reminder counter increments to 1/3, and an immutable audit event is logged.

4. **Regulatory Boundaries (Revocation & Dispute Guards)**:
   - Type in chat:
     > *"Sunita Devi ko reminder bhejo"*
   - **Observe**:
     - Policy Refusal: *"Outreach Refused by Policy: Customer Sunita Devi has revoked contact permission (Status: REVOKED). In-store collection recommended."*
   - Type in chat:
     > *"Manish Gupta ko reminder bhejo"*
   - **Observe**:
     - Policy Pause: *"Outreach Refused by Policy: Receivable is currently disputed by the customer (Basmati rice 2 bags on credit). Vasooli suspends all reminders until discrepancy is resolved."*

5. **Authoritative Auto-Stop on UPI Settlement**:
   - In **Employee Web** under **Vasooli Receivables**, click **"⚡ Simulate Payment Received"** on Vikram Singh:
     - Payment recorded as `VERIFIED_PAID`.
     - Reminders auto-stopped and any pending approval cards are automatically cancelled.

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
