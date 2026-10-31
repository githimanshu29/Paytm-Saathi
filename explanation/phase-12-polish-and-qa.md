# Phase 12: Polish Pass, Security/Testing Sweep and Final QA — Implementation Details

## 1. Frontend Polish & Canonical Design Token Consistency

### Status Chips & Tokens
All status chips in both `apps/merchant-mobile` and `apps/employee-web` adhere strictly to `@paytm-saathi/design-tokens`:
- `verified` (#0B8457 / emerald): Authoritative, cryptographically or telemetrically confirmed states.
- `executed` (#0077A8 / blue): Completed workflows or actions committed to the database.
- `pending` (#4B5563 / gray): Queued, scheduled, or baseline idle items.
- `awaiting_approval` (#B45309 / amber): Human-in-the-loop review cards requiring merchant or manager consent.
- `needs_human` (#DC2626 / red): Security violations, fraud flags, prompt injections, or hardware failures requiring physical technician dispatch.

### Empty States Across Views
Every list and data table was reviewed and enhanced with dedicated empty states:
1. **Control Tower Cases Table**: `FileText` icon + *"No support cases or tasks found. No active cases match the selected status filter."*
2. **Onboarding Pipeline Table**: `UserCheck` icon + *"No onboarding applications found. No merchant KYC records match the selected filter."*
3. **Merchant Health & Dormancy Table**: `Activity` icon + *"No merchants found in this revival status."*
4. **Handoff Audit Trail Timeline**: `GitMerge` icon + *"No handoff audit records yet. Click '⚡ Run Full 6-Step Chain' above to simulate cross-agent routing."*
5. **Vasooli Receivables Ledger**: `Coins` icon + *"No receivables or store credit entries found. All customer dues are clear or none have been recorded yet."*
6. **Merchant Mobile Today's Collections**: `💳` emoji + *"No transactions recorded today. Incoming payments will appear here in real time."*
7. **Merchant Mobile Udhaar Dues**: `📒` emoji + *"No pending store credit records. Keep track of customer udhaar with clear mutual consent."*

---

## 2. Concrete Approval Previews Audit

Across all 5 approval-gated actions, zero screens show a bare "Approve?":
1. **Refund Review Request (Resolve)**: Previews transaction UTR, exact paise amount formatted to INR, and clear disclaimer: *"Initiating bank review does NOT deduct from your settlement balance."*
2. **Settlement Discrepancy Dispute (Reconcile)**: Previews calculated shortfall in minor units, nodal account reference, and ICICI batch statement context.
3. **Retention Offer (Revive)**: Previews offer code (`KIRANA_BOOSTER_0MDR`), 0% MDR on next 100 transactions, and Soundbox rent rebate.
4. **Udhaar Reminder (Vasooli)**: Previews recipient name, phone, exact due amount, bilingual WhatsApp message text, and verified consent status.
5. **Installment Split (Vasooli)**: Previews number of installments, exact part-amounts in paise, and due dates before saving.

---

## 3. Database Seeding Idempotency Fixes

In `backend/scripts/seed_demo_data.py`:
- Added existence checks (`if not db.query(...).filter_by(id=...).first():`) across:
  - `MerchantActivityMetric` and `MerchantFollowup` (Phase 7)
  - `MerchantDocument` (Phase 8)
  - `MerchantVisit` (Phase 9)
  - `AuditEvent` initial seeder log
- Seeding can now be re-executed repeatedly without SQLite `IntegrityError` unique constraint violations, returning exit code 0 every time.

---

## 4. Acceptance Sweep Test Suite (`test_phase12_acceptance_sweep.py`)

A dedicated test suite was built to programmatically verify all 11 core safety invariants:
1. `test_invariant_1_pending_transaction_never_produces_refund_executed`: Proves PENDING state enforces 24-48h SLA and blocks R3 financial refunds.
2. `test_invariant_2_device_recheck_gates_every_fixed_claim`: Proves reboot signal alone never claims recovery; live telemetry re-check gates technician dispatch.
3. `test_invariant_3_settlement_difference_calculated_by_integer_code`: Proves settlement arithmetic is deterministic Python integer subtraction in paise, never LLM hallucination.
4. `test_invariant_4_followup_sent_does_not_equal_merchant_revived`: Proves follow-up communication maintains unrecovered stage until fresh volume is confirmed.
5. `test_invariant_5_ocr_output_alone_never_sets_kyc_verified`: Proves candidate OCR output is tagged untrusted and cannot change `kyc_status` to verified.
6. `test_invariant_6_no_crm_write_without_rep_confirmation`: Proves voice note transcripts produce uncommitted draft summaries requiring explicit rep confirmation.
7. `test_invariant_7_vasooli_blocks_disputed_revoked_and_requires_payment_proof`: Proves reminders are blocked on revoked permission or active disputes, and unverified payments are flagged.
8. `test_invariant_8_idempotency_key_prevents_duplicate_side_effects`: Proves identical canonical hashes are intercepted to prevent duplicate actions.
9. `test_invariant_9_bounded_loop_tool_limit_ends_in_needs_human_review`: Proves workflow bounds (12 tools / 5 loops) escalate to `NEEDS_HUMAN_REVIEW`.
10. `test_invariant_10_prompt_injection_routed_to_needs_human_and_prohibits_tools`: Proves prompt injections route to `NEEDS_HUMAN` without executing prohibited tools.
11. `test_invariant_11_mock_side_effects_are_clearly_labeled_simulated`: Proves all demo links and tasks are explicitly marked `SIMULATED` and `DEMO`.
