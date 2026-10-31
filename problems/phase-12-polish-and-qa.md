# Phase 12: Polish Pass, Security/Testing Sweep and Final QA — Problem Statement

## 1. Context & Objectives
Phase 12 is the final stabilization, audit, and hardening milestone of Paytm Saathi. The objective is zero new speculative features, but rather:
1. **Design Token & UI Polish**: Ensure visual uniformity across both `merchant-mobile` and `employee-web`. All status chips must strictly use the canonical `@paytm-saathi/design-tokens` values (`verified`, `executed`, `pending`, `awaiting_approval`, `needs_human`).
2. **Comprehensive Empty States**: Eliminate all blank tables or screens when data lists are empty. Provide an intuitive Lucide icon, bold header, and clear one-line descriptive subtitle for:
   - Control Tower Cases & Tasks Table
   - KYC Onboarding Pipeline
   - Merchant Health & Revival Table
   - Multi-Agent Handoff Audit Timeline
   - Consensual Udhaar / Receivables Ledger
   - Mobile Transactions and Customer Dues Lists
3. **Graceful Loading & Error States**: Replace raw network errors, stack traces, or uncaught exceptions with user-friendly retry banners and loading skeletons.
4. **Concrete Approval UI Audit**: Audit all approval-gated actions (Refund Review, Discrepancy Dispute, Retention Offer, Udhaar Reminder, Installment Split) so merchants and employees see an exact preview of the proposed action rather than a bare "Approve?".
5. **Acceptance-Test Sweep (11 Safety Invariants)**: Formulate an exhaustive automated test suite (`backend/tests/test_phase12_acceptance_sweep.py`) proving that all 11 Master Context core safety and policy invariants hold unconditionally.
6. **Demo Readiness**: Ensure `seed_demo_data.py` is fully idempotent and executable at any time, and provide an actionable, step-by-step `DEMO_SCRIPT.md` detailing how to present all 7 specialist agents and the multi-agent handoff.
