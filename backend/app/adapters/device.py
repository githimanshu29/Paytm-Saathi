from datetime import datetime, timezone, timedelta
from typing import List, Optional, Protocol, runtime_checkable
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db.models import Device

class DeviceRecord(BaseModel):
    id: str
    tenant_id: str
    merchant_id: str
    device_type: str
    serial_number: str
    sim_number: Optional[str] = None
    battery_level: int
    status: str
    last_heartbeat: Optional[datetime] = None
    signal_strength_dbm: Optional[int] = -70
    firmware_version: Optional[str] = "v3.4.1"
    reboot_in_progress: bool = False
    technician_visit_booked: bool = False
    technician_slot: Optional[str] = None
    created_at: datetime

class DeviceDiagnosticsRecord(BaseModel):
    device_id: str
    serial_number: str
    status: str
    battery_level: int
    battery_healthy: bool
    signal_strength_dbm: int
    signal_quality: str  # EXCELLENT | GOOD | WEAK | NO_SIGNAL
    firmware_version: str
    firmware_up_to_date: bool
    last_heartbeat_ago_seconds: Optional[int] = None
    last_heartbeat_str: str
    is_online: bool
    speaker_status: str
    sim_status: str

class RestartResultRecord(BaseModel):
    success: bool
    device_id: str
    serial_number: str
    command_id: str
    status: str  # RESTART_SIGNAL_DISPATCHED | DEVICE_OFFLINE_CANNOT_REACH | SIMULATED_REBOOTING
    message: str
    initiated_at: datetime

class TechnicianSlotRecord(BaseModel):
    slot_id: str
    slot_time: str
    date_str: str
    technician_name: str
    city: str
    available: bool = True

@runtime_checkable
class IDeviceAdapter(Protocol):
    """
    Decoupled interface for Soundbox and IoT terminal telemetry.
    Swappable for live Paytm IoT gateway or vendor telemetry API.
    """

    def get_device_by_id(self, device_id: str) -> Optional[DeviceRecord]:
        ...

    def get_device_by_serial(self, serial_number: str) -> Optional[DeviceRecord]:
        ...

    def get_device_by_merchant(self, merchant_id: str) -> Optional[DeviceRecord]:
        ...

    def get_device_diagnostics(self, device_id_or_serial: str) -> Optional[DeviceDiagnosticsRecord]:
        ...

    def request_remote_restart(self, device_id_or_serial: str) -> RestartResultRecord:
        ...

    def flip_device_status(self, device_id_or_serial: str, new_status: str) -> bool:
        ...

    def get_technician_slots(self, city: str) -> List[TechnicianSlotRecord]:
        ...

    def update_technician_booking(self, device_id: str, slot: str) -> bool:
        ...


class MockDeviceAdapter:
    """
    Authoritative Database-backed adapter implementing IDeviceAdapter.
    """

    def __init__(self, db: Session):
        self.db = db

    def _to_record(self, dev: Device) -> DeviceRecord:
        return DeviceRecord(
            id=dev.id,
            tenant_id=dev.tenant_id,
            merchant_id=dev.merchant_id,
            device_type=dev.device_type,
            serial_number=dev.serial_number,
            sim_number=dev.sim_number,
            battery_level=dev.battery_level,
            status=dev.status,
            last_heartbeat=dev.last_heartbeat,
            signal_strength_dbm=dev.signal_strength_dbm,
            firmware_version=dev.firmware_version,
            reboot_in_progress=dev.reboot_in_progress,
            technician_visit_booked=dev.technician_visit_booked,
            technician_slot=dev.technician_slot,
            created_at=dev.created_at,
        )

    def get_device_by_id(self, device_id: str) -> Optional[DeviceRecord]:
        dev = self.db.query(Device).filter_by(id=device_id).first()
        return self._to_record(dev) if dev else None

    def get_device_by_serial(self, serial_number: str) -> Optional[DeviceRecord]:
        s = serial_number.strip()
        dev = self.db.query(Device).filter(Device.serial_number.ilike(s)).first()
        if not dev:
            dev = self.db.query(Device).filter(Device.serial_number.ilike(f"{s}%")).first()
        return self._to_record(dev) if dev else None

    def get_device_by_merchant(self, merchant_id: str) -> Optional[DeviceRecord]:
        dev = self.db.query(Device).filter_by(merchant_id=merchant_id).first()
        return self._to_record(dev) if dev else None

    def get_device_diagnostics(self, device_id_or_serial: str) -> Optional[DeviceDiagnosticsRecord]:
        s = device_id_or_serial.strip()
        dev = (
            self.db.query(Device)
            .filter((Device.id == s) | (Device.serial_number.ilike(s)) | (Device.serial_number.ilike(f"{s}%")))
            .first()
        )
        if not dev:
            return None

        now = datetime.now(timezone.utc)
        hb_seconds = None
        hb_str = "No heartbeat recorded"
        if dev.last_heartbeat:
            # Handle naive or aware datetimes safely
            hb_dt = dev.last_heartbeat
            if hb_dt.tzinfo is None:
                hb_dt = hb_dt.replace(tzinfo=timezone.utc)
            hb_seconds = int((now - hb_dt).total_seconds())
            if hb_seconds < 60:
                hb_str = f"{hb_seconds}s ago"
            elif hb_seconds < 3600:
                hb_str = f"{hb_seconds // 60}m ago"
            else:
                hb_str = f"{hb_seconds // 3600}h ago"

        # Signal quality mapping
        sig = dev.signal_strength_dbm if dev.signal_strength_dbm is not None else -100
        if sig >= -75:
            sig_qual = "EXCELLENT"
        elif sig >= -90:
            sig_qual = "GOOD"
        elif sig >= -105:
            sig_qual = "WEAK"
        else:
            sig_qual = "NO_SIGNAL"

        return DeviceDiagnosticsRecord(
            device_id=dev.id,
            serial_number=dev.serial_number,
            status=dev.status,
            battery_level=dev.battery_level,
            battery_healthy=dev.battery_level >= 20,
            signal_strength_dbm=sig,
            signal_quality=sig_qual,
            firmware_version=dev.firmware_version or "v3.4.1",
            firmware_up_to_date=dev.firmware_version == "v3.4.1",
            last_heartbeat_ago_seconds=hb_seconds,
            last_heartbeat_str=hb_str,
            is_online=dev.status.upper() == "ONLINE",
            speaker_status="OPERATIONAL" if dev.status.upper() != "ERROR" else "HARDWARE_FAULT",
            sim_status="REGISTERED" if sig_qual != "NO_SIGNAL" else "UNREGISTERED",
        )

    def request_remote_restart(self, device_id_or_serial: str) -> RestartResultRecord:
        s = device_id_or_serial.strip()
        dev = (
            self.db.query(Device)
            .filter((Device.id == s) | (Device.serial_number.ilike(s)) | (Device.serial_number.ilike(f"{s}%")))
            .first()
        )
        now = datetime.now(timezone.utc)
        if not dev:
            return RestartResultRecord(
                success=False,
                device_id="unknown",
                serial_number=device_id_or_serial,
                command_id=f"cmd_rst_{int(now.timestamp())}",
                status="DEVICE_NOT_FOUND",
                message=f"Device reference {device_id_or_serial} not found in gateway inventory.",
                initiated_at=now,
            )

        # Mark reboot in progress
        dev.reboot_in_progress = True
        self.db.commit()

        return RestartResultRecord(
            success=True,
            device_id=dev.id,
            serial_number=dev.serial_number,
            command_id=f"cmd_rst_{dev.serial_number}_{int(now.timestamp())}",
            status="SIMULATED_REBOOTING",
            message=f"Over-the-air reboot packet dispatched to Soundbox {dev.serial_number} via 4G telemetry.",
            initiated_at=now,
        )

    def flip_device_status(self, device_id_or_serial: str, new_status: str) -> bool:
        """
        Demo toggle: Flips real device status on demand for test and live demonstration.
        """
        s = device_id_or_serial.strip()
        dev = (
            self.db.query(Device)
            .filter((Device.id == s) | (Device.serial_number.ilike(s)) | (Device.serial_number.ilike(f"{s}%")))
            .first()
        )
        if not dev:
            return False

        dev.status = new_status.upper()
        if new_status.upper() == "ONLINE":
            dev.last_heartbeat = datetime.now(timezone.utc)
            dev.reboot_in_progress = False
            if dev.battery_level < 20:
                dev.battery_level = 95
            dev.signal_strength_dbm = -65
        elif new_status.upper() == "OFFLINE":
            dev.reboot_in_progress = False

        self.db.commit()
        return True

    def get_technician_slots(self, city: str) -> List[TechnicianSlotRecord]:
        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)
        day_after = now + timedelta(days=2)
        date1_str = tomorrow.strftime("%d %b (%a)")
        date2_str = day_after.strftime("%d %b (%a)")

        # Realistic slots based on city region
        return [
            TechnicianSlotRecord(
                slot_id="slot_morning_tmrw",
                slot_time="10:00 AM - 12:00 PM",
                date_str=date1_str,
                technician_name="Vikram Verma (Paytm FSE)",
                city=city,
                available=True,
            ),
            TechnicianSlotRecord(
                slot_id="slot_afternoon_tmrw",
                slot_time="02:00 PM - 04:00 PM",
                date_str=date1_str,
                technician_name="Ravi Chawla (Paytm FSE)",
                city=city,
                available=True,
            ),
            TechnicianSlotRecord(
                slot_id="slot_morning_next",
                slot_time="11:00 AM - 01:00 PM",
                date_str=date2_str,
                technician_name="Sunil Sharma (Paytm FSE)",
                city=city,
                available=True,
            ),
        ]

    def update_technician_booking(self, device_id: str, slot: str) -> bool:
        dev = self.db.query(Device).filter_by(id=device_id).first()
        if not dev:
            return False
        dev.technician_visit_booked = True
        dev.technician_slot = slot
        self.db.commit()
        return True
