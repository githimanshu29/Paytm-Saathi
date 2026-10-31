# Phase 5: The Fix Agent (Soundbox Voice Support) — Problems Encountered & Resolutions

## 1. SQLite DDL Limitation on Alter ForeignKey
- **Problem**: When creating migration `0003_add_device_telemetry_and_scheduled_jobs.py` to add `device_id` to the `tasks` table, SQLite threw `NotImplementedError: No support for ALTER of constraints in SQLite dialect` because SQLite's `ALTER TABLE` cannot add foreign key constraints dynamically.
- **Root Cause**: SQLite lacks native support for `ALTER TABLE ADD CONSTRAINT FOREIGN KEY`.
- **Resolution**: Added the `device_id` column as a nullable string (`sa.Column('device_id', sa.String(64), nullable=True)`) without an inline FK constraint in the batch migration, and verified column existence with SQLAlchemy `inspect(bind)` before adding to guarantee idempotent upgrades.

## 2. Seed Script Import Path Mismatch
- **Problem**: Running `reset_demo_data.py` failed with `ImportError: cannot import name 'hash_password' from 'app.api.auth'`.
- **Root Cause**: `hash_password` was originally refactored to `app.core.security` in Phase 1, but `seed_demo_data.py` had an outdated import from `app.api.auth`.
- **Resolution**: Updated the import in `backend/scripts/seed_demo_data.py` to `from app.core.security import hash_password`.

## 3. React Native TouchableOpacity Prop Error
- **Problem**: Running `tsc --noEmit` on `apps/merchant-mobile` failed with:
  `App.tsx: error TS2322: Property 'title' does not exist on type 'IntrinsicAttributes & TouchableOpacityProps'`.
- **Root Cause**: A `title="Speak to Saathi"` attribute was placed on the `TouchableOpacity` mic button instead of a child `<Text>` component.
- **Resolution**: Removed the non-standard `title` prop from `TouchableOpacity` in `apps/merchant-mobile/App.tsx`.

## 4. Serial Number Regex Hyphen Truncation
- **Problem**: The regex `r"(SB-[A-Z0-9]+|dev_[a-z0-9_]+)"` truncated serial numbers like `SB-DEL-404` at the second hyphen, capturing only `SB-DEL`.
- **Root Cause**: `[A-Z0-9]+` excluded the `-` character between `DEL` and `404`.
- **Resolution**:
  1. Updated the regex pattern in `backend/app/agents/fix.py` and `backend/app/agents/orchestrator.py` to `r"(SB-[A-Za-z0-9-]+|dev_[a-zA-Z0-9_]+)"`.
  2. Added resilient prefix-fallback matching in `MockDeviceAdapter` (`get_device_by_serial`, `get_device_diagnostics`, `flip_device_status`, `request_remote_restart`) using `Device.serial_number.ilike(f"{s}%")`.

## 5. Test State Mutation & DB Isolation
- **Problem**: Running the entire test suite caused `test_merchant_summary_authenticated` to fail because `test_fix_agent_online_device_resolves_verified` had mutated `SB-JAI-101`'s battery level in the shared test database from 88% to 92%. Similarly, `test_resolve_branch_b_stuck_reversal_creates_review_task` failed because an earlier test run had approved the task into the `EXECUTED` bucket.
- **Root Cause**: Pytest tests against SQLite share persisted database rows unless explicit cleanup or teardown is implemented.
- **Resolution**:
  1. Standardized `test_fix_agent.py` to use the baseline seeded battery percentage (88%) for `SB-JAI-101`.
  2. Added an explicit pre-test task cleanup in `test_resolve_branch_b_stuck_reversal_creates_review_task` to ensure deterministic execution regardless of run order.
