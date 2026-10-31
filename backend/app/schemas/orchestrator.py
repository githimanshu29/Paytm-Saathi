from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentRoute(str, Enum):
    """
    Deterministic routing destination for Saathi Brain.
    Strictly enforced enum — any unlisted route string is rejected.
    """
    RESOLVE = "RESOLVE"
    FIX = "FIX"
    RECONCILE = "RECONCILE"
    REVIVE = "REVIVE"
    ONBOARD = "ONBOARD"
    FIELDMATE = "FIELDMATE"
    VASOOLI = "VASOOLI"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    UNCLEAR = "UNCLEAR"


class WorkflowStatus(str, Enum):
    """
    Master Context workflow contract status lifecycle.
    """
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    MAX_ITERATIONS_REACHED = "MAX_ITERATIONS_REACHED"


class RouteClassificationResult(BaseModel):
    route: AgentRoute
    confidence: float = 1.0
    reasoning: str
    is_safe: bool = True
    flagged_patterns: List[str] = Field(default_factory=list)


class HandoffStepRequest(BaseModel):
    step: int = Field(..., ge=1, le=6, description="Step 1 to 6 in the cross-agent chain")
    merchant_id: str = "mer_singh_automobiles"
    actor_id: str = "demo_narrator"


class HandoffStepResponse(BaseModel):
    step: int
    step_name: str
    active_agent: str
    summary: str
    details: Dict[str, Any] = Field(default_factory=dict)
    next_step: Optional[int] = None
    is_complete: bool = False
    audit_event_id: Optional[str] = None


class HandoffChainStatusResponse(BaseModel):
    merchant_id: str
    current_step: int
    is_running: bool = False
    completed_steps: List[Dict[str, Any]] = Field(default_factory=list)
    merchant_health: str = "AT_RISK"
    device_status: str = "OFFLINE"
    visit_status: str = "NOT_SCHEDULED"
    revival_stage: str = "AT_RISK"
