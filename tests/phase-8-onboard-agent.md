# Phase 8: The Onboard Agent (KYC Closer & Document Verification) — Test Verification

## 1. Test Suite Summary
The Phase 8 test suite in `backend/tests/test_onboard_agent.py` contains 14 comprehensive test cases verifying all safety invariants, adapter routines, agent branches, and REST API endpoints.

All 14 tests run via `uv run pytest tests/test_onboard_agent.py -v` and pass with 100% success.
The entire backend test suite across all 8 phases (76 tests) passes with 100% green status.

## 2. Test Breakdown

| # | Test Function | Verified Behavior |
|---|---|---|
| 1 | `test_blurry_document_rejected_with_specific_reason` | Confirms blurry PAN on `mer_gupta_electronics` is rejected with exact reason (`"Your PAN card photo is blurry and illegible. Please resend a sharp, well-lit photo"`), never a generic rejection. |
| 2 | `test_missing_document_identified_correctly` | Confirms missing Bank Proof on `mer_singh_automobiles` is flagged with specific upload instructions. |
| 3 | `test_untrusted_ocr_candidate_fields_invariant` | Verifies that OCR candidate fields are explicitly marked with `untrusted: True` and disclaimer. |
| 4 | `test_ocr_alone_cannot_activate_or_verify` | Invariant: even when all 3 docs pass OCR, `kyc_status` remains `PENDING` and merchant status is not `ACTIVE`. |
| 5 | `test_full_pass_reaches_active_only_after_simulated_verification` | Invariant: calling authorized verification transitions merchant to `ACTIVE`, `kyc_status = VERIFIED`, and logs `AUTHORIZED_KYC_VERIFICATION_COMPLETED` audit event. |
| 6 | `test_cannot_submit_incomplete_application_for_verification` | Verifies that attempting to verify an application with blurry or missing documents is rejected with clear error message. |
| 7 | `test_security_invariant_blocks_asking_for_password_otp_pin` | Security Invariant: queries asking for passwords, OTPs, or UPI PINs are blocked and return security violation alert. |
| 8 | `test_agent_chases_blurry_pan_with_specific_guidance` | Confirms OnboardAgent LangGraph produces specific chase instructions and `ONBOARDING_CHASE_CARD` for blurry documents. |
| 9 | `test_agent_submits_verification_when_all_docs_pass` | Confirms OnboardAgent LangGraph proceeds to authorized verification when all 3 docs pass OCR, returning `ONBOARDING_COMPLETED_CARD`. |
| 10 | `test_orchestrator_routes_onboard_query_and_generates_speech` | SaathiBrainOrchestrator routes onboarding intents to `ONBOARD` agent and synthesizes speech audio base64. |
| 11 | `test_api_merchant_onboarding_checklist` | `GET /merchant/onboarding/checklist` returns checklist with 3 mandatory document items. |
| 12 | `test_api_merchant_upload_blurry_document` | `POST /merchant/onboarding/upload` with `simulate_blur=True` sets status to `OCR_FAILED` and flag `BLURRY`. |
| 13 | `test_api_merchant_upload_clear_document` | `POST /merchant/onboarding/upload` with clean scan sets status to `OCR_PASSED` and flag `CLEAR` with candidate fields. |
| 14 | `test_api_employee_pipeline_view` | `GET /employee/onboarding/pipeline` returns seeded applications across all pipeline stages. |

## 3. Frontend Verification
- **Merchant Mobile (`apps/merchant-mobile`)**: Verified with `pnpm --filter merchant-mobile exec tsc --noEmit` $\to$ Exit code 0 (zero errors).
- **Employee Web (`apps/employee-web`)**: Verified with `pnpm --filter employee-web build` $\to$ Exit code 0 (clean production build).
- **Full Backend Suite**: Verified with `uv run pytest -v` $\to$ 76 passed, 0 failed.
