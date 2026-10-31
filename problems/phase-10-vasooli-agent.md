# Phase 10: The Vasooli Agent (Receivable Reminders) - Problems & Challenges

## 1. Regulatory & Ethical Boundary: Store Credit vs Debt Collection
- **Hard Boundary**: Vasooli means consensual **RECEIVABLE TRACKING** (merchant's informal *udhaar* / store khata ledger) and polite customer reminders. It is **NOT** regulated loan recovery, debt collection, or NBFC collection agency work.
- **Risks**:
  - Unregulated harassment or intimidation of customers.
  - Violating consumer protection norms and RBI Fair Practices Code for digital debt collection.
  - Damaging long-term trust between local neighbourhood kirana merchants and their patrons.
- **Architectural Guardrail**:
  - Hardcoded anti-coercion policy filters (`BANNED_PHRASES`).
  - Mandatory customer communication permission gate (`get_contact_permission`).
  - Active dispute freeze (`is_disputed == True` halts all automated contact).
  - Maximum attempt ceiling (strictly capped at 3 polite reminders).

## 2. Coercive Language & Threat Elimination
- **Challenge**: LLMs naturally drift into aggressive, coercive, or high-pressure language when prompted to "recover money" or "collect debt" (e.g., using terms like "legal notice", "final warning", "police report", "blacklisted").
- **Solution**:
  - Enforced deterministic string scanning for 14 prohibited coercive patterns across English and Hindi before any message is drafted or dispatched:
    - *English*: `police`, `jail`, `arrest`, `court`, `legal notice`, `threat`, `defaulter`, `penalty fee`, `recovery agent`, `blacklisted`, `final warning`.
    - *Hindi*: `giraftari`, `kanooni karwayi`, `police report`.
  - Violations raise `VasooliPolicyViolationError` (`R4_COERCIVE_LANGUAGE_BLOCKED`) and are logged to `audit_events`.
  - Prompts are constrained to templated polite phrasing with courteous greetings (*"Namaste... yeh ek vinamra anurodh hai"*).

## 3. Communication Consent & Revocation Handling
- **Challenge**: Merchants may attempt to message customers who have explicitly opted out or revoked permission to receive digital reminders.
- **Solution**:
  - Customer table stores granular consent flags: `contact_permission` (boolean) and `permission_status` (`ALLOWED`, `REVOKED`, `OPTED_OUT`).
  - Every draft and send tool call executes `get_contact_permission` first.
  - If revoked, the agent **visibly refuses** outreach with an explanation: *"Outreach refused: Customer Sunita Devi has explicitly opted out or revoked communication consent."*

## 4. Disputed Receivables & Halting Outreach
- **Challenge**: Store credit records can be erroneous (e.g., customer claims they already paid in cash, or dispute item quantity). Sending payment demands to a customer with a contested bill causes customer friction.
- **Solution**:
  - Each `Receivable` record tracks `is_disputed` (boolean) and `dispute_reason`.
  - Any active dispute immediately halts outreach: *"Outreach refused: Receivable for Manish Gupta is currently marked as disputed (Item returned). Automated reminders are paused."*

## 5. False Settlement Claims vs Authoritative Payment Verification
- **Challenge**: A merchant or customer might verbally claim in chat *"Ramesh paid yesterday"* or *"Payment done"*. Marking receivables as settled without proof leads to fraudulent accounting and bookkeeping sync errors.
- **Solution**:
  - The agent **never** marks a receivable settled based solely on unstructured chat text.
  - Settlements require an authoritative payment event (`is_authoritative = True`), carrying a verifiable bank transaction reference or webhook signal (`POST /demo/vasooli/payment-event`).
  - Receivables maintain an explicit verification state (`settlement_verification_status`: `PENDING`, `VERIFIED_PAID`, `MANUAL_REVIEW`).

## 6. Payment Arrival Race Condition & Auto-Stop Invariant
- **Challenge**: A customer might pay via UPI or QR code while a reminder draft or merchant approval is queued in the system. Sending a payment reminder *after* the customer has already paid is embarrassing and damages merchant credibility.
- **Solution**:
  - The moment an authoritative payment event arrives (`record_payment_status`), the system triggers an atomic **auto-stop**:
    1. Sets receivable status to `PAID` with timestamp and bank reference.
    2. Identifies all pending `ActionApproval` records linked to that `receivable_id`.
    3. Auto-cancels pending approvals with note: `"AUTO_CANCELLED: Payment arrived before reminder was sent."`.
    4. Prohibits any future reminder dispatch.

## 7. Partial Payment & Installment Negotiation
- **Challenge**: Customers frequently cannot pay the entire store credit balance at once and request installment splits.
- **Solution**:
  - Built `split_negotiator` node and `negotiate_split_installment` tool.
  - Divides outstanding balance into structured integer minor unit (paise) installments.
  - Saves negotiated plan to `receivables.negotiated_installments` and creates an `ActionApproval` for merchant sign-off before committing to the adjusted timeline.
