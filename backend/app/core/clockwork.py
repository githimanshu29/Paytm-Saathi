import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import ScheduledJob, Device
from app.adapters.device import MockDeviceAdapter
from app.tools.fix import FixTools
from app.policy.audit import audit_log

logger = logging.getLogger("paytm_saathi.clockwork")

class ClockworkScheduler:
    """
    Clockwork: In-process background scheduler for delayed and periodic agent jobs.
    Crash-safe architecture: All pending jobs are persisted in the 'scheduled_jobs' database table.
    On restart, uncompleted scheduled jobs are safely re-hydrated without loss or duplicates.
    """

    def __init__(self, start_scheduler: bool = True):
        self.scheduler = BackgroundScheduler(daemon=True)
        if start_scheduler:
            try:
                self.scheduler.start()
            except Exception as e:
                logger.warning(f"BackgroundScheduler start warning: {e}")

    def schedule_device_recheck(
        self,
        db: Session,
        merchant_id: str,
        device_ref: str,
        delay_seconds: int = 5,
        execution_id: Optional[str] = None,
    ) -> ScheduledJob:
        now = datetime.now(timezone.utc)
        run_at = now + timedelta(seconds=delay_seconds)
        exec_id = execution_id or f"exec_clk_{int(now.timestamp())}"
        idempotency_key = f"clk_recheck_{merchant_id}_{device_ref}_{int(run_at.timestamp() // 10)}"

        # Check existing scheduled job
        existing = db.query(ScheduledJob).filter_by(idempotency_key=idempotency_key).first()
        if existing:
            return existing

        payload = {
            "merchant_id": merchant_id,
            "device_ref": device_ref,
            "execution_id": exec_id,
        }

        job_row = ScheduledJob(
            id=f"job_clk_{idempotency_key[-16:]}",
            tenant_id=merchant_id,
            job_type="DEVICE_RECHECK",
            target_id=device_ref,
            run_at=run_at,
            status="SCHEDULED",
            idempotency_key=idempotency_key,
            payload_json=json.dumps(payload),
            is_synthetic=True,
            environment="DEMO",
        )
        db.add(job_row)
        db.commit()

        # Register in APScheduler
        try:
            self.scheduler.add_job(
                func=self.execute_recheck_job,
                trigger="date",
                run_date=run_at,
                args=[job_row.id],
                id=job_row.id,
                replace_existing=True,
            )
        except Exception as e:
            logger.error(f"Error adding job to in-process scheduler: {e}")

        return job_row

    def execute_recheck_job(self, job_id: str) -> Dict[str, Any]:
        """
        Executes a scheduled device recheck against the authoritative DeviceAdapter.
        """
        db = SessionLocal()
        try:
            job = db.query(ScheduledJob).filter_by(id=job_id).first()
            if not job or job.status == "COMPLETED":
                return {"executed": False, "reason": "Already completed or not found"}

            job.status = "RUNNING"
            db.commit()

            payload = json.loads(job.payload_json or "{}")
            device_ref = payload.get("device_ref", job.target_id)
            merchant_id = payload.get("merchant_id", "mer_demo")
            exec_id = payload.get("execution_id", "exec_recheck_auto")

            adapter = MockDeviceAdapter(db)
            tools = FixTools(adapter, db)

            # Authoritative fresh status check (NEVER ASSUMED)
            status_data = tools.get_device_status(device_ref, exec_id, "clockwork_scheduler")
            is_online = status_data.get("is_online", False)

            if is_online:
                # Device genuinely came online
                audit_log(
                    db=db,
                    actor="clockwork_scheduler",
                    action="DEVICE_RECHECK_VERIFIED_ONLINE",
                    target=device_ref,
                    result="ONLINE_VERIFIED",
                    policy_decision_id="dec_recheck_success",
                    idempotency_key=f"recheck_ok_{job.id}",
                )
                job.status = "COMPLETED"
                db.commit()
                return {"executed": True, "device_status": "ONLINE", "technician_booked": False}

            # Device is still offline or degraded -> book technician visit
            slots = tools.get_technician_slots("Jaipur", exec_id, "clockwork_scheduler")
            selected_slot = slots[0]["slot_time"] if slots else "Tomorrow 10:00 AM - 12:00 PM"
            tech_res = tools.create_technician_task(
                merchant_id=merchant_id,
                device_ref=device_ref,
                slot_str=selected_slot,
                issue_description="Soundbox offline. Automated Clockwork re-check confirmed remote recovery failed.",
                execution_id=exec_id,
                actor_id="clockwork_scheduler",
            )

            audit_log(
                db=db,
                actor="clockwork_scheduler",
                action="DEVICE_RECHECK_FAILED_BOOKED_TECHNICIAN",
                target=device_ref,
                result="TECHNICIAN_DISPATCHED",
                policy_decision_id="dec_recheck_failed",
                idempotency_key=f"recheck_fail_{job.id}",
            )

            job.status = "COMPLETED"
            db.commit()
            return {
                "executed": True,
                "device_status": "OFFLINE",
                "technician_booked": True,
                "task_id": tech_res.get("task_id"),
                "slot": selected_slot,
            }
        except Exception as e:
            logger.error(f"Clockwork recheck failed: {e}")
            db.rollback()
            return {"executed": False, "error": str(e)}
        finally:
            db.close()

    def recover_pending_jobs(self, db: Session) -> int:
        """
        Crash-safe recovery: Scans DB for SCHEDULED jobs and re-registers them in the scheduler.
        """
        now = datetime.now(timezone.utc)
        pending = db.query(ScheduledJob).filter(ScheduledJob.status == "SCHEDULED").all()
        recovered_count = 0

        for job in pending:
            run_dt = job.run_at
            if run_dt.tzinfo is None:
                run_dt = run_dt.replace(tzinfo=timezone.utc)

            # If overdue, execute immediately
            if run_dt <= now:
                self.execute_recheck_job(job.id)
            else:
                try:
                    self.scheduler.add_job(
                        func=self.execute_recheck_job,
                        trigger="date",
                        run_date=run_dt,
                        id=job.id,
                        replace_existing=True,
                    )
                except Exception as e:
                    logger.warning(f"Could not re-add job {job.id}: {e}")
            recovered_count += 1

        return recovered_count

# Global Clockwork singleton
clockwork = ClockworkScheduler(start_scheduler=True)

def get_clockwork_scheduler() -> ClockworkScheduler:
    return clockwork
