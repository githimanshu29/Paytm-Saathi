# Phase 2: Test Execution & Verification Evidence

### 1. Pytest Test Results
Command: `uv run pytest tests/test_merchant.py`
```text
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\Himanshu Kumar\Desktop\Paytm-Saathi\backend
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1, asyncio-1.4.1
collected 3 items

tests\test_merchant.py ...                                               [100%]

======================= 3 passed in 1.48s =======================
```

Full Test Suite Run: `uv run pytest`
```text
collected 17 items

tests\test_auth.py ........                                              [ 47%]
tests\test_health.py .                                                   [ 52%]
tests\test_merchant.py ...                                               [ 70%]
tests\test_seed_invariants.py .....                                      [100%]

====================== 17 passed in 10.36s =======================
```

### 2. Verified Test Cases
1. **`test_merchant_summary_authenticated`**:
   - Logs in with demo merchant phone `+919876543210` via OTP `123456`.
   - Calls `GET /merchant/me/summary` with `Bearer <token>`.
   - Confirms HTTP 200 and matches seeded values:
     - Store: `Sharma Kirana Store`, City: `Jaipur`, Status: `ACTIVE`.
     - Device: `Soundbox 4G Pro`, S/N: `SB-JAI-101`, Battery: `88%`, Chip: `verified`.
     - Payments: `60000 paise` (`₹600.00`), Count: `2`, Chip: `verified`.
     - Dues: `85000 paise` (`₹850.00`) for customer `Vikram Singh`, Chip: `awaiting_approval`.
2. **`test_merchant_summary_unauthenticated_rejected`**:
   - Calls `GET /merchant/me/summary` without token.
   - Asserts clean HTTP 401 response.
3. **`test_merchant_chat_message_roundtrip`**:
   - Posts a query to `POST /merchant/chat/message`.
   - Asserts HTTP 200 response with `[Saathi Prototype · Phase 2]`, `sender: "saathi"`, and `is_synthetic: True`.
   - Verifies an `audit_events` row was recorded for `MERCHANT_CHAT_MESSAGE_RECEIVED` with `result: "RECEIVED"`.

---

### 3. Frontend Build & Typecheck Verification
- **Merchant Mobile (`apps/merchant-mobile`)**:
  - `pnpm exec tsc --noEmit` passed with 0 errors.
  - Implements pull-to-refresh (`RefreshControl`), live status cards with `StatusChipNative`, loading skeleton, error retry state, floating mic FAB, and full chat UI with backend round-trip communication.
- **Employee Web (`apps/employee-web`)**:
  - `pnpm --filter employee-web build` built cleanly with Vite (0 errors).
