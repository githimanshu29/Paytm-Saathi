from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.policy.audit import audit_log
from app.schemas.common import HealthResponse
from app.schemas.merchant import DeviceToggleResponse
from app.adapters.device import MockDeviceAdapter
from app.core.config import settings
from app.api.auth import auth_router
from app.api.merchant import merchant_router
from app.api.employee import employee_router
from app.api.revive import revive_router
from app.api.onboard import onboard_router
from app.api.fieldmate import fieldmate_router
from app.api.vasooli import vasooli_router, demo_vasooli_router, employee_vasooli_router
from app.api.handoff import router as handoff_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(merchant_router)
api_router.include_router(employee_router)
api_router.include_router(revive_router)
api_router.include_router(onboard_router)
api_router.include_router(fieldmate_router)
api_router.include_router(vasooli_router)
api_router.include_router(demo_vasooli_router)
api_router.include_router(employee_vasooli_router)
api_router.include_router(handoff_router)

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

@api_router.post("/demo/device/{device_ref}/toggle", response_model=DeviceToggleResponse)
def demo_toggle_device(
    device_ref: str,
    target_status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Demo Toggle: Flips a device between ONLINE and OFFLINE for test execution and live demo.
    """
    adapter = MockDeviceAdapter(db)
    dev = adapter.get_device_by_serial(device_ref)
    if not dev:
        dev = adapter.get_device_by_id(device_ref)
    if not dev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {device_ref} not found.",
        )

    new_st = target_status.upper() if target_status else ("OFFLINE" if dev.status == "ONLINE" else "ONLINE")
    adapter.flip_device_status(dev.serial_number, new_st)

    audit_log(
        db=db,
        actor="demo_operator",
        action="DEMO_DEVICE_STATUS_TOGGLED",
        target=dev.serial_number,
        result=new_st,
        policy_decision_id="dec_demo_toggle_public",
    )

    return DeviceToggleResponse(
        success=True,
        device_id=dev.id,
        serial_number=dev.serial_number,
        new_status=new_st,
        message=f"Soundbox {dev.serial_number} status flipped to {new_st} (Demo Toggle).",
    )
