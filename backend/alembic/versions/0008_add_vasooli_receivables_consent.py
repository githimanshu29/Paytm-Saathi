"""add vasooli receivables consent and dispute tracking

Revision ID: 0008_add_vasooli_receivables_consent
Revises: 0007_add_fieldmate_sales_visits
Create Date: 2026-10-29 23:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0008_add_vasooli_receivables_consent'
down_revision: Union[str, None] = '0007_add_fieldmate_sales_visits'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add columns to customers
    with op.batch_alter_table('customers') as batch_op:
        batch_op.add_column(sa.Column('contact_permission', sa.Boolean(), nullable=False, server_default=sa.text('1')))
        batch_op.add_column(sa.Column('permission_status', sa.String(length=32), nullable=False, server_default='ALLOWED'))
        batch_op.add_column(sa.Column('permission_updated_at', sa.DateTime(), nullable=True))

    # 2. Add columns to receivables
    with op.batch_alter_table('receivables') as batch_op:
        batch_op.add_column(sa.Column('is_disputed', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('dispute_reason', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('reminder_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('last_reminder_sent_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('paid_amount', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('settled_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('settlement_verification_status', sa.String(length=50), nullable=False, server_default='UNSETTLED'))
        batch_op.add_column(sa.Column('payment_reference', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('payment_link_url', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('negotiated_installments', sa.Text(), nullable=True))

    # 3. Add receivable_id to action_approvals
    with op.batch_alter_table('action_approvals') as batch_op:
        batch_op.add_column(sa.Column('receivable_id', sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('action_approvals') as batch_op:
        batch_op.drop_column('receivable_id')

    with op.batch_alter_table('receivables') as batch_op:
        batch_op.drop_column('negotiated_installments')
        batch_op.drop_column('payment_link_url')
        batch_op.drop_column('payment_reference')
        batch_op.drop_column('settlement_verification_status')
        batch_op.drop_column('settled_at')
        batch_op.drop_column('paid_amount')
        batch_op.drop_column('last_reminder_sent_at')
        batch_op.drop_column('reminder_count')
        batch_op.drop_column('dispute_reason')
        batch_op.drop_column('is_disputed')

    with op.batch_alter_table('customers') as batch_op:
        batch_op.drop_column('permission_updated_at')
        batch_op.drop_column('permission_status')
        batch_op.drop_column('contact_permission')
