# Phase 8: The Onboard Agent (KYC Closer & Document Verification) — Problems & Pitfalls

## 1. Problem Statement
Small merchant onboarding in India suffers from high drop-off rates due to vague KYC rejection messages (e.g., "Documents rejected. Contact branch"). Kirana owners frequently abandon signups when an illegible or blurry photo is submitted without immediate, specific guidance on which document failed and how to rectify it.

Simultaneously, building autonomous AI onboarding poses severe safety and compliance risks:
1. **The Probabilistic OCR Trap**: OCR models frequently make confident errors on glare, skewed angles, or cropped documents. Allowing OCR extraction or LLMs to set `kyc_status = VERIFIED` directly creates major regulatory non-compliance.
2. **Credential Phishing & Exfiltration**: Unscrupulous or hallucinating conversational agents might prompt merchants for sensitive banking credentials (e.g., passwords, OTPs, or UPI PINs).
3. **Premature Activation**: Activating Soundbox payment acceptance before authorized external verification (such as NSDL PAN validation or bank penny-drop) exposes the platform to fraud.

## 2. Core Invariants & Architectural Constraints
- **Invariant 1: OCR Output is UNTRUSTED Candidate Data**: Extracted OCR fields are treated as candidate metadata with `untrusted: True`. Neither OCR confidence nor LLM judgment alone can mark KYC verified or activate the merchant.
- **Invariant 2: Simulated Authorized Verification Gate**: A merchant's status transitions to `ACTIVE` and `kyc_status = VERIFIED` **only** after executing a simulated authorized external verification step (NSDL PAN database & Penny-drop verification).
- **Invariant 3: Actionable, Specific Rejection Reasons**: The agent must identify and chase the exact missing or degraded document with specific instructions ("Your PAN card photo is blurry and illegible. Please resend a sharp, well-lit photo" — never a generic error).
- **Invariant 4: Credential Security Guardrail**: Asking for passwords, OTPs, or UPI PINs is an explicit security violation. Any query soliciting credentials is halted immediately with a security alert.

## 3. Disallowed Actions
- Setting `kyc_status = 'VERIFIED'` or `status = 'ACTIVE'` directly from OCR extraction or LLM completion.
- Generic document rejection without pinpointing the exact document and flaw.
- Requesting passwords, OTPs, or UPI PINs from the user.
