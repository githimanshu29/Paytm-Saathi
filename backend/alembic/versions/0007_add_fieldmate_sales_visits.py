"""add fieldmate sales visits and merchant geo coordinates

Revision ID: 0007_add_fieldmate_sales_visits
Revises: 0006_add_onboarding_and_kyc_documents
Create Date: 2026-10-29 23:17:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0007_add_fieldmate_sales_visits'
down_revision: Union[str, None] = '0006_add_onboarding_and_kyc_documents'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add columns to merchants table
    with op.batch_alter_table('merchants') as batch_op:
        batch_op.add_column(sa.Column('assigned_sales_rep_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('latitude', sa.Float(), nullable=True, server_default='26.9124'))
        batch_op.add_column(sa.Column('longitude', sa.Float(), nullable=True, server_default='75.7873'))
        batch_op.add_column(sa.Column('lead_status', sa.String(length=50), nullable=True, server_default='NONE'))

    # 2. Create merchant_visits table
    op.create_table(
        'merchant_visits',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('tenant_id', sa.String(length=64), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('merchant_id', sa.String(length=64), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('sales_rep_id', sa.String(length=64), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('visit_status', sa.String(length=50), nullable=False, server_default='SCHEDULED'),
        sa.Column('planned_order', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('priority', sa.String(length=50), nullable=False, server_default='MEDIUM'),
        sa.Column('distance_km', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('evidence_backed_brief', sa.String(length=255), nullable=False),
        sa.Column('brief_cause_type', sa.String(length=50), nullable=False, server_default='GENERAL_CHECKIN'),
        sa.Column('raw_audio_base64', sa.Text(), nullable=True),
        sa.Column('raw_transcript', sa.Text(), nullable=True),
        sa.Column('extracted_candidate_fields', sa.Text(), nullable=True),
        sa.Column('confirmed_notes', sa.Text(), nullable=True),
        sa.Column('lead_interest', sa.String(length=100), nullable=True),
        sa.Column('is_confirmed_by_rep', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_synthetic', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('environment', sa.String(length=32), nullable=False, server_default='DEMO'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('merchant_visits')
    with op.batch_alter_table('merchants') as batch_op:
        batch_op.drop_column('lead_status')
        batch_op.drop_column('longitude')
        batch_op.drop_column('latitude')
        batch_op.drop_column('assigned_sales_rep_id')
