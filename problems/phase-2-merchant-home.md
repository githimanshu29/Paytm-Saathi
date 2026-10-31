# Phase 2: Problems Encountered & Resolutions

### 1. TypeScript Primitive Typo (`int` vs `number`)
- **Problem:** When declaring `interface DeviceSummary` in `apps/merchant-mobile/App.tsx`, `battery_level: int;` was used instead of `number`. TypeScript threw `error TS2304: Cannot find name 'int'`.
- **Resolution:** Replaced `int` with standard TypeScript `number`. `tsc --noEmit` then succeeded with zero errors.

### 2. Graceful Error Presentation Without Exposing Backend Tracebacks
- **Problem:** If the backend is temporarily offline or an unauthenticated 401 occurs during the summary call, naive UI implementations often crash or display raw JSON stack traces to kirana merchants.
- **Resolution:** Implemented friendly, plain-language error handling with a retry button (`"Unable to load your live store summary. Please check your network and tap Retry."`) and automatic token clearance/redirect if the server responds with a 401 unauthorized status.

### 3. Minor Unit (Paise) Conversion for Display
- **Problem:** In accordance with the system design, all money is stored in integer minor units (paise). Displaying raw integers like `60000` or `85000` directly in the UI would confuse merchants.
- **Resolution:** Built server-side formatting utilities (`format_paise_to_inr(paise: int) -> str`) yielding both raw integer minor units (`today_total_paise: 60000`) for deterministic accounting and human-friendly formatted values (`today_total_formatted: "₹600.00"`) for direct UI rendering.
