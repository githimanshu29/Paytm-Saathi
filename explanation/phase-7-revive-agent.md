# Phase 7: Technical Explanation (The Revive Agent — Dormant Merchant Reactivation)

### 1. Overview & System Mission
Phase 7 delivers **The Revive Agent**, the fourth specialist agent in Paytm Saathi. Its mission is **proactive, honest dormant merchant reactivation**.

Rather than waiting for a small kirana owner to complain or churn silently to a competitor QR, the Revive Agent:
1. Runs background scheduled scans using APScheduler and deterministic Python math (never LLM guesses) to compute comparable-period volume declines against seeded baseline metrics.
2. Automatically flags kiranas experiencing a $\ge 40\%$ drop in transaction volume.
3. Reuses existing adapters (`DeviceAdapter` from Phase 5, `SettlementAdapter` from Phase 6) to diagnose the genuine root cause across three realistic branches:
   - **Branch 1: Technical Device Issue**: Offline or degraded Soundbox telemetry $\to$ hands off evidence to the **Fix Agent**.
   - **Branch 2: Technical Settlement Issue**: Unresolved payout shortfalls or chargebacks $\to$ hands off evidence to the **Reconcile Agent**.
   - **Branch 3: Pure Commercial Disengagement / Competitor**: Hardware and settlements verified healthy $\to$ dispatches a policy-gated **Kirana Booster (0% MDR for 30 Days)** retention offer.
4. If the merchant accepts the offer, creates a warm-lead field visit task assigned to Sales Rep **Amit V.**.
5. **The Honest Tracking Invariant**: A merchant is NEVER declared revived at the moment an offer is sent or accepted. Only when a subsequent metrics recheck demonstrates actual counter volume recovery ($\ge 80\%$ of baseline) does the status transition to `REVIVED`.

---

### 2. Architecture & Data Flow

```
                  ┌─────────────────────────────────────────────────────────┐
                  │  APScheduler Background Scan / Manual Trigger Endpoint  │
                  │              (POST /employee/revive/scan)               │
                  └────────────────────────────┬────────────────────────────┘
                                               │
                                               ▼
                              ReviveAgent: LangGraph StateGraph
                    ┌─────────────────────────────────────────────────────┐
                    │  scan_and_compute_decline  (≥40% drop threshold)    │
                    └──────────────────────────┬──────────────────────────┘
                                               │
                                               ▼
                                      diagnose_root_cause
                         ┌─────────────────────┴─────────────────────┐
                         ▼                                           ▼
                 MockDeviceAdapter                         MockSettlementAdapter
               (Offline SB-DEL-404?)                       (ICICI Shortfall -₹940?)
                         │                                           │
         ┌───────────────┴───────────────┐           ┌───────────────┴───────────────┐
      [Offline]                       [Online]    [Discrepancy]                   [Clean]
         │                               │           │                               │
         ▼                               └─────┬─────┘                               ▼
     Branch 1:                                 │                                 Branch 3:
   DEVICE_ISSUE                                │                       COMPETITOR_OR_DISENGAGEMENT
   Evidence Handoff                            │                       PolicyEngine Gated Offer:
   to FIX Agent                                │                       Kirana Booster (BOOSTER30)
                                               ▼                                     │
                                           Branch 2:                                 ▼
                                       SETTLEMENT_ISSUE                  Merchant Mobile App:
                                       Evidence Handoff                  [Accept]      [Dismiss]
                                       to RECONCILE Agent                    │
                                                                             ▼
                                                                     Creates Warm-Lead Task
                                                                     Assigned to Sales Rep (Amit V.)
                                                                             │
                                                                             ▼
                                                                  [Stage: WARM_LEAD (NOT REVIVED)]
                                                                             │
                                                                             ▼
                                                                  Subsequent Volume Recheck:
                                                                  Real volume ≥ 80% baseline?
                                                                      ├── NO  ──▶ Retains WARM_LEAD
                                                                      └── YES ──▶ Flips to REVIVED!
```

---

### 3. Database Schema Models (`backend/app/db/models.py`)

1. **`merchant_activity_metrics`**:
   - `merchant_id`: Foreign key linked to `merchants.id`.
   - `baseline_daily_tx_count`: Baseline normal daily transactions (e.g. 35 tx/day).
   - `baseline_daily_volume_paise`: Baseline normal daily volume in paise (e.g. ₹9,500 = 950,000 paise).
   - `recent_daily_tx_count`: Recent evaluated daily count.
   - `recent_daily_volume_paise`: Recent evaluated daily volume in paise.
   - `drop_percentage`: Deterministic integer decline percentage: $\text{int}\left(\frac{\text{baseline} - \text{recent}}{\text{baseline}} \times 100\right)$.
   - `health_status`: `HEALTHY`, `AT_RISK`, `DORMANT`.
   - `diagnosed_cause`: `DEVICE_ISSUE`, `SETTLEMENT_ISSUE`, `COMPETITOR_OR_DISENGAGEMENT`.
   - `revival_stage`: `AT_RISK`, `FOLLOWUP_SENT`, `WARM_LEAD`, `REVIVED`.
   - `last_scanned_at`: UTC timestamp of latest dormancy scan.
   - `recovered_at`: Nullable UTC timestamp set ONLY when volume recovery is verified.

2. **`merchant_followups`**:
   - `id`: Primary key (`fol_...`).
   - `merchant_id`: Linked merchant.
   - `cause_type`: Root cause enum string.
   - `message_title`, `message_body`: Notification content rendered in merchant mobile app.
   - `offer_code`, `offer_details`: Authorized incentive parameters.
   - `status`: `DELIVERED`, `ACCEPTED`, `DISMISSED`.
   - `handed_off_to`: Target specialist agent (`FIX` or `RECONCILE`).
   - `task_id`: Linked task if converted to sales rep lead.
   - `delivered_at`, `responded_at`: Real-time audit timestamps.

---

### 4. Seeded Scenario Demonstration Kiranas

| Merchant | City | Baseline / Day | Recent / Day | Drop % | Diagnosed Cause | Handoff / Offer | Initial Revival Stage |
|---|---|---|---|---|---|---|---|
| **Gupta Electronics** (`mer_gupta_electronics`) | Delhi | ₹20,000 | ₹1,600 | **-92%** | `DEVICE_ISSUE` | Handoff to **Fix Agent** (`SB-DEL-404 OFFLINE`) | `AT_RISK` (`needs_human`) |
| **Verma Sweets** (`mer_verma_sweets`) | Kanpur | ₹12,000 | ₹2,500 | **-79%** | `SETTLEMENT_ISSUE` | Handoff to **Reconcile Agent** (ICICI shortfall -₹940) | `AT_RISK` (`needs_human`) |
| **Sharma General Store** (`mer_sharma_kirana`) | Jaipur | ₹9,500 | ₹2,850 | **-70%** | `COMPETITOR_OR_DISENGAGEMENT` | **Kirana Booster 0% MDR** (Gated Policy Offer) | `FOLLOWUP_SENT` (`pending`) |

---

### 5. UI Integration

1. **Merchant Mobile (`apps/merchant-mobile/App.tsx`)**:
   - **Home Tab Check-in Banner**: When an active follow-up exists, renders a prominent Kirana Booster banner with offer terms, "Accept Offer", and "Dismiss".
   - **Saathi Chat Tab Integration**: Chat responds to natural language dormancy queries (e.g., *"Why is my volume down? Can Paytm help me revive sales?"*), returns audio playback via `speech_audio_base64`, and renders an interactive inline check-in card.
   - **Quick Scenario Chip**: Added `🌟 Kirana Booster Growth Offer (Revive)` quick pill.

2. **Employee Web Dashboard (`apps/employee-web/src/App.tsx`)**:
   - **Revive Navigation Tab**: Selecting `Revive (Dormant)` renders the dedicated **Merchant Health & Dormancy Recovery** control tower:
     - **Top KPI Cards**: Real counts for *At-Risk Kiranas*, *Causes Diagnosed*, *Follow-ups Sent*, *Warm Leads Queued*, and *Verified Revived*.
     - **Manual Scan Trigger**: "Run Dormancy Scan Now" button calling `POST /employee/revive/scan`.
     - **Filter Bar**: Quick filters for *All At-Risk*, *Warm Leads (Sales Rep)*, *Device Issues*, *Settlement Issues*, *Kirana Booster*, and *Revived*.
     - **At-Risk Kiranas Table**: Real-time decline metrics, drop badges, diagnosed root causes, StatusChips, and active follow-up summaries.
     - **⚡ Simulate Recovery Action**: Interactive button for reviewers to simulate fresh volume and immediately observe the honest revival invariant in real time.
