from typing import Optional
from sqlalchemy.orm import Session
from app.db.models import AuditEvent
from app.core.config import settings

def audit_log(
    db: Session,
    actor: str,
    action: str,
    target: str,
    result: str,
    policy_decision_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> AuditEvent:
    """
    Writes an immutable row into audit_events.
    Source of truth for all activity across merchant and employee apps.
    """
    event = AuditEvent(
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        target=target,
        policy_decision_id=policy_decision_id,
        idempotency_key=idempotency_key,
        result=result,
        is_synthetic=True,
        environment=settings.ENVIRONMENT,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
