# Phase 3: Problems Encountered & Resolutions

### 1. Unified Cases vs. Discrete Relational Models
- **Problem:** In our relational schema, agent tasks reside in `tasks` while sensitive actions needing sign-off reside in `action_approvals`. A naive approach might force the frontend to make multiple disjoint queries and manually stitch them together.
- **Resolution:** Created a unified `/employee/cases` view on the backend that joins `tasks` with `merchants` and left outer joins `action_approvals`. The response returns a single cohesive `CaseItem` structure containing the store name, priority, StatusChip bucket, and embedded approval details (`decision`, `risk_tier`, `approver`, `reason`).

### 2. Live Activity Polling Without Memory Leaks or Resource Exhaustion
- **Problem:** Setting up rapid uncoordinated polling across multiple components can trigger overlapping requests, UI thrashing, and database connection pool exhaustion.
- **Resolution:** Centralized polling in `apps/employee-web/src/App.tsx` using staggered timers (Audit log polls every 4 seconds; KPI & cases poll every 8 seconds) with comprehensive cleanup hooks in React's `useEffect`. Also added a manual refresh button with spinner state.

### 3. Sourcing Timeline Directly from Audit Events
- **Problem:** Prototype dashboards often fake timeline items or hardcode historical events in UI state.
- **Resolution:** Built `GET /employee/cases/{case_id}/timeline` querying straight from the `audit_events` table (matching `target == case_id`, `merchant_id`, or case hash). The slide-over panel renders a real, vertical connected timeline backed by verifiable database rows.
