# Phase 8: The Onboard Agent (KYC Closer & Document Verification) — Technical Implementation

## 1. Architectural Overview
Phase 8 introduces **Onboard**, the fifth specialist agent in the Paytm Saathi monorepo. It autonomously guides merchants through incomplete signups, inspects uploaded identity and business proofs via a deterministic mock OCR adapter, rejects defective uploads with exact actionable feedback, and gates merchant activation behind an authorized external verification engine.

```
Merchant App / Chat ──────► Saathi Brain Orchestrator
                                  │
                                  ▼
                            [Onboard Agent]
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
  [Inspect Checklist]     [Chase Missing Doc]    [Authorized Verification Gate]
  - Missing Items         - Blurry PAN Guidance   - Simulated NSDL Check
  - Blurry Filter         - Missing Bank Proof    - Bank Penny-Drop
  - Untrusted OCR         - Action Card Dispatch  - Transitions to ACTIVE & VERIFIED
```

## 2. Key Components Built

### 2.1 Database Schema & Migration (`0006_add_onboarding_and_kyc_documents.py`)
- **`MerchantDocument` Model**:
  - `document_type`: Enum string (`PAN_CARD`, `BANK_PROOF`, `SHOP_PHOTO`)
  - `status`: Lifecycle status (`MISSING`, `OCR_PASSED`, `OCR_FAILED`, `VERIFIED`)
  - `ocr_quality_flag`: Image quality evaluation (`CLEAR`, `BLURRY`, `CROPPED`, `GLARE`)
  - `ocr_candidate_fields`: JSON storage of candidate fields marked explicitly `untrusted: True`
  - `is_ocr_passed`: Boolean flag from OCR layer (insufficient for activation on its own)
  - `rejection_reason`: Actionable, specific feedback on why document failed
  - `authorized_verification_status`: Status from external verification engine (`PENDING`, `VERIFIED`, `REJECTED`)

### 2.2 Seeded Merchant Application Scenarios
1. **Gupta Electronics (`mer_gupta_electronics`)**: PAN card photo is `BLURRY` (`OCR_FAILED`), Bank Proof & Shop Photo passed OCR.
2. **Singh Automobiles (`mer_singh_automobiles`)**: Bank Proof is `MISSING`, PAN & Shop Photo passed OCR.
3. **Shree Radhe Bakery (`mer_shree_radhe_bakery`)**: Shop storefront photo is `MISSING`, PAN & Bank Proof passed OCR.
4. **Apex Retail (`mer_apex_retail`)**: Full-pass candidate where all 3 documents passed OCR, ready for simulated authorized verification.
5. **Sharma Kirana (`mer_sharma_kirana`)**: Fully verified baseline.

### 2.3 Deterministic Mock OCR & KYC Adapter (`MockOnboardAdapter`)
- `extract_document_fields()`: Extracts candidate fields (`candidate_pan`, `candidate_name`, `confidence`) with explicit notice: *"Candidate OCR fields are explicitly UNTRUSTED until authorized verification."*
- `get_onboarding_checklist()`: Computes checklist status across the 3 mandatory documents.
- `upload_document()`: Simulates camera capture. Applies blur detection filter. Sets status to `OCR_PASSED` or `OCR_FAILED` (never verified).
- `submit_for_authorized_verification()`: Simulates authorized NSDL PAN registry and bank penny-drop checking. Only upon success are merchant records updated to `ACTIVE` and `kyc_status = "VERIFIED"`. Emits `AUTHORIZED_KYC_VERIFICATION_COMPLETED` audit event.
- `get_pipeline_applications()`: Aggregates pipeline state for Employee Web.

### 2.4 Risk-Tiered Agent Tools (`OnboardTools`)
- `get_onboarding_checklist` (R0): Reads authoritative checklist.
- `get_document_receipt_status` (R0): Returns individual document status.
- `extract_document_fields` (R0): OCR extraction with candidate fields flagged untrusted.
- `create_missing_document_task` (R1): Idempotent task creation for human sales / ops assistance.
- `submit_for_authorized_verification` (R1): Policy-gated execution of simulated external verification.
- `validate_security_invariants`: Blocks queries asking for passwords, OTPs, or UPI PINs.

### 2.5 LangGraph Specialist Agent (`OnboardAgent`)
StateGraph with conditional edge routing:
- `inspect_checklist`: Checks credentials security invariant $\to$ evaluates application completeness.
- `chase_specific_missing_item`: Produces specific guidance for blurry (e.g. blurry PAN) or missing documents, issuing an `ONBOARDING_CHASE_CARD`.
- `submit_verification`: When all 3 documents pass OCR, triggers authorized external verification and returns `ONBOARDING_COMPLETED_CARD`.

### 2.6 Saathi Brain Orchestrator Routing
Orchestrator routes onboarding and document queries (`"onboard"`, `"kyc"`, `"documents"`, `"pan"`, `"bank proof"`, `"shop photo"`, `"passbook"`, `"verify documents"`, `"signup"`) to `OnboardAgent`, generating Indic voice synthesis audio.

### 2.7 Frontend Implementations
- **`merchant-mobile`**:
  - Dedicated **KYC Onboard** screen with 4-step progress tracker (PAN $\to$ Bank $\to$ Photo $\to$ Activation).
  - Camera upload control supporting Clear vs. Blurry test simulation.
  - Rejection alert card with specific retry button.
  - Candidate OCR preview with explicit untrusted disclaimer.
  - Single-tap *"Submit for Authorized Verification"* activating the account.
  - Home tab incomplete signup banner and Chat quick-action chip.
  - Login demo account quick-selector for all 4 merchant states.
- **`employee-web`**:
  - Dedicated **Onboard (KYC)** tab with KPI cards (Total Pipeline, Missing Docs, Blurry Resubmit, Ready, Verified).
  - Real-time Applications table with per-document status chips.
  - Candidate OCR Inspection modal with untrusted invariant notice.
  - One-click *"Verify & Activate"* button executing authorized verification.
