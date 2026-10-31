# Phase 6: Technical Explanation (The Reconcile Agent — Settlement Copilot)

### 1. Overview & System Mission
Phase 6 delivers **The Reconcile Agent**, the third specialist agent in the Paytm Saathi multi-agent architecture. Its mission is to act as a **Settlement Copilot** for Kirana store owners and small merchants.

When a merchant asks why a daily payout does not match their expectations, the Reconcile Agent:
1. Performs deterministic, code-based arithmetic in integer minor units (paise) to calculate expected net settlement:
   $$\text{Expected Net} = \text{Gross Sales} - \text{Refunds} - \text{Fees (MDR + Soundbox)} - \text{Chargebacks}$$
2. Compares expected net with the actual nodal bank credit received (`ICICINODAL...` UTR).
3. If balanced ($\text{Discrepancy} = 0$), phrases the breakdown in clear language and verifies that all deductions match the ledger without creating unnecessary tickets.
4. If a genuine discrepancy exists ($\text{Discrepancy} \neq 0$), files an evidence-backed dispute case under `needs_human` with the exact shortfall amount and invites the merchant to attach bank statement proof.

---

### 2. Architecture & Core Components

```
                   ┌────────────────────────────────────────┐
                   │    Merchant App / Web Control Tower     │
                   └──────────────────┬─────────────────────┘
                                      │
                                      ▼
                        SaathiBrainOrchestrator
                       (Intent Routing: Reconcile)
                                      │
                                      ▼
                    LangGraph: ReconcileAgent StateGraph
          ┌─────────────────────────────────────────────────────────┐
          │  parse_date ──▶ fetch_and_calculate ──▶ generate_action  │
          └───────────────────────────┬─────────────────────────────┘
                                      │
                     Deterministic Integer Arithmetic
                     (Strict Integer Minor Units / Paise)
                                      │
                                      ▼
                                ReconcileTools
                   ┌──────────────────┴──────────────────┐
                   ▼                                     ▼
        get_settlement_summary (R0)            create_settlement_dispute (R1)
        get_settlement_line_items (R0)         - Needs Human Bucket
                                               - Evidence Notes Attached
                                               - Idempotency Enforced
                                      │
                                      ▼
                          MockSettlementAdapter
                                      │
                                      ▼
                  Database: settlements, transaction_fees,
                        chargebacks, tasks, audit_events
```

#### A. Database Schema & Models (`backend/app/db/models.py`)
- **`settlements`**: Stores daily settlement batch summaries per merchant:
  - `settlement_date`: `YYYY-MM-DD` string.
  - `gross_sales`, `refunds`, `fees`, `chargebacks`, `net_expected`, `net_settled`, `discrepancy`: All in integer paise.
  - `status`: `RECONCILED`, `DISCREPANCY`, `DISPUTED`.
  - `bank_utr`, `nodal_account`: Bank clearing identifiers.
  - `dispute_case_id`: Foreign key reference to `tasks.id`.
- **`transaction_fees`**: Stores line-item fees (e.g. MDR 1.5%, Soundbox rental fee) tied to `transaction_id`.
- **`chargebacks`**: Stores contested transactions with dispute reference, reason, and status.
- **`tasks` (Extended)**: Added `evidence_notes`, `evidence_url`, and `dispute_amount` (in paise).

#### B. Adapter Layer (`backend/app/adapters/settlement.py`)
- Implements `ISettlementAdapter` protocol:
  - `get_settlement(merchant_id, settlement_date) -> Optional[SettlementRecord]`
  - `get_settlement_line_items(merchant_id, settlement_date) -> SettlementLineItemsRecord`
  - `list_settlements(merchant_id, limit) -> List[SettlementRecord]`
- Decouples storage details so real Paytm nodal payout APIs can swap in seamlessly without altering agent reasoning.

#### C. Deterministic Arithmetic Engine (`backend/app/tools/reconcile.py`)
- **Strict Invariant**: Floating-point numbers and LLM arithmetic calculations are completely banned.
- `calculate_settlement_difference(gross_sales_paise, refunds_paise, fees_paise, chargebacks_paise, net_settled_paise)` computes:
  ```python
  net_expected = gross_sales_paise - refunds_paise - fees_paise - chargebacks_paise
  diff = net_settled_paise - net_expected
  is_reconciled = (diff == 0)
  ```
  Returns exact paise differences and human-readable formatted rupee representations.

#### D. Idempotent Dispute Case Creation (`ReconcileTools.create_settlement_dispute`)
- Governed by Paytm Policy Engine at Risk Tier **R1** (Internal Human Review Task).
- Generates an idempotency key from `f"{execution_id}:CREATE_SETTLEMENT_DISPUTE:{merchant_id}:{settlement_date}"`.
- Queries existing tasks before insertion. If an active dispute already exists for that merchant and settlement date, it re-returns the existing case ID without double-writing.
- Attaches mathematical audit mismatch breakdown to `Task.evidence_notes` and nodal statement URL to `Task.evidence_url`.
- Automatically logs `CREATE_SETTLEMENT_DISPUTE` to `audit_events`.

---

### 3. Seeded Data Scenarios

| Merchant | Settlement Date | Gross Sales | Refunds | Fees | Chargebacks | Expected Net | Actual Bank Payout | Discrepancy | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Sharma Kirana Store** | `2026-10-28` (Yesterday) | ₹10,000 | ₹500 | ₹300 | ₹0 | **₹9,200** | **₹9,200** | **₹0.00** | `RECONCILED` (`verified`) |
| **Sharma Kirana Store** | `2026-10-27` (Day Before) | ₹15,000 | ₹1,000 | ₹450 | ₹550 | **₹13,000** | **₹11,800** | **-₹1,200.00** | `DISCREPANCY` (`needs_human`) |

---

### 4. User Interface Integrations

#### A. Merchant Mobile (`apps/merchant-mobile/App.tsx`)
- Structured `SETTLEMENT_BREAKDOWN` Card:
  - Neatly formats Gross Sales (+), Customer Refunds (-), MDR & Soundbox Fees (-), and Chargebacks (-) in a monospace numerical table.
  - Highlights calculated net due vs actual bank deposit.
  - Dynamically renders `StatusChipNative` with `verified` (Reconciled) or `needs_human` (Shortfall Detected).
  - On discrepancy, displays priority dispute case alert and an interactive **"📷 Attach Passbook / Statement Proof"** button that immediately updates state and confirms evidence submission.
- Scenario quick-launch chips in Saathi chat bar:
  - `📊 Yesterday's Settlement (Reconciled)`
  - `⚠️ 27 Oct Settlement (Discrepancy Shortfall)`

#### B. Employee Web Control Tower (`apps/employee-web/src/App.tsx`)
- `Reconcile (Settlements)` navigation tab filters cases specifically for settlement disputes and reconciliation shortfalls.
- Cases table displays an inline badge: `Shortfall: -₹1,200.00`.
- Slide-over detail panel displays a dedicated **Nodal Settlement Discrepancy Evidence** card featuring:
  - Exact shortfall amount.
  - Full audit statement breakdown note explaining the discrepancy.
  - Direct statement attachment link.
  - Case timeline showing the `CREATE_SETTLEMENT_DISPUTE` event sourced from `audit_events`.
