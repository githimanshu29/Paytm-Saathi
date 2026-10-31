"""add onboarding and kyc documents

Revision ID: 0006_add_onboarding_and_kyc_documents
Revises: 0005_add_revive_metrics_and_followups
Create Date: 2026-10-29 22:36:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0006_add_onboarding_and_kyc_documents'
down_revision: Union[str, None] = '0005_add_revive_metrics_and_followups'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'merchant_documents',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('tenant_id', sa.String(length=64), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('merchant_id', sa.String(length=64), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('document_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='MISSING'),
        sa.Column('file_url', sa.String(length=512), nullable=True),
        sa.Column('file_name', sa.String(length=255), nullable=True),
        sa.Column('ocr_quality_flag', sa.String(length=50), nullable=True),
        sa.Column('ocr_candidate_fields', sa.Text(), nullable=True),
        sa.Column('ocr_confidence', sa.Float(), nullable=True),
        sa.Column('is_ocr_passed', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('rejection_reason', sa.String(length=255), nullable=True),
        sa.Column('authorized_verification_status', sa.String(length=50), nullable=False, server_default='PENDING'),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('is_synthetic', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('environment', sa.String(length=32), nullable=False, server_default='DEMO'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('merchant_documents')
