# Problems and Solutions: Phase 4 — The Resolve Agent (Failed Payment)

## 1. Idempotency Return Payload Missing `approval_id`
- **Issue**: In `ResolveTools.request_refund_review()`, when an existing task was found matching the transaction reference (idempotency check), the method returned `is_duplicate_idempotent=True` with `task_id`, but omitted `approval_id`. When the agent generated an `approval_card` for the merchant UI or test suite, `approval_card["approval_id"]` was `None`. Consequently, attempting to decide on the approval called `POST /merchant/approvals/None/decide`, returning HTTP 404.
- **Root Cause**: The idempotency branch in `request_refund_review` only queried `Task` and returned `task.id` without querying the linked `ActionApproval` table.
- **Fix**: Added `existing_appr = self.db.query(ActionApproval).filter_by(task_id=existing_task.id).first()` in the idempotency return block and passed `approval_id=existing_appr.id if existing_appr else f"appr_{existing_task.id}"`.

## 2. Baseline Payment Collections Count in Existing Tests
- **Issue**: `tests/test_merchant.py::test_merchant_summary_authenticated` failed with `AssertionError: assert 92000 == 60000` and `assert 3 == 2`.
- **Root Cause**: Phase 4 added scenario transaction `txn_success_confirmed` (₹320.00 / 32,000 paise) to the demo seed dataset for `mer_sharma_kirana` to enable Branch C verification ("payment actually succeeded"). Sharma Kirana now legitimately has 3 successful transactions totaling ₹920.00 rather than 2 totaling ₹600.00.
- **Fix**: Updated `test_merchant.py` assertions to align with the seeded dataset (92,000 paise across 3 transactions).

## 3. Policy Boundary: R3 Direct Financial Action Prevention
- **Issue**: Risk of autonomous agents hallucinating or directly triggering monetary refunds upon merchant or customer complaint.
- **Root Cause**: In traditional LLM agent systems, models given tool calling may invoke refund APIs based on conversational prompts.
- **Fix**: Implemented strict architectural separation:
  - Allowed: `request_refund_review` (R1 Internal Review Task in `awaiting_approval` bucket).
  - Prohibited: `execute_refund` (R3 Regulated Financial Action). Calling this tool explicitly queries `PolicyEngine`, which returns `allowed=False`, records an `EXECUTE_REFUND_BLOCKED` audit trail event with `result="BLOCKED_BY_POLICY"`, and blocks execution.

## 4. Pydantic v2 `dict()` Deprecation Warnings
- **Issue**: Pydantic v2 emits `PydanticDeprecatedSince20: The dict method is deprecated; use model_dump instead`.
- **Fix**: Replaced `.dict()` with `.model_dump()` in `app/tools/resolve.py`.
