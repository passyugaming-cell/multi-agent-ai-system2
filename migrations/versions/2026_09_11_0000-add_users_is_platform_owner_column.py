"""add_users_is_platform_owner_column

Revision ID: add_platform_owner_col
Revises: add_active_conn_uniq_idx
Create Date: 2026-09-11 00:00:00.000000+00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_platform_owner_col'
down_revision: Union[str, None] = 'add_active_conn_uniq_idx'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_platform_owner', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'is_platform_owner')
