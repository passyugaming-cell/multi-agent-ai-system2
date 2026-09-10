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
    inspector = sa.inspect(conn)
    existing_cols = [c['name'] for c in inspector.get_columns('integration_connections')]

    # 1. Preflight check for orphaned integration_connections referencing non-existent integrations
    orphan_check = sa.text("""
        SELECT ic.id, ic.integration_id
        FROM integration_connections ic
        LEFT JOIN integrations i ON ic.integration_id = i.id
        WHERE i.id IS NULL
    """)
    orphans = conn.execute(orphan_check).fetchall()
    if orphans:
        orphan_ids = ", ".join([str(r[0]) for r in orphans[:5]])
        raise Exception(
            f"Deployment blocked: Orphaned integration connections found without matching parent integration (e.g., {orphan_ids}). Clean orphan records before migration."
        )

    # 2. Add provider_key column to integration_connections if not exists
    if 'provider_key' not in existing_cols:
        op.add_column(
            'integration_connections',
            sa.Column('provider_key', sa.String(length=100), nullable=False, server_default='', index=True),
        )

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

    # Verify post-backfill provider_key consistency
    empty_provider_check = sa.text("""
        SELECT COUNT(*)
        FROM integration_connections
        WHERE provider_key IS NULL OR provider_key = ''
    """)
    empty_count = conn.execute(empty_provider_check).scalar()
    if empty_count and empty_count > 0:
        raise Exception(
            f"Deployment blocked: {empty_count} connection records still have empty provider_key after backfill."
        )

    # 3. Preflight check for duplicate catalog integration records
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

    # 4. Create catalog integration provider singleton index
    op.create_index(
        'uq_catalog_integrations_provider',
        'integrations',
        ['provider_key'],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
        sqlite_where=sa.text("tenant_id IS NULL"),
    )

    # 5. Preflight check for duplicate active integration connections
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

    # 6. Create active connection provider/external account unique index
    op.create_index(
        'uq_active_provider_external_account',
        'integration_connections',
        ['provider_key', 'external_account_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('ACTIVE', 'CONNECTED', 'CONNECTING') AND external_account_id IS NOT NULL"),
        sqlite_where=sa.text("status IN ('ACTIVE', 'CONNECTED', 'CONNECTING') AND external_account_id IS NOT NULL"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = [c['name'] for c in inspector.get_columns('integration_connections')]

    op.drop_index('uq_active_provider_external_account', table_name='integration_connections')
    op.drop_index('uq_catalog_integrations_provider', table_name='integrations')
    if 'provider_key' in existing_cols:
        op.drop_column('integration_connections', 'provider_key')
