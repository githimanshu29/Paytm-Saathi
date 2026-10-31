# Phase 12: Polish Pass, Security/Testing Sweep and Final QA — Test Plan & Execution

## 1. Test Overview
The Phase 12 verification process spans three layers:
1. **Frontend Typecheck & Production Build Verification**:
   - `merchant-mobile`: `pnpm --filter merchant-mobile exec tsc --noEmit`
   - `employee-web`: `pnpm --filter employee-web build`
2. **Acceptance Sweep Test Suite**:
   - `backend/tests/test_phase12_acceptance_sweep.py` (11 targeted invariant tests)
3. **Full System Regression Sweep**:
   - Entire backend pytest suite across all 13 test modules: `cd backend; uv run pytest -p no:langsmith`

---

## 2. Acceptance Sweep Results (`test_phase12_acceptance_sweep.py`)

| Test Case Name | Core Master Context Invariant | Result |
|---|---|:---:|
| `test_invariant_1_pending_transaction_never_produces_refund_executed` | PENDING transaction never auto-refunds or claims success | **PASSED** |
| `test_invariant_2_device_recheck_gates_every_fixed_claim` | Live device telemetry re-check gates recovery or books technician | **PASSED** |
| `test_invariant_3_settlement_difference_calculated_by_integer_code` | Minor units (paise) integer arithmetic in code, never LLM | **PASSED** |
| `test_invariant_4_followup_sent_does_not_equal_merchant_revived` | Follow-up sent does not mark merchant revived without real volume | **PASSED** |
| `test_invariant_5_ocr_output_alone_never_sets_kyc_verified` | OCR candidate output is untrusted; authorized verification required | **PASSED** |
| `test_invariant_6_no_crm_write_without_rep_confirmation` | Voice note transcript is draft; rep confirmation required for CRM | **PASSED** |
| `test_invariant_7_vasooli_blocks_disputed_revoked_and_requires_payment_proof` | Halts on revoked consent/disputes; unverified payments flagged | **PASSED** |
| `test_invariant_8_idempotency_key_prevents_duplicate_side_effects` | SHA-256 parameter signature intercepts duplicate side-effects | **PASSED** |
| `test_invariant_9_bounded_loop_tool_limit_ends_in_needs_human_review` | Tool/planner limits ceiling breach transitions to `NEEDS_HUMAN_REVIEW` | **PASSED** |
| `test_invariant_10_prompt_injection_routed_to_needs_human_and_prohibits_tools` | Adversarial injection routes to `NEEDS_HUMAN` without tool execution | **PASSED** |
| `test_invariant_11_mock_side_effects_are_clearly_labeled_simulated` | All mock side-effects carry explicit `SIMULATED` / `DEMO` markers | **PASSED** |

**Summary**: 11 passed, 0 failed in 9.22 seconds.

---

## 3. Database Seeding & UI Verification
- `uv run python scripts/seed_demo_data.py`: Exits with code 0 idempotently on consecutive runs.
- `merchant-mobile`: Typechecks clean with 0 errors. Empty states render for empty collections and udhaar.
- `employee-web`: Production build succeeds in 1m 40s. Empty states render with matching Lucide icons for Cases, Onboarding, Revive, Vasooli, and Handoff Timeline.
