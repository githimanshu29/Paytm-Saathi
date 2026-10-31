import hashlib
import json
import uuid
from typing import Any, Dict, Optional, Set
from sqlalchemy.orm import Session

from app.schemas.orchestrator import WorkflowStatus
from app.policy.audit import audit_log


class WorkflowLimitExceededError(Exception):
    """Raised when a bounded-loop limit is breached."""
    pass


class DuplicateActionBlockedError(Exception):
    """Raised when an action with the exact same canonical signature is retried."""
    pass


class WorkflowContext:
    """
    Enforces the shared Master Context workflow contract across all Saathi agents:
    1. Bounded-loop ceilings:
       - max 5 planner loops
       - max 6 delegations
       - max 12 tool calls
       - max 2 retries
    2. Repeated-action idempotency guard:
       hash(execution_id + action_type + target_id + canonical_params)
    3. Failure contract:
       Ceilings reached without verified progress resolve to NEEDS_HUMAN_REVIEW (never silent COMPLETED).
    """

    MAX_PLANNER_LOOPS: int = 5
    MAX_DELEGATIONS: int = 6
    MAX_TOOL_CALLS: int = 12
    MAX_RETRIES: int = 2

    def __init__(
        self,
        execution_id: Optional[str] = None,
        db: Optional[Session] = None,
        merchant_id: Optional[str] = None,
        actor_id: str = "orchestrator",
    ):
        self.execution_id = execution_id or f"exec_wf_{uuid.uuid4().hex[:10]}"
        self.db = db
        self.merchant_id = merchant_id
        self.actor_id = actor_id
        self.status: WorkflowStatus = WorkflowStatus.RUNNING

        # Counters
        self.planner_loop_count: int = 0
        self.delegation_count: int = 0
        self.tool_call_count: int = 0
        self.retry_count: int = 0

        # Repeated-action side-effect guard
        self._executed_action_hashes: Set[str] = set()

    def record_planner_loop(self) -> None:
        """Increment planner loop counter; enforce bounded loop limit."""
        self.planner_loop_count += 1
        if self.planner_loop_count > self.MAX_PLANNER_LOOPS:
            self._handle_ceiling_breach(
                limit_name="max_planner_loops",
                limit_val=self.MAX_PLANNER_LOOPS,
                current_val=self.planner_loop_count,
            )

    def record_delegation(self, target_agent: str) -> None:
        """Increment agent delegation counter; enforce bounded delegation limit."""
        self.delegation_count += 1
        if self.delegation_count > self.MAX_DELEGATIONS:
            self._handle_ceiling_breach(
                limit_name="max_delegations",
                limit_val=self.MAX_DELEGATIONS,
                current_val=self.delegation_count,
            )

    def record_tool_call(self, tool_name: str) -> None:
        """Increment tool call counter; enforce bounded tool call limit."""
        self.tool_call_count += 1
        if self.tool_call_count > self.MAX_TOOL_CALLS:
            self._handle_ceiling_breach(
                limit_name="max_tool_calls",
                limit_val=self.MAX_TOOL_CALLS,
                current_val=self.tool_call_count,
            )

    def record_retry(self, reason: str = "") -> None:
        """Increment retry counter; enforce bounded retry limit."""
        self.retry_count += 1
        if self.retry_count > self.MAX_RETRIES:
            self.status = WorkflowStatus.FAILED_TERMINAL
            if self.db:
                audit_log(
                    db=self.db,
                    actor=self.actor_id,
                    action="WORKFLOW_MAX_RETRIES_BREACHED",
                    target=self.execution_id,
                    result="FAILED_TERMINAL",
                    policy_decision_id="dec_wf_max_retries",
                )
            raise WorkflowLimitExceededError(
                f"Maximum retry limit ({self.MAX_RETRIES}) reached for workflow {self.execution_id}."
            )

    def check_and_record_action(
        self,
        action_type: str,
        target_id: str,
        parameters: Dict[str, Any],
    ) -> str:
        """
        Enforce repeated-action guard keyed on:
        hash(execution_id + action_type + target_id + canonical_params)
        Blocks duplicate side effects on retries.
        """
        canonical_params = json.dumps(parameters, sort_keys=True)
        raw_key = f"{self.execution_id}:{action_type}:{target_id}:{canonical_params}"
        action_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        if action_hash in self._executed_action_hashes:
            if self.db:
                audit_log(
                    db=self.db,
                    actor=self.actor_id,
                    action="DUPLICATE_ACTION_BLOCKED",
                    target=f"{action_type}:{target_id}",
                    result="BLOCKED_BY_GUARD",
                    idempotency_key=action_hash[:16],
                    policy_decision_id="dec_dup_action_guard",
                )
            raise DuplicateActionBlockedError(
                f"Duplicate side-effect action {action_type} on target {target_id} blocked by idempotency guard."
            )

        self._executed_action_hashes.add(action_hash)
        return action_hash

    def mark_completed(self, has_warnings: bool = False) -> None:
        if self.status != WorkflowStatus.NEEDS_HUMAN_REVIEW and self.status != WorkflowStatus.MAX_ITERATIONS_REACHED:
            self.status = WorkflowStatus.COMPLETED_WITH_WARNINGS if has_warnings else WorkflowStatus.COMPLETED

    def mark_waiting_for_approval(self) -> None:
        self.status = WorkflowStatus.WAITING_FOR_APPROVAL

    def escalate_to_human(self, reason: str) -> None:
        self.status = WorkflowStatus.NEEDS_HUMAN_REVIEW
        if self.db:
            audit_log(
                db=self.db,
                actor=self.actor_id,
                action="WORKFLOW_ESCALATED_TO_HUMAN",
                target=self.merchant_id or self.execution_id,
                result="NEEDS_HUMAN_REVIEW",
                policy_decision_id="dec_wf_human_review",
            )

    def _handle_ceiling_breach(self, limit_name: str, limit_val: int, current_val: int) -> None:
        # Invariant: A workflow hitting loop/tool ceiling without verified progress
        # ends in NEEDS_HUMAN_REVIEW, NEVER silent COMPLETED.
        self.status = WorkflowStatus.NEEDS_HUMAN_REVIEW
        if self.db:
            audit_log(
                db=self.db,
                actor=self.actor_id,
                action="WORKFLOW_BOUNDED_LOOP_LIMIT_EXCEEDED",
                target=f"{limit_name}:{current_val}>{limit_val}",
                result="NEEDS_HUMAN_REVIEW",
                policy_decision_id="dec_wf_bounded_loop",
            )
        raise WorkflowLimitExceededError(
            f"Bounded-loop limit exceeded: {limit_name} breached ({current_val} > {limit_val}). "
            f"Workflow escalated to NEEDS_HUMAN_REVIEW."
        )
