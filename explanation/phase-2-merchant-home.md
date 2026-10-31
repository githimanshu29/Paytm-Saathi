# Phase 2: Architectural Explanations & Core Concepts

### 1. Database-Backed Merchant Summary (`GET /merchant/me/summary`)
The merchant home screen is not hardcoded; it dynamically queries authoritative database rows linked to the authenticated merchant's identity:
1. **Device Telemetry (`devices` table):**
   - Retrieves active hardware (Soundbox 4G Pro `SB-JAI-101`), battery level (88%), and maps operational statuses (`ONLINE` -> `verified`, `ERROR` -> `needs_human`, `OFFLINE` -> `awaiting_approval`).
2. **Payments & Collections (`transactions` table):**
   - Sums all successful transactions in minor units (paise) for the day (`15000 + 45000 = 60000 paise` / `₹600.00`).
   - Retrieves itemized recent transactions with UPI rail references and customer names.
3. **Receivables & Customer Udhaar (`receivables` & `customers` tables):**
   - Identifies unpaid customer dues (`85000 paise` / `₹850.00` for Vikram Singh), mapping status to `awaiting_approval` for proactive reminder management.

### 2. StatusChip Integration Across Both Platforms
The mobile app directly renders `StatusChipNative` imported from the shared `@paytm-saathi/design-tokens` package:
- Device health: `StatusChipNative status="verified"` (green)
- Payment reconciliation: `StatusChipNative status="verified"` (green)
- Pending customer udhaar: `StatusChipNative status="awaiting_approval"` (orange)
This enforces semantic consistency between what the merchant sees on mobile and what the Paytm support team sees in the Control Tower.

### 3. End-to-End Chat Wireframe (`POST /merchant/chat/message`)
Before activating complex LangGraph orchestrator workflows in Phase 3, Phase 2 establishes the end-to-end communication conduit between the merchant mobile chat UI and the Python FastAPI backend:
- Tapping the floating mic FAB (`"Talk to Saathi"`) or the bottom Chat tab opens the chat interface.
- Merchant inputs a query (e.g. `"How is my Soundbox battery doing?"`).
- The message is sent to `/merchant/chat/message` with JWT Bearer authentication.
- The backend logs the chat query to `audit_events` and returns a structured response with a clearly-labeled canned prototype message:
  `"[Saathi Prototype · Phase 2] Namaste Sharma Kirana Store! I received your message: \"...\". Multi-agent autonomous coordination will activate in upcoming phases..."`
- The UI appends the response to the chat stream with sender timestamp and bubble styling.
