# Phase 0: Architectural Explanations & Core Concepts

### 1. Security Boundary: Policy Engine Over Prompts
- **Why this matters:** Large Language Models are probabilistic and prone to prompt injections, hallucinations, and unauthorized actions.
- **Implementation:** `PolicyEngine.evaluate(proposal: ActionProposal) -> PolicyDecision`. 
- **Risk Tiers:**
  - `R0`: Read-only queries (auto-allowed).
  - `R1`: Internal/reversible tasks (auto-allowed, audited).
  - `R2`: External actions/bookings (requires merchant or manager consent).
  - `R3`: Regulated financial actions (disabled in prototype; creates human review task).
  - `R4`: Prohibited actions (strictly blocked and logged).
- **Rule:** The LLM only *proposes* an `ActionProposal`. No tool or agent may execute a side-effecting action without an affirmative `allowed=true` decision from the deterministic `PolicyEngine`.

### 2. Minor Unit Financial Precision (Paise)
- **Why this matters:** Storing currency as floating-point numbers (`float` or `double`) leads to rounding errors (`0.1 + 0.2 = 0.30000000000000004`), which is unacceptable in financial accounting and reconciliation.
- **Implementation:** All amounts in `transactions` and `receivables` are strictly stored as 64-bit integers representing paise (`1 INR = 100 paise`). For example, ₹150.00 is stored as `15000`.

### 3. Synthetic Data Governance
- **Why this matters:** In this hackathon prototype, all external systems (Paytm APIs, banks, telecom SIMs, Soundboxes) are simulated.
- **Implementation:** Every record in the database includes:
  - `is_synthetic: Boolean (True)`
  - `environment: String ("DEMO")`
  This prevents any synthetic record from ever being mistaken for real merchant data or production financial claims.

### 4. Cross-Platform StatusChip Component
- **Why this matters:** Both the mobile app (Expo/React Native) and the employee web app (React DOM) must share identical design tokens and status chips without code duplication.
- **Implementation:** `packages/design-tokens` provides:
  - `StatusChip.tsx`: Native Web component using semantic HTML and inline styling.
  - `StatusChipNative.tsx` & `StatusChip.native.tsx`: React Native component dynamically rendering `View` and `Text` primitives.
  - Metro automatically resolves the `.native.tsx` variant for mobile, while Vite bundles the `.tsx` variant for web.
