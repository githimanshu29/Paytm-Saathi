# Phase 5: The Fix Agent (Soundbox Voice Support) — Technical Architecture & Explanations

## 1. Overview & Business Context
Small merchants rely on Paytm Soundbox audio chimes for instant confirmation of customer UPI payments. When a Soundbox goes silent, blinks red, or loses cellular connectivity, the kirana merchant is blinded to payment confirmations during busy hours.

The **Fix Agent** acts as an AI hardware diagnostics specialist. It:
1. Listens to merchant descriptions via voice or text (in Indic languages like Hindi).
2. Diagnoses the issue using **authoritative device telemetry** (battery percentage, signal dBm, SIM registration status, firmware version, and last heartbeat).
3. Guides the merchant through basic physical troubleshooting (charging, power-button long press).
4. Dispatches simulated over-the-air (OTA) remote restart commands (`request_remote_restart`, R1).
5. **Never assumes the reboot succeeded**: executes a fresh status check. If the device remains offline or erroring, it books a physical technician visit with a real slot (`get_technician_slots`, R0 -> `create_technician_task`, R1).
6. Prevents duplicate booking through cryptographic and database-level idempotency guards.

---

## 2. Core Architecture & Components

```
                          ┌─────────────────────────────┐
                          │   Merchant Mobile App       │
                          │ (Voice Mic & Chat Interface)│
                          └──────────────┬──────────────┘
                                         │  POST /merchant/voice/chat
                                         │  POST /merchant/chat/message
                                         ▼
                          ┌─────────────────────────────┐
                          │   SaathiBrainOrchestrator   │
                          │   (Intent Router & Gateway) │
                          └──────────────┬──────────────┘
                                         │ (Device / Soundbox query)
                                         ▼
                          ┌─────────────────────────────┐
                          │          FixAgent           │
                          │   (LangGraph State Machine) │
                          └───────┬──────────────┬──────┘
                                  │              │
                   ┌──────────────▼───┐     ┌────▼─────────────┐
                   │    FixTools      │     │  SpeechAdapter   │
                   │ (Policy-Enforced)│     │  (STT & TTS)     │
                   └───────┬──────────┘     └──────────────────┘
                           │
      ┌────────────────────┼─────────────────────┐
      ▼                    ▼                     ▼
┌───────────────┐  ┌───────────────┐   ┌──────────────────┐
│ DeviceAdapter │  │ PolicyEngine  │   │ClockworkScheduler│
│(Authoritative)│  │(R0 / R1 Gates)│   │ (APScheduler+DB) │
└───────┬───────┘  └───────┬───────┘   └─────────┬────────┘
        │                  │                     │
        └──────────────────┼─────────────────────┘
                           ▼
                  ┌───────────────────┐
                  │ PostgreSQL/SQLite │
                  │  devices, tasks,  │
                  │  scheduled_jobs   │
                  └───────────────────┘
```

---

## 3. The Authoritative Telemetry Boundary & Anti-Hallucination Invariant
The single most critical safety requirement of the Fix Agent is:
> **The agent must NEVER assume a remote fix worked. It must NEVER claim "verified" when status is still offline.**

### How this is guaranteed:
1. `FixTools` queries `IDeviceAdapter.get_device_status()` and `get_device_diagnostics()`.
2. When a remote restart is requested, `request_remote_restart()` sends an OTA reboot packet and sets `reboot_in_progress = True`.
3. The agent then executes an **immediate fresh check** against the authoritative `DeviceAdapter`.
4. If `fresh_check.get("is_online")` is `False`, the agent:
   - Sets `chip_status = "needs_human"` (NEVER `"verified"`).
   - Retrieves available technician slots via `get_technician_slots()`.
   - Books a technician visit via `create_technician_task()`.
   - Returns a structured `TECHNICIAN_VISIT_BOOKED` action card for the UI.
5. Only if the fresh status check authoritatively returns `ONLINE` (e.g. after the demo toggle is flipped) does the agent transition to `chip_status = "verified"`.

---

## 4. Swappable Speech Adapter (`ISpeechAdapter`)
To support Hindi and Indic voice interactions seamlessly while allowing zero-friction upgrades to production Indian speech APIs (such as Sarvam AI, Bhashini, or Google Cloud Speech):
- Defined `ISpeechAdapter` protocol with `transcribe(audio_data, language_hint)` and `synthesize(text, language, voice)`.
- `MockSpeechAdapter` provides deterministic mock transcription and generates valid 44-byte WAV audio headers in base64, calculating duration based on conversational speaking cadence (~2.5 words per second).
- Returned payloads include `speech_audio_base64` and `speech_duration_seconds` for immediate audio playback in the merchant app.

---

## 5. Clockwork: Crash-Safe Background Job Scheduler
- In-process `APScheduler` wrapped in `ClockworkScheduler`.
- **Crash Safety**: When a delayed device recheck is scheduled (`schedule_device_recheck`), a row is committed to the database table `scheduled_jobs` with status `SCHEDULED`, run time, and parameters.
- When the backend boots or restarts, `recover_pending_jobs(db)` scans for uncompleted jobs. If overdue, they execute immediately; if in the future, they are re-registered in the background scheduler. No jobs are lost if the server process dies.

---

## 6. Double-Booking Guard & Idempotency
Technician visits represent field service costs. Double-dispatching technicians must be prevented:
- `create_technician_task` builds a deterministic SHA-256 idempotency key: `f"{execution_id}:CREATE_TECHNICIAN_TASK:{device_ref}:{params}"`.
- Before creating a new task, the tool queries existing active tasks under `TaskBucket.NEEDS_HUMAN` matching the device's serial number.
- If an active technician task is found:
  - It does NOT create a duplicate task.
  - Returns `is_duplicate_idempotent = True`, along with the existing `task_id` and assigned slot.
  - The agent informs the merchant: *"A Paytm technician visit is already confirmed for [Slot]."*

---

## 7. Interactive Demo Toggle
To empower hackathon judges, QA engineers, and live demoers to demonstrate both branches:
- Exposed `POST /demo/device/{serial_number}/toggle` (public demo endpoint).
- Exposed `POST /merchant/device/{serial_number}/toggle-status` (authenticated merchant endpoint).
- Flipping an offline device (`SB-DEL-404`) to `ONLINE` instantly updates battery to 95%, signal to -65 dBm, and records a fresh heartbeat.
- Asking Saathi to re-check the device immediately flips the outcome from `needs_human` to `verified`!
