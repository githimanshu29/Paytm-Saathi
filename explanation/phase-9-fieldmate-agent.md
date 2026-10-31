# Phase 9: The FieldMate Agent (Field Sales Copilot) - Implementation & Architecture

## 1. Architectural Overview
Phase 9 delivers **FieldMate**, an autonomous and risk-tiered copilot assisting Paytm field sales representatives on their merchant beat. It connects real hardware telemetry (Fix), settlement status (Reconcile), dormancy recovery metrics (Revive), and KYC documentation states (Onboard) into actionable, truthful sales intelligence.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        EMPLOYEE CONTROL TOWER                          │
│                                                                        │
│   [ 🚗 Sales Rep View: Amit V. ]       [ 📊 Manager EOD View: Pooja M. ]│
│   • Prioritized Jaipur Route Stops     • Route Completion Rate %       │
│   • Evidence-Backed Briefs             • Confirmed Visit Notes Log     │
│   • Voice Note Recording & Review      • Qualified Leads Tally         │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │ REST APIs / JWT Auth
┌────────────────────────────────────▼───────────────────────────────────┐
│                      FIELDMATE SPECIALIST AGENT                        │
│                                                                        │
│   • LangGraph Workflow (RoutePlanner -> BriefGen -> Extractor -> Gate) │
│   • Haversine Distance Heuristics (MI Road Hub to Merchants)           │
│   • Voice Note NLP Structuring (Candidate Extraction)                  │
│   • Optimistic Concurrency Engine (Version Counter)                    │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │ Authoritative DB Checks
┌────────────────────────────────────▼───────────────────────────────────┐
│                    PAYTM SAATHI POSTGRESQL / SQLITE                    │
│   • merchant_visits (version, status, brief, notes, is_confirmed)      │
│   • devices (telemetry: battery, status)                               │
│   • merchant_documents (status: MISSING, BLURRY, VERIFIED)             │
│   • merchant_activity_metrics (drop_percentage, diagnosed_cause)       │
│   • audit_events (action: CRM_VISIT_NOTE_SAVED, CREATE_SALES_LEAD)     │
└────────────────────────────────────────────────────────────────────────┘
```

## 2. Seeded Jaipur Territory & Entities
Five real merchants assigned to `emp_sales_01` (Amit Verma, Sales Rep) around the MI Road hub (`26.9150° N, 75.8150° E`):

1. **Singh Automobiles & Spares** (`mer_singh_automobiles`, Transport Nagar - 3.3 km):
   - Telemetry: Soundbox offline 3 days (12% battery) + missing `BANK_PROOF`.
   - Brief: *"Soundbox offline (12% battery) & BANK_PROOF missing — replace adapter, collect physical cheque."*
   - Priority: `HIGH`.
2. **Gupta Electronics** (`mer_gupta_electronics`, Raja Park - 2.8 km):
   - Telemetry: PAN card photo is `BLURRY` (45% confidence).
   - Brief: *"PAN_CARD photo is blurry — collect physical paper copy for re-verification."*
   - Priority: `HIGH`.
3. **Radhe Krishna Bakery** (`mer_shree_radhe_bakery`, C-Scheme - 1.5 km):
   - Telemetry: `SHOP_PHOTO` missing.
   - Brief: *"SHOP_PHOTO is missing — collect physical photo/copy to complete onboarding."*
   - Priority: `MEDIUM`.
4. **Apex Fresh Mart** (`mer_apex_retail`, Vaishali Nagar - 7.4 km):
   - Telemetry: All 3 KYC documents passed OCR (`is_ocr_passed=True`).
   - Brief: *"All KYC docs passed OCR — perform physical store check and signboard confirmation."*
   - Priority: `LOW`.
5. **Sharma Kirana Store** (`mer_sharma_kirana`, Johari Bazaar - 1.1 km):
   - Telemetry: Sales dropped 70% in baseline scan / high loan potential. Seeded as `COMPLETED` visit.
   - Brief: *"Sales dropped 70% (COMPETITOR_OR_DISENGAGEMENT) — check competitor presence, pitch Kirana Booster offer."*
   - Confirmed note: Met Ramesh ji in person. Pitched ₹50,000 Merchant Loan at 1.2% monthly.

## 3. Allowed Risk-Tiered Toolset (`FieldMateTools`)
- `get_assigned_merchants` (R0): Read-only listing of assigned visits with coordinates and distance.
- `get_merchant_brief` (R0): Real-time derivation of talking points, pitch, and evidence breakdown from DB state.
- `suggest_visit_order` (R0): Heuristic priority sort (HIGH urgency first, then ascending distance).
- `create_visit_task` (R1): Internal task creation for technician or follow-up check.
- `save_structured_visit_note` (R1): Confirms note with optimistic lock check and policy gating.
- `create_sales_lead` (R1): Creates warm lead in CRM for loan or Soundbox upsell.

## 4. Policy Guardrails & Enforced Disallowed Actions
1. **No Fabricated Travel Times**: Haversine distance is calculated deterministically; no simulated traffic delays or fake ETA minutes are generated.
2. **Rep Boundary Isolation**: Reps cannot read or update visits for merchants assigned to another representative (`sales_rep_id != user.sub` $\to$ 403 Forbidden).
3. **No Loan Auto-Approvals**: Any draft or note committing to loan approval, sanction, or credit guarantee is blocked with `POLICY_VIOLATION`.
4. **No Inferred Consent**: Express interest leads to follow-up tasks, never binding enrollment.
5. **Mandatory Confirmation Gate**: Zero unconfirmed persistence. Voice notes are extracted into candidate fields with `requires_rep_confirmation = True`. CRM writes only occur on explicit rep confirmation.

## 5. Optimistic Concurrency Control
- Added `version` column to `MerchantVisit`.
- When confirming, client passes `expected_version`.
- If `visit.version != expected_version`, adapter raises `ConcurrencyConflictError` and API returns `HTTP 409 Conflict`.
- Prevents concurrent field updates from silently wiping previous notes.

## 6. Frontend Implementation (`apps/employee-web`)
- Integrated in the `FieldMate (Sales Copilot)` tab.
- Includes a **Persona Switcher** allowing instant switching between:
  - **Field Rep Route Console**: Shows planned order, live distance, evidence-backed brief, quick phone dialer, brief viewer, and voice note recording modal.
  - **Manager End-of-Day Summary**: Shows KPI cards (assigned, completed, rate %, leads), territory rep card, and authoritative table of confirmed visits with version numbers.
- **Voice Note Modal**: Provides rapid text/voice entry, candidate draft extraction, explicit warning that AI draft is unpersisted, editable confirmed notes, lead interest selector, and 409 conflict alert.
