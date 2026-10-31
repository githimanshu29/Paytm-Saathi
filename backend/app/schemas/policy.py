import enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class RiskTier(str, enum.Enum):
    R0 = "R0"  # Read-only (auto-allowed)
    R1 = "R1"  # Internal / reversible (auto-allowed, audited)
    R2 = "R2"  # External communication / booking (needs approval/consent)
    R3 = "R3"  # Financial / regulated (disabled in prototype; creates review task)
    R4 = "R4"  # Prohibited (always blocked and logged)

class ActionProposal(BaseModel):
    action_type: str
    target_id: str
    risk_tier: RiskTier
    actor_id: str
    actor_role: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    rationale: Optional[str] = None

class PolicyDecision(BaseModel):
    decision_id: str
    allowed: bool
    risk_tier: RiskTier
    reason_codes: List[str] = Field(default_factory=list)
    required_approvals: List[str] = Field(default_factory=list)
    constraints: Dict[str, Any] = Field(default_factory=dict)
