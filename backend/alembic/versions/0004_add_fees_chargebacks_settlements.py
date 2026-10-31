"""add_fees_chargebacks_settlements

Revision ID: 0004_add_fees_chargebacks_settlements
Revises: 0003_add_device_telemetry_and_scheduled_jobs
Create Date: 2026-10-29 18:47:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = '0004_add_fees_chargebacks_settlements'
down_revision: Union[str, None] = '0003_add_device_telemetry_and_scheduled_jobs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing_tables = inspector.get_table_names()
    existing_task_cols = [c['name'] for c in inspector.get_columns('tasks')]

    # 1. Extend tasks table with evidence and dispute amount
    if 'evidence_notes' not in existing_task_cols:
        op.add_column('tasks', sa.Column('evidence_notes', sa.Text(), nullable=True))
    if 'evidence_url' not in existing_task_cols:
        op.add_column('tasks', sa.Column('evidence_url', sa.String(length=255), nullable=True))
    if 'dispute_amount' not in existing_task_cols:
        op.add_column('tasks', sa.Column('dispute_amount', sa.Integer(), nullable=True))

    # 2. Create transaction_fees table
    if 'transaction_fees' not in existing_tables:
        op.create_table(
            'transaction_fees',
            sa.Column('id', sa.String(length=64), primary_key=True),
            sa.Column('tenant_id', sa.String(length=64), nullable=False),
            sa.Column('merchant_id', sa.String(length=64), nullable=False),
            sa.Column('transaction_id', sa.String(length=64), nullable=True),
            sa.Column('amount', sa.Integer(), nullable=False),
            sa.Column('fee_type', sa.String(length=50), server_default='MDR', nullable=False),
            sa.Column('description', sa.String(length=255), nullable=True),
            sa.Column('settlement_date', sa.String(length=20), nullable=True),
            sa.Column('is_synthetic', sa.Boolean(), server_default='1', nullable=False),
            sa.Column('environment', sa.String(length=32), server_default='DEMO', nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )

    # 3. Create chargebacks table
    if 'chargebacks' not in existing_tables:
        op.create_table(
            'chargebacks',
            sa.Column('id', sa.String(length=64), primary_key=True),
            sa.Column('tenant_id', sa.String(length=64), nullable=False),
            sa.Column('merchant_id', sa.String(length=64), nullable=False),
            sa.Column('transaction_id', sa.String(length=64), nullable=True),
            sa.Column('amount', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=50), server_default='PROCESSED', nullable=False),
            sa.Column('reason', sa.String(length=255), nullable=False),
            sa.Column('dispute_ref', sa.String(length=100), nullable=True),
            sa.Column('evidence_notes', sa.Text(), nullable=True),
            sa.Column('settlement_date', sa.String(length=20), nullable=True),
            sa.Column('is_synthetic', sa.Boolean(), server_default='1', nullable=False),
            sa.Column('environment', sa.String(length=32), server_default='DEMO', nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )

    # 4. Create settlements table
    if 'settlements' not in existing_tables:
        op.create_table(
            'settlements',
            sa.Column('id', sa.String(length=64), primary_key=True),
            sa.Column('tenant_id', sa.String(length=64), nullable=False),
            sa.Column('merchant_id', sa.String(length=64), nullable=False),
            sa.Column('settlement_date', sa.String(length=20), nullable=False),
            sa.Column('gross_sales', sa.Integer(), server_default='0', nullable=False),
            sa.Column('refunds', sa.Integer(), server_default='0', nullable=False),
            sa.Column('fees', sa.Integer(), server_default='0', nullable=False),
            sa.Column('chargebacks', sa.Integer(), server_default='0', nullable=False),
            sa.Column('net_expected', sa.Integer(), server_default='0', nullable=False),
            sa.Column('net_settled', sa.Integer(), server_default='0', nullable=False),
            sa.Column('discrepancy', sa.Integer(), server_default='0', nullable=False),
            sa.Column('status', sa.String(length=50), server_default='RECONCILED', nullable=False),
            sa.Column('bank_utr', sa.String(length=100), nullable=True),
            sa.Column('nodal_account', sa.String(length=100), server_default='ICICI_NODAL_0192', nullable=True),
            sa.Column('dispute_case_id', sa.String(length=64), nullable=True),
            sa.Column('evidence_attached', sa.Text(), nullable=True),
            sa.Column('is_synthetic', sa.Boolean(), server_default='1', nullable=False),
            sa.Column('environment', sa.String(length=32), server_default='DEMO', nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table('settlements')
    op.drop_table('chargebacks')
    op.drop_table('transaction_fees')
    op.drop_column('tasks', 'dispute_amount')
    op.drop_column('tasks', 'evidence_url')
    op.drop_column('tasks', 'evidence_notes')
