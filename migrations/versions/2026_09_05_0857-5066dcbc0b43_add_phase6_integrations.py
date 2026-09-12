"""add_phase6_integrations

Revision ID: 5066dcbc0b43
Revises: '72dbe1a9c9ce'
Create Date: 2026-09-05 08:57:23.510518+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5066dcbc0b43'
down_revision: Union[str, None] = '72dbe1a9c9ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. integrations
    op.create_table(
        'integrations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=True),
        sa.Column('integration_key', sa.String(length=100), nullable=False),
        sa.Column('provider_key', sa.String(length=100), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False, server_default='general'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='AVAILABLE'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('configuration', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('integration_key', 'tenant_id', name='uq_integrations_key_tenant'),
    )
    op.create_index('ix_integrations_integration_key', 'integrations', ['integration_key'], unique=False)
    op.create_index('ix_integrations_provider_key', 'integrations', ['provider_key'], unique=False)
    op.create_index('ix_integrations_tenant_id', 'integrations', ['tenant_id'], unique=False)
    op.create_index('ix_integrations_provider', 'integrations', ['provider_key'], unique=False)
    op.create_index('ix_integrations_tenant', 'integrations', ['tenant_id'], unique=False)

    # 2. integration_connections
    op.create_table(
        'integration_connections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('provider_key', sa.String(length=100), nullable=False, server_default=''),
        sa.Column('integration_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='DISCONNECTED'),
        sa.Column('external_account_id', sa.String(length=255), nullable=True),
        sa.Column('meta_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('last_connected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'integration_id', 'external_account_id', name='uq_integration_connections_account'),
    )
    op.create_index('ix_integration_connections_integration_id', 'integration_connections', ['integration_id'], unique=False)
    op.create_index('ix_integration_connections_provider_key', 'integration_connections', ['provider_key'], unique=False)
    op.create_index('ix_integration_connections_status', 'integration_connections', ['status'], unique=False)
    op.create_index('ix_integration_connections_tenant_id', 'integration_connections', ['tenant_id'], unique=False)
    op.create_index('ix_integration_connections_tenant_status', 'integration_connections', ['tenant_id', 'status'], unique=False)

    # 3. integration_credentials
    op.create_table(
        'integration_credentials',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('connection_id', sa.UUID(), nullable=False),
        sa.Column('credential_type', sa.String(length=50), nullable=False),
        sa.Column('encrypted_secret', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['connection_id'], ['integration_connections.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_integration_credentials_connection_id', 'integration_credentials', ['connection_id'], unique=False)
    op.create_index('ix_integration_credentials_tenant_conn', 'integration_credentials', ['tenant_id', 'connection_id'], unique=False)
    op.create_index('ix_integration_credentials_tenant_id', 'integration_credentials', ['tenant_id'], unique=False)

    # 4. integration_executions
    op.create_table(
        'integration_executions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('connection_id', sa.UUID(), nullable=False),
        sa.Column('operation', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='PENDING'),
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
        sa.Column('correlation_id', sa.String(length=255), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_code', sa.String(length=100), nullable=True),
        sa.Column('safe_error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('request_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('response_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['connection_id'], ['integration_connections.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_integration_executions_connection_id', 'integration_executions', ['connection_id'], unique=False)
    op.create_index('ix_integration_executions_correlation_id', 'integration_executions', ['correlation_id'], unique=False)
    op.create_index('ix_integration_executions_idempotency', 'integration_executions', ['tenant_id', 'idempotency_key'], unique=False)
    op.create_index('ix_integration_executions_idempotency_key', 'integration_executions', ['idempotency_key'], unique=False)
    op.create_index('ix_integration_executions_status', 'integration_executions', ['status'], unique=False)
    op.create_index('ix_integration_executions_tenant_id', 'integration_executions', ['tenant_id'], unique=False)
    op.create_index('ix_integration_executions_tenant_status', 'integration_executions', ['tenant_id', 'status'], unique=False)

    # 5. webhook_configs
    op.create_table(
        'webhook_configs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('connection_id', sa.UUID(), nullable=True),
        sa.Column('webhook_type', sa.String(length=50), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('encrypted_secret', sa.Text(), nullable=True),
        sa.Column('event_types', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.ForeignKeyConstraint(['connection_id'], ['integration_connections.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_webhook_configs_connection_id', 'webhook_configs', ['connection_id'], unique=False)
    op.create_index('ix_webhook_configs_tenant_id', 'webhook_configs', ['tenant_id'], unique=False)
    op.create_index('ix_webhook_configs_tenant_type', 'webhook_configs', ['tenant_id', 'webhook_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_webhook_configs_tenant_type', table_name='webhook_configs')
    op.drop_index('ix_webhook_configs_tenant_id', table_name='webhook_configs')
    op.drop_index('ix_webhook_configs_connection_id', table_name='webhook_configs')
    op.drop_table('webhook_configs')

    op.drop_index('ix_integration_executions_tenant_status', table_name='integration_executions')
    op.drop_index('ix_integration_executions_tenant_id', table_name='integration_executions')
    op.drop_index('ix_integration_executions_status', table_name='integration_executions')
    op.drop_index('ix_integration_executions_idempotency_key', table_name='integration_executions')
    op.drop_index('ix_integration_executions_idempotency', table_name='integration_executions')
    op.drop_index('ix_integration_executions_correlation_id', table_name='integration_executions')
    op.drop_index('ix_integration_executions_connection_id', table_name='integration_executions')
    op.drop_table('integration_executions')

    op.drop_index('ix_integration_credentials_tenant_id', table_name='integration_credentials')
    op.drop_index('ix_integration_credentials_tenant_conn', table_name='integration_credentials')
    op.drop_index('ix_integration_credentials_connection_id', table_name='integration_credentials')
    op.drop_table('integration_credentials')

    op.drop_index('ix_integration_connections_tenant_status', table_name='integration_connections')
    op.drop_index('ix_integration_connections_tenant_id', table_name='integration_connections')
    op.drop_index('ix_integration_connections_status', table_name='integration_connections')
    op.drop_index('ix_integration_connections_provider_key', table_name='integration_connections')
    op.drop_index('ix_integration_connections_integration_id', table_name='integration_connections')
    op.drop_table('integration_connections')

    op.drop_index('ix_integrations_tenant_id', table_name='integrations')
    op.drop_index('ix_integrations_tenant', table_name='integrations')
    op.drop_index('ix_integrations_provider_key', table_name='integrations')
    op.drop_index('ix_integrations_provider', table_name='integrations')
    op.drop_index('ix_integrations_integration_key', table_name='integrations')
    op.drop_table('integrations')
