import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import engine, SessionLocal
from app.db.models import (
    Tenant,
    Merchant,
    Employee,
    Device,
    Transaction,
    Customer,
    Receivable,
    Task,
    ActionApproval,
    AuditEvent,
)
from scripts.seed_demo_data import seed_demo_data

def reset_demo_data():
    db = SessionLocal()
    try:
        print("Resetting database demo state...")
        # Delete dependent children first
        db.query(AuditEvent).delete()
        db.query(ActionApproval).delete()
        db.query(Task).delete()
        db.query(Receivable).delete()
        db.query(Customer).delete()
        db.query(Transaction).delete()
        db.query(Device).delete()
        db.query(Employee).delete()
        db.query(Merchant).delete()
        db.query(Tenant).delete()
        db.commit()
        print("All records cleaned. Re-seeding deterministic demo state...")
    except Exception as e:
        db.rollback()
        print(f"Error resetting database: {e}")
        raise
    finally:
        db.close()

    # Re-seed
    seed_demo_data()
    print("Database reset and re-seeded successfully.")

if __name__ == "__main__":
    reset_demo_data()
