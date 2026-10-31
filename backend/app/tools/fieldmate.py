import hashlib
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.adapters.fieldmate import (
    IFieldMateAdapter,
    MockFieldMateAdapter,
    ConcurrencyConflictError,
    RepPolicyViolationError,
)
from app.db.models import Task, TaskBucket, AuditEvent, Merchant, MerchantVisit
from app.policy.engine import PolicyEngine
from app.policy.audit import audit_log
from app.schemas.policy import ActionProposal, RiskTier


def generate_idempotency_key(execution_id: str, action_type: str, target_id: str, params: Dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True)
    raw = f"{execution_id}:{action_type}:{target_id}:{canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class FieldMateTools:
    """
    Constrained, risk-tiered toolset for the FieldMate Sales Copilot.
    Enforces:
    - Truthful briefs: derived strictly from real DB state.
    - Rep Confirmation Gate: Zero auto-saves without explicit rep review and confirmation.
    - Concurrency Safety: Optimistic locking (version checks) to avoid silent overwrites.
    - Policy Guardrails:
        1. Reps can only view/edit their own assigned merchants.
        2. Prohibited from fabricating travel times.
        3. Prohibited from auto-approving loans or guaranteeing financing.
        4. Inferred interest is never treated as binding consent.
    """

    PROHIBITED_LOAN_TERMS = ["loan approved", "loan sanctioned", "credit guaranteed", "pre-approved disbursal"]

    def __init__(
        self,
        db_or_adapter: Optional[Any] = None,
        fieldmate_adapter: Optional[IFieldMateAdapter] = None,
        db: Optional[Session] = None,
    ):
        if isinstance(db_or_adapter, Session):
            db = db_or_adapter
        elif db_or_adapter is not None and hasattr(db_or_adapter, "get_assigned_merchants"):
            fieldmate_adapter = db_or_adapter

        self.db = db
        self.fieldmate_adapter = fieldmate_adapter or (MockFieldMateAdapter(db) if db else None)

    # TOOL 1: get_assigned_merchants (R0 Read-Only)
    def get_assigned_merchants(
        self,
        sales_rep_id: str,
        rep_lat: float = 26.9150,
        rep_lon: float = 75.8150,
        actor_id: str = "agent_fieldmate",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="GET_ASSIGNED_MERCHANTS",
            target_id=sales_rep_id,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="sales_rep",
            parameters={"sales_rep_id": sales_rep_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.fieldmate_adapter:
            return {"found": False, "reason": "Access denied or adapter unavailable."}

        items = self.fieldmate_adapter.get_assigned_merchants(sales_rep_id, rep_lat, rep_lon)
        return {
            "found": True,
            "sales_rep_id": sales_rep_id,
            "count": len(items),
            "merchants": [
                {
                    "visit_id": i.visit_id,
                    "merchant_id": i.merchant_id,
                    "store_name": i.store_name,
                    "merchant_name": i.merchant_name,
                    "phone": i.phone,
                    "city": i.city,
                    "latitude": i.latitude,
                    "longitude": i.longitude,
                    "distance_km": i.distance_km,
                    "priority": i.priority,
                    "planned_order": i.planned_order,
                    "visit_status": i.visit_status,
                    "evidence_backed_brief": i.evidence_backed_brief,
                    "brief_cause_type": i.brief_cause_type,
                    "lead_status": i.lead_status,
                    "is_confirmed_by_rep": i.is_confirmed_by_rep,
                    "version": i.version,
                }
                for i in items
            ],
        }

    # TOOL 2: get_merchant_brief (R0 Read-Only)
    def get_merchant_brief(
        self,
        merchant_id: str,
        sales_rep_id: str,
        rep_lat: float = 26.9150,
        rep_lon: float = 75.8150,
        actor_id: str = "agent_fieldmate",
    ) -> Dict[str, Any]:
        # Rep assignment boundary check
        if self.db:
            m = self.db.query(Merchant).filter(Merchant.id == merchant_id).first()
            if m and m.assigned_sales_rep_id and m.assigned_sales_rep_id != sales_rep_id:
                return {
                    "found": False,
                    "error": "ACCESS_DENIED",
                    "reason": "Merchant is not assigned to this sales representative.",
                }

        proposal = ActionProposal(
            action_type="GET_MERCHANT_BRIEF",
            target_id=merchant_id,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="sales_rep",
            parameters={"merchant_id": merchant_id, "sales_rep_id": sales_rep_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.fieldmate_adapter:
            return {"found": False, "reason": "Access denied or adapter unavailable."}

        brief = self.fieldmate_adapter.get_merchant_brief(merchant_id, rep_lat, rep_lon)
        if not brief:
            return {"found": False, "reason": f"No merchant found for ID {merchant_id}."}

        return {
            "found": True,
            "merchant_id": brief.merchant_id,
            "store_name": brief.store_name,
            "merchant_name": brief.merchant_name,
            "phone": brief.phone,
            "city": brief.city,
            "latitude": brief.latitude,
            "longitude": brief.longitude,
            "distance_km": brief.distance_km,
            "priority": brief.priority,
            "one_line_brief": brief.one_line_brief,
            "brief_cause_type": brief.brief_cause_type,
            "evidence_breakdown": brief.evidence_breakdown,
            "talking_points": brief.talking_points,
            "recommended_pitch": brief.recommended_pitch,
            "visit_id": brief.visit_id,
            "version": brief.version,
        }

    # TOOL 3: suggest_visit_order (R0 Read-Only Recommendation)
    def suggest_visit_order(
        self,
        sales_rep_id: str,
        rep_lat: float = 26.9150,
        rep_lon: float = 75.8150,
        actor_id: str = "agent_fieldmate",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="SUGGEST_VISIT_ORDER",
            target_id=sales_rep_id,
            risk_tier=RiskTier.R0,
            actor_id=actor_id,
            actor_role="sales_rep",
            parameters={"sales_rep_id": sales_rep_id},
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.fieldmate_adapter:
            return {"found": False, "reason": "Access denied or adapter unavailable."}

        ordered_items = self.fieldmate_adapter.suggest_visit_order(sales_rep_id, rep_lat, rep_lon)
        return {
            "found": True,
            "sales_rep_id": sales_rep_id,
            "disclaimer": "This is a heuristic priority recommendation, not a guaranteed-optimal route.",
            "count": len(ordered_items),
            "ordered_route": [
                {
                    "visit_id": i.visit_id,
                    "merchant_id": i.merchant_id,
                    "store_name": i.store_name,
                    "merchant_name": i.merchant_name,
                    "phone": i.phone,
                    "city": i.city,
                    "distance_km": i.distance_km,
                    "priority": i.priority,
                    "planned_order": i.planned_order,
                    "visit_status": i.visit_status,
                    "evidence_backed_brief": i.evidence_backed_brief,
                    "lead_status": i.lead_status,
                    "version": i.version,
                }
                for i in ordered_items
            ],
        }

    # TOOL 4: create_visit_task (R1 Internal Task Creation)
    def create_visit_task(
        self,
        merchant_id: str,
        sales_rep_id: str,
        title: str,
        description: str,
        priority: str = "MEDIUM",
        execution_id: str = "exec_visit_task",
        actor_id: str = "agent_fieldmate",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="CREATE_VISIT_TASK",
            target_id=merchant_id,
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="sales_rep",
            parameters={
                "merchant_id": merchant_id,
                "sales_rep_id": sales_rep_id,
                "title": title,
                "description": description,
                "priority": priority,
            },
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"created": False, "reason": "Policy denied action."}

        if not self.db:
            return {"created": False, "reason": "Database session unavailable."}

        # Check rep boundary
        m = self.db.query(Merchant).filter(Merchant.id == merchant_id).first()
        if m and m.assigned_sales_rep_id and m.assigned_sales_rep_id != sales_rep_id:
            return {
                "created": False,
                "error": "ACCESS_DENIED",
                "reason": "Cannot create task for merchant assigned to another representative.",
            }

        task = Task(
            tenant_id=m.tenant_id if m else "tenant_paytm_demo",
            merchant_id=merchant_id,
            title=title,
            description=description,
            bucket=TaskBucket.PENDING,
            priority=priority,
            assigned_to=sales_rep_id,
            is_synthetic=True,
            environment="DEMO",
        )
        self.db.add(task)

        # Audit Event
        idemp = generate_idempotency_key(execution_id, "CREATE_VISIT_TASK", merchant_id, {"title": title})
        audit = audit_log(
            db=self.db,
            actor=actor_id,
            action="CREATE_VISIT_TASK",
            target=f"tasks:{task.id}",
            policy_decision_id=decision.decision_id,
            idempotency_key=idemp,
            result="SUCCESS",
        )
        self.db.commit()

        return {
            "created": True,
            "task_id": task.id,
            "title": task.title,
            "assigned_to": task.assigned_to,
            "bucket": task.bucket.value if hasattr(task.bucket, "value") else str(task.bucket),
            "audit_event_id": audit.id,
        }

    # TOOL 5: save_structured_visit_note (R1 - Enforces Confirmation Gate & Concurrency Control)
    def save_structured_visit_note(
        self,
        visit_id: str,
        expected_version: int,
        confirmed_notes: str,
        sales_rep_id: str,
        lead_interest: Optional[str] = None,
        execution_id: str = "exec_visit_note_save",
        actor_id: str = "agent_fieldmate",
    ) -> Dict[str, Any]:
        # Block prohibited loan auto-approvals
        n_lower = confirmed_notes.lower()
        for term in self.PROHIBITED_LOAN_TERMS:
            if term in n_lower:
                return {
                    "saved": False,
                    "error": "POLICY_VIOLATION",
                    "reason": f"Prohibited term detected: '{term}'. Sales reps cannot approve loans or guarantee financing.",
                }

        proposal = ActionProposal(
            action_type="SAVE_STRUCTURED_VISIT_NOTE",
            target_id=visit_id,
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="sales_rep",
            parameters={
                "visit_id": visit_id,
                "expected_version": expected_version,
                "lead_interest": lead_interest,
            },
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed or not self.fieldmate_adapter:
            return {"saved": False, "reason": "Policy denied action or adapter unavailable."}

        try:
            res = self.fieldmate_adapter.confirm_and_save_visit_note(
                visit_id=visit_id,
                expected_version=expected_version,
                confirmed_notes=confirmed_notes,
                lead_interest=lead_interest,
                sales_rep_id=sales_rep_id,
            )
            return {
                "saved": True,
                "visit_id": res.visit_id,
                "merchant_id": res.merchant_id,
                "is_confirmed": res.is_confirmed,
                "confirmed_notes": res.confirmed_notes,
                "lead_interest": res.lead_interest,
                "new_version": res.new_version,
                "audit_event_id": res.audit_event_id,
                "message": res.message,
            }
        except ConcurrencyConflictError as ce:
            return {
                "saved": False,
                "error": "CONCURRENCY_CONFLICT",
                "reason": str(ce),
            }
        except RepPolicyViolationError as pe:
            return {
                "saved": False,
                "error": "POLICY_VIOLATION",
                "reason": str(pe),
            }
        except Exception as e:
            return {
                "saved": False,
                "error": "INTERNAL_ERROR",
                "reason": str(e),
            }

    # TOOL 6: create_sales_lead (R1 CRM Lead Creation)
    def create_sales_lead(
        self,
        merchant_id: str,
        sales_rep_id: str,
        product_name: str,
        interest_level: str = "INTERESTED",
        notes: str = "",
        execution_id: str = "exec_create_lead",
        actor_id: str = "agent_fieldmate",
    ) -> Dict[str, Any]:
        proposal = ActionProposal(
            action_type="CREATE_SALES_LEAD",
            target_id=merchant_id,
            risk_tier=RiskTier.R1,
            actor_id=actor_id,
            actor_role="sales_rep",
            parameters={
                "merchant_id": merchant_id,
                "sales_rep_id": sales_rep_id,
                "product_name": product_name,
                "interest_level": interest_level,
            },
        )
        decision = PolicyEngine.evaluate(proposal)
        if not decision.allowed:
            return {"created": False, "reason": "Policy denied action."}

        if not self.db:
            return {"created": False, "reason": "Database session unavailable."}

        m = self.db.query(Merchant).filter(Merchant.id == merchant_id).first()
        if not m:
            return {"created": False, "reason": "Merchant not found."}

        if m.assigned_sales_rep_id and m.assigned_sales_rep_id != sales_rep_id:
            return {
                "created": False,
                "error": "ACCESS_DENIED",
                "reason": "Cannot create sales lead for another rep's merchant.",
            }

        # Update merchant lead status
        m.lead_status = interest_level

        # Create Task for follow-up review
        task = Task(
            tenant_id=m.tenant_id,
            merchant_id=merchant_id,
            title=f"Sales Lead: {product_name} - {m.store_name}",
            description=f"Field rep logged interest in {product_name}. Notes: {notes}. Interest Level: {interest_level}",
            bucket=TaskBucket.PENDING,
            priority="HIGH" if interest_level == "HIGH_INTEREST" else "MEDIUM",
            assigned_to=sales_rep_id,
            is_synthetic=True,
            environment="DEMO",
        )
        self.db.add(task)

        # Audit event
        idemp = generate_idempotency_key(execution_id, "CREATE_SALES_LEAD", merchant_id, {"product": product_name})
        audit = audit_log(
            db=self.db,
            actor=actor_id,
            action="CREATE_SALES_LEAD",
            target=f"tasks:{task.id}",
            policy_decision_id=decision.decision_id,
            idempotency_key=idemp,
            result="SUCCESS",
        )
        self.db.commit()

        return {
            "created": True,
            "merchant_id": merchant_id,
            "lead_status": m.lead_status,
            "product_name": product_name,
            "task_id": task.id,
            "audit_event_id": audit.id,
        }
