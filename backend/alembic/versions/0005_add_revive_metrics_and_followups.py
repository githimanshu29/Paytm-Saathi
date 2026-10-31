"""add revive metrics and followups

Revision ID: 0005_add_revive_metrics_and_followups
Revises: 0004_add_fees_chargebacks_settlements
Create Date: 2026-10-29 19:21:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0005_add_revive_metrics_and_followups'
down_revision: Union[str, None] = '0004_add_fees_chargebacks_settlements'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'merchant_activity_metrics',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('tenant_id', sa.String(length=64), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('merchant_id', sa.String(length=64), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('baseline_daily_tx_count', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('baseline_daily_volume_paise', sa.Integer(), nullable=False, server_default='1000000'),
        sa.Column('recent_daily_tx_count', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('recent_daily_volume_paise', sa.Integer(), nullable=False, server_default='300000'),
        sa.Column('drop_percentage', sa.Integer(), nullable=False, server_default='70'),
        sa.Column('health_status', sa.String(length=50), nullable=False, server_default='AT_RISK'),
        sa.Column('diagnosed_cause', sa.String(length=50), nullable=True),
        sa.Column('revival_stage', sa.String(length=50), nullable=False, server_default='AT_RISK'),
        sa.Column('last_scanned_at', sa.DateTime(), nullable=False),
        sa.Column('recovered_at', sa.DateTime(), nullable=True),
        sa.Column('is_synthetic', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('environment', sa.String(length=32), nullable=False, server_default='DEMO'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    op.create_table(
        'merchant_followups',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('tenant_id', sa.String(length=64), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('merchant_id', sa.String(length=64), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('cause_type', sa.String(length=50), nullable=False),
        sa.Column('message_title', sa.String(length=255), nullable=False),
        sa.Column('message_body', sa.Text(), nullable=False),
        sa.Column('offer_code', sa.String(length=100), nullable=True),
        sa.Column('offer_details', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='DELIVERED'),
        sa.Column('handed_off_to', sa.String(length=50), nullable=True),
        sa.Column('task_id', sa.String(length=64), nullable=True),
        sa.Column('delivered_at', sa.DateTime(), nullable=False),
        sa.Column('responded_at', sa.DateTime(), nullable=True),
        sa.Column('merchant_response', sa.String(length=50), nullable=True),
        sa.Column('is_synthetic', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('environment', sa.String(length=32), nullable=False, server_default='DEMO'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('merchant_followups')
    op.drop_table('merchant_activity_metrics')
