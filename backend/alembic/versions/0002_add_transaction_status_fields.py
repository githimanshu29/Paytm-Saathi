"""add_transaction_status_fields

Revision ID: 0002_add_transaction_status_fields
Revises: 0001_initial_schema
Create Date: 2026-10-29 17:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002_add_transaction_status_fields'
down_revision: Union[str, None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column('bank_response_code', sa.String(length=50), nullable=True))
    op.add_column('transactions', sa.Column('reversal_status', sa.String(length=50), nullable=True))
    op.add_column('transactions', sa.Column('payer_vpa', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('transactions', 'payer_vpa')
    op.drop_column('transactions', 'reversal_status')
    op.drop_column('transactions', 'bank_response_code')
