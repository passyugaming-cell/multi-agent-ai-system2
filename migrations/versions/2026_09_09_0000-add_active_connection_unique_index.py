"""add_active_connection_unique_index

Revision ID: add_active_conn_uniq_idx
Revises: add_users_role_col
Create Date: 2026-09-09 00:00:00.000000+00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_active_conn_uniq_idx'
down_revision: Union[str, None] = 'add_users_role_col'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'uq_active_provider_external_account',
        'integration_connections',
        ['integration_id', 'external_account_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('ACTIVE', 'CONNECTED', 'CONNECTING') AND external_account_id IS NOT NULL"),
        sqlite_where=sa.text("status IN ('ACTIVE', 'CONNECTED', 'CONNECTING') AND external_account_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index('uq_active_provider_external_account', table_name='integration_connections')
