"""add_users_role_column

Revision ID: add_users_role_col
Revises: 61gbizdata01
Create Date: 2026-09-08 00:00:00.000000+00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_users_role_col'
down_revision: Union[str, None] = '61gbizdata01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('role', sa.String(length=50), server_default='owner', nullable=False))
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.create_check_constraint('ck_users_role_valid', 'users', sa.text("role IN ('owner', 'admin', 'member')"))


def downgrade() -> None:
    op.drop_constraint('ck_users_role_valid', 'users', type_='check')
    op.drop_column('users', 'role')
