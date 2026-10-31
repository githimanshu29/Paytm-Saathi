# Phase 9: The FieldMate Agent (Field Sales Copilot) - Problems & Challenges

## 1. UI Placement Dilemma & Authentication Boundary
- **Question**: Where should the field sales rep's UI live — a role-switched screen inside `merchant-mobile` or a rep view inside `employee-web`?
- **Trade-off Analysis**:
  - *Option A (`merchant-mobile`)*: Putting employee functionality inside the merchant mobile app contaminates merchant authentication, complicates OTP-based auth with corporate password auth, and risks leaking internal territory management logic to store owners.
  - *Option B (`employee-web`)*: An authenticated employee console maintaining strict JWT RBAC boundaries (`sales_rep` vs `manager` vs `support_agent`). Mobile-responsive layout allows reps to use it on mobile browsers while on the move, while managers review territory summaries in the exact same Control Tower ecosystem.
- **Decision**: Implemented as **Rep Route Console inside `employee-web`** with persona switcher for seamless live demonstration between Amit Verma (`sales_rep`) and Pooja Malhotra (`manager`).

## 2. Hallucinated Travel Times & Fake Optimal Routes
- **Challenge**: LLMs tend to invent minute-by-minute traffic predictions and claim mathematically "optimal" traveling salesperson routes without live GPS traffic telemetry.
- **Solution**:
  - Implemented deterministic **Haversine great-circle distance** in km based on seeded Jaipur coordinates.
  - Designed `suggest_visit_order` as an explicit **heuristic priority recommendation** balancing urgency priority (HIGH > MEDIUM > LOW) and distance.
  - Clearly displayed disclaimers in API responses and frontend: *"Route is a heuristic priority recommendation, not a guaranteed-optimal route."*

## 3. Truthful Briefs vs Hallucinated Pitches
- **Challenge**: Generative models easily invent reasons for visiting a merchant (e.g. inventing that a merchant wants a loan or that a soundbox was dropped).
- **Solution**:
  - Implemented `get_merchant_brief` strictly reading authoritative DB records:
    1. Real `Device` telemetry (`status == "OFFLINE"`, battery %) $\to$ hardware check.
    2. Real `MerchantDocument` status (`MISSING`, `BLURRY`) $\to$ physical document collection.
    3. Real `MerchantActivityMetric` decline ($\ge 40\%$) $\to$ Kirana Booster retention offer.
    4. Real KYC completion $\to$ physical storefront signboard check.
    5. Healthy transaction volume $\to$ Merchant Growth Loan upsell.

## 4. Voice Note Auto-Saving vs Mandatory Confirmation Gate
- **Challenge**: Auto-saving AI-transcribed notes directly to the CRM leads to erroneous commitments, incorrect interest tags, and compliance hazards.
- **Core Invariant**: **Zero unconfirmed persistence**.
  - Voice notes transcribed and processed by AI return an **UNCONFIRMED CANDIDATE DRAFT** (`requires_rep_confirmation = True`).
  - The database leaves `is_confirmed_by_rep = False` and `confirmed_notes = None`.
  - The record is persisted and audited only when the sales rep explicitly reviews, edits, and submits confirmation.

## 5. Concurrent Session Overwrite Hazards
- **Challenge**: In field operations, two concurrent rep sessions (or a background sync job and a rep note submission) could silently overwrite each other's visit updates.
- **Solution**:
  - Added an integer `version` column to `merchant_visits` for **Optimistic Concurrency Control**.
  - Every update checks `WHERE id = :id AND version = :expected_version`.
  - Stale versions raise `ConcurrencyConflictError` (HTTP 409 Conflict), blocking silent data corruption and prompting the rep to refresh.

## 6. Prohibited Financial & Loan Disbursal Actions
- **Challenge**: Sales reps might attempt to promise guaranteed financing or auto-approve loan terms.
- **Solution**:
  - Strictly enforced in `FieldMateTools` and adapter: any note containing "loan approved", "sanctioned", or "credit guaranteed" is blocked with `POLICY_VIOLATION`. Financing terms require formal risk underwriting review.
