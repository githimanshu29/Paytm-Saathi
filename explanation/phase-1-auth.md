# Phase 1: Architectural Explanations & Core Concepts

### 1. Dual Independent Authentication Flows Sharing One Backend
Paytm Saathi supports two distinct personas that share the same backend orchestrator:
1. **Kirana Merchants (`POST /auth/merchant/request-otp` & `POST /auth/merchant/verify-otp`):**
   - Small shopkeepers and Soundbox merchants authenticate using a frictionless Phone + OTP flow.
   - For demo fidelity, requesting an OTP logs the fixed code (`123456`) to the console and responds with a simulation message.
   - Upon verification, an authoritative JWT token is generated with `user_type: "merchant"` and `role: "merchant"`, bound to the merchant record.
2. **Paytm Employees (`POST /auth/employee/login`):**
   - Support agents, managers, field sales reps, and admins authenticate using email + bcrypt-hashed password credentials.
   - Issues a JWT token containing `user_type: "employee"` and their specific role (`support_agent`, `manager`, `sales_rep`, `admin`).

### 2. JWT Claims Structure & Role Boundary
All issued access tokens contain strict, deterministic claims:
```json
{
  "sub": "emp_support_01",
  "user_type": "employee",
  "role": "support_agent",
  "email": "support@paytm.demo",
  "name": "Rajesh Sharma",
  "tenant_id": "tenant_paytm_demo",
  "iat": 1730212000,
  "exp": 1730298400
}
```
Downstream agents, tools, and the `PolicyEngine` verify these claims to enforce role-based access control and prevent privilege escalation (e.g., merchants cannot call employee review endpoints, and sales reps cannot bypass manager approval gates).

### 3. Route Protection & Automatic Session Expiration
- Both frontends protect their workspace routes:
  - If no token is present, the app renders the Login screen (`PHONE_ENTRY` on mobile, Login card on web).
  - On launch, the apps ping `GET /auth/me` with the stored `Bearer <token>`.
  - If the token is invalid or expired, the backend returns HTTP 401, causing the client to clear stored tokens and redirect to login.
- Logout immediately invalidates local storage and in-memory tokens, safely returning to the unauthenticated state.

### 4. Audit Logging of Authentication Events
Every authentication attempt (both successful logins and failed OTP / password attempts) is captured in `audit_events` via `audit_log()`:
- `MERCHANT_OTP_REQUESTED`
- `MERCHANT_LOGIN_SUCCESS`
- `MERCHANT_OTP_VERIFY_FAILED`
- `EMPLOYEE_LOGIN_SUCCESS`
- `EMPLOYEE_LOGIN_FAILED`
This maintains a tamper-evident log of all access activity.
