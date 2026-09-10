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
    conn = op.get_bind()

    # 1. Add provider_key column to integration_connections if not exists
    try:
        op.add_column(
            'integration_connections',
            sa.Column('provider_key', sa.String(length=100), nullable=False, server_default='', index=True),
        )
    except Exception:
        pass

    # Populate provider_key from integrations for existing connection records
    conn.execute(sa.text("""
        UPDATE integration_connections
        SET provider_key = (
            SELECT integrations.provider_key
            FROM integrations
            WHERE integrations.id = integration_connections.integration_id
        )
        WHERE provider_key = '' OR provider_key IS NULL
    """))

    # 2. Preflight check for duplicate catalog integration records
    catalog_dup_check = sa.text("""
        SELECT provider_key, COUNT(*) as cnt
        FROM integrations
        WHERE tenant_id IS NULL AND provider_key IS NOT NULL
        GROUP BY provider_key
        HAVING COUNT(*) > 1
    """)
    cat_dups = conn.execute(catalog_dup_check).fetchall()
    if cat_dups:
        raise Exception(
            "Deployment blocked: Pre-existing duplicate catalog integrations found for provider_key; clean duplicates before migration."
        )

    # 3. Create catalog integration provider singleton index
    op.create_index(
        'uq_catalog_integrations_provider',
        'integrations',
        ['provider_key'],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
        sqlite_where=sa.text("tenant_id IS NULL"),
    )

    # 4. Preflight check for duplicate active integration connections
    conn_dup_check = sa.text("""
        SELECT provider_key, external_account_id, COUNT(*) as cnt
        FROM integration_connections
        WHERE status IN ('ACTIVE', 'CONNECTED', 'CONNECTING')
          AND external_account_id IS NOT NULL
        GROUP BY provider_key, external_account_id
        HAVING COUNT(*) > 1
    """)
    conn_dups = conn.execute(conn_dup_check).fetchall()
    if conn_dups:
        conn_desc = ", ".join([f"(provider_key={r[0]}, account={r[1]}, count={r[2]})" for r in conn_dups])
        raise Exception(
            f"Deployment blocked: Pre-existing active duplicate connections found. Resolve duplicate integration connections before applying uq_active_provider_external_account: {conn_desc}."
        )

    # 5. Create active connection provider/external account unique index
    op.create_index(
        'uq_active_provider_external_account',
        'integration_connections',
        ['provider_key', 'external_account_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('ACTIVE', 'CONNECTED', 'CONNECTING') AND external_account_id IS NOT NULL"),
        sqlite_where=sa.text("status IN ('ACTIVE', 'CONNECTED', 'CONNECTING') AND external_account_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index('uq_active_provider_external_account', table_name='integration_connections')
    op.drop_index('uq_catalog_integrations_provider', table_name='integrations')
    try:
        op.drop_column('integration_connections', 'provider_key')
    except Exception:
        pass
