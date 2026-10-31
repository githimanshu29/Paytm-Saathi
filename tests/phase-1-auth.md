# Phase 1: Test Execution & Verification Evidence

### 1. Pytest Test Results
Command: `uv run pytest tests/test_auth.py`
```text
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\Himanshu Kumar\Desktop\Paytm-Saathi\backend
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1, asyncio-1.4.1
collected 8 items

tests\test_auth.py ........                                              [100%]

======================= 8 passed in 5.82s =======================
```

Full Test Suite Run: `uv run pytest`
```text
collected 14 items

tests\test_auth.py ........                                              [ 57%]
tests\test_health.py .                                                   [ 64%]
tests\test_seed_invariants.py .....                                      [100%]

======================= 14 passed in 9.02s =======================
```

### 2. Verified Test Cases
1. **`test_merchant_otp_request_and_verify_flow`**:
   - Sends `POST /auth/merchant/request-otp` with phone `+919876543210` -> receives 200 with demo OTP notification.
   - Sends `POST /auth/merchant/verify-otp` with OTP `123456` -> receives 200 with JWT bearer token and merchant details.
   - Pings protected `GET /auth/me` with `Bearer <token>` -> receives 200 and merchant profile (`role: "merchant"`).
2. **`test_merchant_otp_verify_invalid_code`**:
   - Sends `POST /auth/merchant/verify-otp` with incorrect OTP `999999` -> rejects with clean HTTP 401 (`"Invalid or expired OTP"`).
3. **`test_employee_login_all_seeded_roles`**:
   - Tests `support@paytm.demo` (role: `support_agent`) with password `Demo@1234` -> receives 200 and valid JWT.
   - Tests `manager@paytm.demo` (role: `manager`) with password `Demo@1234` -> receives 200 and valid JWT.
   - Tests `sales@paytm.demo` (role: `sales_rep`) with password `Demo@1234` -> receives 200 and valid JWT.
   - Tests `admin@paytm.demo` (role: `admin`) with password `Demo@1234` -> receives 200 and valid JWT.
4. **`test_employee_login_invalid_password`**:
   - Tests `support@paytm.demo` with wrong password -> rejects with clean HTTP 401 (`"Invalid email or password"`).
5. **`test_employee_login_nonexistent_email`**:
   - Tests unseeded email `ghost@paytm.demo` -> rejects with clean HTTP 401.
6. **`test_protected_route_rejects_missing_token`**:
   - Calls `GET /auth/me` without Authorization header -> rejects with clean HTTP 401 (`"Missing or malformed Authorization header"`).
7. **`test_protected_route_rejects_invalid_token`**:
   - Calls `GET /auth/me` with invalid token -> rejects with clean HTTP 401 (`"Invalid token"`).
8. **`test_protected_route_rejects_expired_token`**:
   - Calls `GET /auth/me` with expired JWT (`exp` in the past) -> rejects with clean HTTP 401 (`"Token has expired"`).

---

### 3. Frontend Verification
- **Employee Web (`apps/employee-web`)**:
  - `pnpm --filter employee-web build` built cleanly with Vite.
  - Features dedicated Login screen with quick-select seeded demo accounts (`support@paytm.demo`, `manager@paytm.demo`, `sales@paytm.demo`), JWT token storage in `localStorage`, route protection redirecting invalid tokens to login, and a working **Sign Out** button.
- **Merchant Mobile (`apps/merchant-mobile`)**:
  - `pnpm exec tsc --noEmit` passed with 0 errors.
  - Implements 3-step state machine: `PHONE_ENTRY` (with default `9876543210`) -> `OTP_ENTRY` (with default `123456`) -> authenticated `HOME` dashboard with merchant store name, phone, StatusChips, and a working **Sign Out** button.
