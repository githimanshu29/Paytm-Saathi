# Phase 6: Problems & Overcoming Them (The Reconcile Agent)

### Problem 1: Preventing Floating-Point Inaccuracies and LLM Hallucinated Math in Financial Settlements
- **Context**: In merchant settlement reconciliation, merchants often query discrepancies between gross sales, customer refunds, processing fees, chargebacks, and net credited payouts. Allowing an LLM to perform arithmetic or using floating-point math can introduce rounding drift (e.g. `0.1 + 0.2 = 0.30000000000000004`), which is unacceptable for banking and financial operations.
- **Root Cause**: LLMs are statistical language predictors, not arithmetic engines; floats are IEEE 754 representations prone to decimal inaccuracies.
- **Resolution**:
  - All database columns and adapter fields (`gross_sales`, `refunds`, `fees`, `chargebacks`, `net_expected`, `net_settled`, `discrepancy`) are strictly represented in integer minor units (paise: `1 INR = 100 paise`).
  - `calculate_settlement_difference` in `ReconcileTools` is deterministic Python integer code: `net_expected = gross_sales_paise - refunds_paise - fees_paise - chargebacks_paise` and `diff = net_settled_paise - net_expected`.
  - The LLM's sole role is phrasing the deterministic outputs into conversational English and Hindi explanations; it never calculates or overrides numbers.

---

### Problem 2: Idempotency and Preventing Duplicate Dispute Filings on Retried Inquiries
- **Context**: A merchant may ask "Why is my 27 Oct settlement ₹1,200 short?" multiple times in the chat. Without idempotency protection, each inquiry would generate an independent dispute case in `needs_human`, spamming the operations review queue.
- **Root Cause**: Stateless agent invocations could trigger `create_settlement_dispute` on every prompt execution.
- **Resolution**:
  - Implemented multi-layered idempotency in `ReconcileTools.create_settlement_dispute`:
    1. Built an SHA-256 idempotency key: `f"{execution_id}:CREATE_SETTLEMENT_DISPUTE:{merchant_id}:{settlement_date}"`.
    2. Before inserting a new task, queried existing active tasks matching `Task.merchant_id == merchant_id` and `Task.title.like(f"%Settlement Dispute%{settlement_date}%")`.
    3. If found, returns the existing `task_id` with `is_duplicate_idempotent: True` and skips creating a duplicate task or audit event.

---

### Problem 3: Distinguishing Live Checkout Volume from Past Settlement Batch Data in `get_merchant_summary`
- **Context**: When seeding historical settlement batches for normal (2026-10-28, ₹10,000) and anomalous (2026-10-27, ₹15,000) days, `GET /merchant/me/summary` aggregated all `SUCCESS` transactions in `limit(10)`, inadvertently inflating `today_total_paise` from `92,000` to `2,592,000` paise.
- **Root Cause**: `get_merchant_summary` lacked date scoping and settlement transaction filtering.
- **Resolution**:
  - Filtered `today_success_txs` in `get_merchant_summary` by `tx.created_at.date() == datetime.utcnow().date()` and `not tx.id.startswith("tx_set_")`.
  - Allowed checkout dashboard totals to reflect today's real-time counter sales while isolating historical settlement batches for the Reconcile copilot.

---

### Problem 4: Employee Web Case Timeline Event Truncation
- **Context**: In `GET /employee/cases/{id}/timeline`, when fetching audit events for a newly opened settlement dispute, earlier merchant audit events took up the entire `limit(25)` when ordered ascending (`created_at.asc()`), omitting the `CREATE_SETTLEMENT_DISPUTE` event from the response.
- **Root Cause**: Queries ordered chronologically ascending returned the first 25 events from initial system seeding rather than the most recent case-specific operations.
- **Resolution**:
  - Changed query to `order_by(AuditEvent.created_at.desc()).limit(25)` and then reversed the list in Python (`list(reversed(events_query))`) to ensure recent dispute creation and policy events appear in the chronological timeline.
