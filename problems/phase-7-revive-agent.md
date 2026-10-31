# Phase 7: Problems & Overcoming Them (The Revive Agent)

### Problem 1: Preventing False "Revival" Declarations (The Honest Tracking Invariant)
- **Context**: In traditional CRM systems or naive reactivation bots, sending an email or push notification to a churned customer often prematurely marks the campaign as "successful" or the merchant as "reactivated". In financial services and payment acquiring, declaring a dormant kirana "revived" merely because an agent dispatched an offer or the merchant clicked "Accept" creates false business metrics.
- **Root Cause**: Equating customer engagement (reading or accepting an offer) with actual commercial recovery (re-starting counter transactions on the Paytm Soundbox).
- **Resolution**:
  - Architected a strict two-stage state machine:
    $$\text{AT\_RISK} \xrightarrow{\text{Offer Sent}} \text{FOLLOWUP\_SENT} \xrightarrow{\text{Merchant Accepts}} \text{WARM\_LEAD} \xrightarrow[\ge 80\%\text{ baseline volume}]{\text{Authoritative Telemetry Recheck}} \text{REVIVED}$$
  - Implemented `record_merchant_recovery` in `MockReviveAdapter`: only when real transaction telemetry shows $\ge 80\%$ baseline daily volume recovery is `health_status` set to `HEALTHY`, `revival_stage` set to `REVIVED`, and `recovered_at` timestamp recorded.
  - Sending a follow-up or accepting an offer safely tracks the merchant under `FOLLOWUP_SENT` or `WARM_LEAD` (assigned to field sales rep Amit V.), with zero risk of phantom metrics.

---

### Problem 2: Handoff Integrity Across Existing Domain Adapters
- **Context**: When a scheduled scan detects that a merchant's volume has plummeted by $\ge 40\%$, re-running raw diagnostics from scratch would duplicate the logic already established in Fix (Phase 5) and Reconcile (Phase 6).
- **Root Cause**: Siloed agent designs tend to duplicate telemetry queries and reinvent diagnostics.
- **Resolution**:
  - Reused `MockDeviceAdapter` and `MockSettlementAdapter` through a unified `ReviveTools` interface.
  - Branch 1 (Device issue): Evaluates device telemetry (`SB-DEL-404 OFFLINE`). Instead of reinventing technician booking, hands off evidence directly to the Fix Agent (`handed_off_to="FIX"`).
  - Branch 2 (Settlement issue): Evaluates settlement ledgers (`ICICI shortfall -₹940`). Instead of re-investigating nodal accounts, hands off evidence directly to the Reconcile Agent (`handed_off_to="RECONCILE"`).
  - Branch 3 (Pure Disengagement / Competitor): Only when hardware is verified online and payouts are fully reconciled does Revive trigger commercial retention actions.

---

### Problem 3: Policy Gating Against Unauthorized Financial Waivers & Fake Discount Codes
- **Context**: Autonomous LLM agents attempting to retain merchants might hallucinate unapproved commercial terms, such as "100% lifetime MDR waiver" or unauthorized cash rebates.
- **Root Cause**: Free-form LLM generation without policy-enforced action schemas.
- **Resolution**:
  - Enforced `PolicyEngine` evaluation on every `create_merchant_followup` action.
  - Whitelisted approved commercial retention offers (`{"BOOSTER30", "KIRANA_BOOSTER_0MDR", "REBATE100", "STAND_REFRESH"}`).
  - Any attempt to submit an unauthorized code (e.g. `ILLEGAL_100_PERCENT`) elevates the proposal to `RiskTier.R4` (prohibited), immediately rejected by `PolicyEngine.evaluate(proposal)` with a policy violation audit trail.

---

### Problem 4: Test State Isolation Across Chained Pytest Invocations
- **Context**: When running unit and integration tests sequentially, Test 7 and Test 10 simulated real volume recovery ($\ge 80\%$ baseline), mutating `mer_sharma_kirana`'s drop percentage from 70% to 0%. This caused subsequent tests (such as manual scan counts and orchestrator dormancy intent checks) to see 0% drop and report the merchant as already healthy.
- **Root Cause**: In-memory database records mutated during simulation persisted across test functions in the same pytest session.
- **Resolution**:
  - Added an `autouse=True` fixture `ensure_seed_metrics(db)` in `test_revive_agent.py` that deterministically resets baseline drop percentages (92%, 79%, 70%), offline device telemetry, and delivered follow-ups before every test run.
  - Reset the database via `scripts/reset_demo_data.py` to leave a deterministic demo environment for reviewers.
