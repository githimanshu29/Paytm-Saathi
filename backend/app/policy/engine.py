import uuid
from app.schemas.policy import ActionProposal, PolicyDecision, RiskTier

class PolicyEngine:
    """
    Central security and governance boundary for Paytm Saathi.
    No tool or agent can execute an action without a PolicyDecision from this engine.
    """

    @staticmethod
    def evaluate(proposal: ActionProposal) -> PolicyDecision:
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"

        # Prohibited actions are always rejected and logged
        if proposal.risk_tier == RiskTier.R4:
            return PolicyDecision(
                decision_id=decision_id,
                allowed=False,
                risk_tier=RiskTier.R4,
                reason_codes=["R4_PROHIBITED_ACTION_BLOCKED"],
                required_approvals=[],
                constraints={"blocked": True},
            )

        # R3 Financial / regulated actions are disabled in this prototype
        if proposal.risk_tier == RiskTier.R3:
            return PolicyDecision(
                decision_id=decision_id,
                allowed=False,
                risk_tier=RiskTier.R3,
                reason_codes=["R3_REGULATED_FINANCIAL_AUTOMATION_DISABLED"],
                required_approvals=["SENIOR_MANAGER", "COMPLIANCE_OFFICER"],
                constraints={"requires_review_task": True},
            )

        # R2 External communications or bookings require approval
        if proposal.risk_tier == RiskTier.R2:
            return PolicyDecision(
                decision_id=decision_id,
                allowed=False,
                risk_tier=RiskTier.R2,
                reason_codes=["R2_EXTERNAL_ACTION_REQUIRES_APPROVAL"],
                required_approvals=["MERCHANT_APPROVAL"],
                constraints={"expires_in_hours": 24},
            )

        # R1 Internal / reversible actions are auto-allowed and audited
        if proposal.risk_tier == RiskTier.R1:
            return PolicyDecision(
                decision_id=decision_id,
                allowed=True,
                risk_tier=RiskTier.R1,
                reason_codes=["R1_INTERNAL_REVERSIBLE_ALLOWED"],
                required_approvals=[],
                constraints={"audit_required": True},
            )

        # R0 Read-only queries are always allowed
        return PolicyDecision(
            decision_id=decision_id,
            allowed=True,
            risk_tier=RiskTier.R0,
            reason_codes=["R0_READ_ALWAYS_ALLOWED"],
            required_approvals=[],
            constraints={},
        )
