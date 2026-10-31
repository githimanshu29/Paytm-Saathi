# Phase 1: Problems Encountered & Resolutions

### 1. Inconsistent Password Hashes in Initial Seed vs. Bcrypt Verification
- **Problem:** In Phase 0, the seed script used dummy mock hash strings (`"$2b$12$eMockHashedPassword..."`). Attempting to verify passwords against these placeholders via `bcrypt.checkpw()` caused verification failures and invalid salt format exceptions.
- **Resolution:** Updated `backend/scripts/seed_demo_data.py` to import `hash_password` from `app.core.security`. All seeded employees (`support@paytm.demo`, `manager@paytm.demo`, `sales@paytm.demo`, `admin@paytm.demo`) are now initialized with real bcrypt-hashed passwords using `Demo@1234`. Executed `reset_demo_data.py` to re-seed cleanly.

### 2. Universal Storage Support Across Expo Web and React Native Native Runtimes
- **Problem:** Native mobile apps use `AsyncStorage`, while web environments use `localStorage`. Attempting a direct hardcoded access to `window.localStorage` can throw exceptions in non-web native JS runtimes.
- **Resolution:** Wrapped client token access in safe environment checks (`typeof window !== 'undefined' && window.localStorage`) with in-memory React state fallbacks, ensuring reliable token storage and route redirection across web previews, Metro, and mobile devices.

### 3. Graceful 401 Rejections Without Stack Traces
- **Problem:** Unhandled token decode exceptions (`jwt.ExpiredSignatureError`, `jwt.PyJWTError`) can bubble up into uncaught 500 internal server errors with python tracebacks.
- **Resolution:** Built explicit exception handlers in `app/core/security.py:decode_access_token` and FastAPI dependency `get_current_user` in `app/api/auth.py`, intercepting expired or malformed tokens and immediately returning a clean HTTP 401 response with standard `WWW-Authenticate: Bearer` headers.
