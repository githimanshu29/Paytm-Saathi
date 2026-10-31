# Phase 3: Architectural Explanations & Core Concepts

### 1. The Activity Log as a Direct Projection of `audit_events`
A core tenet of the Paytm Saathi governance model is that the Employee Activity Log is **not** a separately maintained event bus or fabricated UI list:
- Every action evaluated by the `PolicyEngine`, every tool executed, and every HTTP health ping writes an immutable row to `audit_events`.
- `GET /employee/audit-log` queries this exact database table in descending order of `created_at`.
- The dashboard polls this endpoint every 4 seconds, guaranteeing that any activity performed anywhere in the system (e.g. merchant login, health check, automated settlement) immediately reflects in the employee console.

### 2. Cases Table & Risk-Gated Slide-Over Panel
The Cases view unifies tasks across the five master StatusChip lifecycle states:
- `verified` (e.g. daily settlement auto-verified)
- `executed` (e.g. soundbox audio language update applied)
- `pending` (e.g. dormant merchant revival outreach evaluation)
- `awaiting_approval` (e.g. soundbox SIM reset requiring R2 authorization)
- `needs_human` (e.g. KYC bank account mismatch requiring compliance review)

When an employee clicks on any case row:
1. A slide-over panel glides into view from the right.
2. If the task contains an approval gate (`R2` / `R3`), it prominently presents the approval decision, reason, approver, and expiration timer.
3. It fetches `GET /employee/cases/{case_id}/timeline` to render a vertical audit timeline sourced directly from authoritative `audit_events`.

### 3. Real Seeded KPI Calculation
All top-line metrics in the dashboard are dynamically computed via SQL aggregates across the seeded demo database:
- **Kiranas Monitored:** `COUNT(merchants)`
- **Soundboxes Active:** `COUNT(devices WHERE status = 'ONLINE') / COUNT(devices)`
- **Pending Approvals:** `COUNT(action_approvals WHERE decision = 'PENDING')`
- **Human Review Needed:** `COUNT(tasks WHERE bucket = 'needs_human')`
- **Settled Volume:** `SUM(transactions.amount WHERE status = 'SUCCESS')` formatted from minor paise to INR.
