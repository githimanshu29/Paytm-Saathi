"""add_device_telemetry_and_scheduled_jobs

Revision ID: 0003_add_device_telemetry_and_scheduled_jobs
Revises: 0002_add_transaction_status_fields
Create Date: 2026-10-29 18:08:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = '0003_add_device_telemetry_and_scheduled_jobs'
down_revision: Union[str, None] = '0002_add_transaction_status_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing_device_cols = [c['name'] for c in inspector.get_columns('devices')]
    existing_task_cols = [c['name'] for c in inspector.get_columns('tasks')]
    existing_tables = inspector.get_table_names()

    # 1. Extend devices table idempotently
    if 'last_heartbeat' not in existing_device_cols:
        op.add_column('devices', sa.Column('last_heartbeat', sa.DateTime(), nullable=True))
    if 'signal_strength_dbm' not in existing_device_cols:
        op.add_column('devices', sa.Column('signal_strength_dbm', sa.Integer(), nullable=True, server_default='-70'))
    if 'firmware_version' not in existing_device_cols:
        op.add_column('devices', sa.Column('firmware_version', sa.String(length=50), nullable=True, server_default='v3.4.1'))
    if 'reboot_in_progress' not in existing_device_cols:
        op.add_column('devices', sa.Column('reboot_in_progress', sa.Boolean(), nullable=False, server_default='0'))
    if 'technician_visit_booked' not in existing_device_cols:
        op.add_column('devices', sa.Column('technician_visit_booked', sa.Boolean(), nullable=False, server_default='0'))
    if 'technician_slot' not in existing_device_cols:
        op.add_column('devices', sa.Column('technician_slot', sa.String(length=100), nullable=True))
    if 'updated_at' not in existing_device_cols:
        op.add_column('devices', sa.Column('updated_at', sa.DateTime(), nullable=True))

    # 2. Extend tasks table with device_id idempotently
    if 'device_id' not in existing_task_cols:
        op.add_column('tasks', sa.Column('device_id', sa.String(length=64), nullable=True))

    # 3. Create scheduled_jobs table for crash-safe Clockwork rechecks
    if 'scheduled_jobs' not in existing_tables:
        op.create_table(
            'scheduled_jobs',
            sa.Column('id', sa.String(length=64), primary_key=True),
            sa.Column('tenant_id', sa.String(length=64), nullable=True),
            sa.Column('job_type', sa.String(length=64), nullable=False),
            sa.Column('target_id', sa.String(length=64), nullable=False),
            sa.Column('run_at', sa.DateTime(), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False, server_default='SCHEDULED'),
            sa.Column('idempotency_key', sa.String(length=128), unique=True, nullable=False),
            sa.Column('payload_json', sa.Text(), nullable=True),
            sa.Column('is_synthetic', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('environment', sa.String(length=32), nullable=False, server_default='DEMO'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table('scheduled_jobs')
    op.drop_column('tasks', 'device_id')
    op.drop_column('devices', 'updated_at')
    op.drop_column('devices', 'technician_slot')
    op.drop_column('devices', 'technician_visit_booked')
    op.drop_column('devices', 'reboot_in_progress')
    op.drop_column('devices', 'firmware_version')
    op.drop_column('devices', 'signal_strength_dbm')
    op.drop_column('devices', 'last_heartbeat')
