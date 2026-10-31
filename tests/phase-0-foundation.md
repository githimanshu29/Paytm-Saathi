# Phase 0: Test Execution & Verification Evidence

### 1. Backend Pytest Suite
All automated tests run via `uv run pytest`:
```text
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\Himanshu Kumar\Desktop\Paytm-Saathi\backend
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1, asyncio-1.4.1
collected 6 items

tests\test_health.py .                                                   [ 16%]
tests\test_seed_invariants.py .....                                      [100%]

======================= 6 passed in 19.64s ========================
```

#### Test Invariants Verified:
1. `test_health_returns_200_and_logs_audit_event`: Confirms HTTP 200 response from `/health` and verifies that a corresponding row was persisted in `audit_events` with `actor="system"`, `is_synthetic=True`, and `environment="DEMO"`.
2. `test_merchant_seed_invariants`: Confirms at least 4 demo merchants exist, each with `is_synthetic=True` and `environment="DEMO"`.
3. `test_transaction_invariants`: Confirms all transaction amounts are strictly positive integers (paise) with `currency="INR"`.
4. `test_device_invariants`: Confirms all Soundbox devices have `battery_level` between 0–100% and valid serial numbers.
5. `test_task_bucket_states_represented`: Confirms that all 5 status bucket states (`verified`, `executed`, `pending`, `awaiting_approval`, `needs_human`) exist in the seeded task dataset.
6. `test_policy_engine_rules`: Asserts that `R0` reads are allowed, `R4` actions are blocked, `R3` regulated actions are rejected with a required review task, and `R2` actions require approvals.

---

### 2. Database Migration & Seeding Verification
- **Alembic migration:** `uv run alembic upgrade head` successfully created all 10 tables (`tenants`, `merchants`, `employees`, `devices`, `transactions`, `customers`, `receivables`, `tasks`, `action_approvals`, `audit_events`) and 3 indexes.
- **Deterministic reset:** `uv run python scripts/reset_demo_data.py` confirmed table purge and re-seed idempotency:
  ```text
  Resetting database demo state...
  All records cleaned. Re-seeding deterministic demo state...
  Demo data successfully seeded for 4 merchants, 4 employees, devices, tasks, transactions, and audit trail.
  Database reset and re-seeded successfully.
  ```

---

### 3. Frontend Build & Typecheck Verification
- **Shared Design Tokens:** `pnpm --filter @paytm-saathi/design-tokens build` compiled with `tsc` to `./dist` (ESM + types).
- **Employee Web App:** `pnpm --filter employee-web build` built via Vite:
  ```text
  dist/index.html                   0.80 kB │ gzip:  0.47 kB
  dist/assets/index-C2Q5_w5A.css   13.36 kB │ gzip:  3.44 kB
  dist/assets/index-MTszCtIF.js   158.99 kB │ gzip: 50.77 kB
  ✓ built in 19.54s
  ```
- **Merchant Mobile App:** `cd apps/merchant-mobile; pnpm exec tsc --noEmit` exited with code 0 (zero TypeScript errors).
