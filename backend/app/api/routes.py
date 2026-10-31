from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.policy.audit import audit_log
from app.schemas.common import HealthResponse
from app.core.config import settings
from app.api.auth import auth_router
from app.api.merchant import merchant_router
from app.api.employee import employee_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(merchant_router)
api_router.include_router(employee_router)

@api_router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    # Record health ping in audit log to verify end-to-end logging
    event = audit_log(
        db=db,
        actor="system",
        action="HEALTH_CHECK",
        target="backend_service",
        result="SUCCESS",
        policy_decision_id="dec_system_auto",
        idempotency_key=None,
    )
    return HealthResponse(
        status="ok",
        service=settings.PROJECT_NAME,
        environment=settings.ENVIRONMENT,
        audit_event_id=event.id,
    )
