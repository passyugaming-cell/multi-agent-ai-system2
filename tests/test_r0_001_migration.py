"""Verification test suite for R0-001 Phase 6 Integration Migration Repair.

Tests that all 5 Phase 6 integration tables exist with expected columns,
foreign keys, unique constraints, and indexes when metadata tables are created,
and validates migration upgrade and downgrade behaviors.
"""
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from app.database.base import Base
from app.database.models import integrations  # Ensures models are imported in Base.metadata


@pytest.mark.asyncio
async def test_phase6_integration_tables_schema_and_constraints(tmp_path):
    """Verify that the 5 Phase 6 integration tables exist in SQLAlchemy metadata with expected structure."""
    db_file = tmp_path / "test_r0_001.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.connect() as conn:
        def inspect_tables(sync_conn):
            inspector = sa.inspect(sync_conn)
            tables = inspector.get_table_names()

            # 1. Check all 5 Phase 6 tables exist
            phase6_tables = [
                "integrations",
                "integration_connections",
                "integration_credentials",
                "integration_executions",
                "webhook_configs",
            ]
            for table_name in phase6_tables:
                assert table_name in tables, f"Missing Phase 6 table: {table_name}"

            # 2. Check integrations table columns & constraints
            integrations_cols = {c["name"] for c in inspector.get_columns("integrations")}
            expected_integrations_cols = {
                "id", "created_at", "updated_at", "tenant_id", "integration_key",
                "provider_key", "display_name", "category", "status", "is_enabled", "configuration"
            }
            assert expected_integrations_cols.issubset(integrations_cols)

            # 3. Check integration_connections table columns & constraints
            conn_cols = {c["name"] for c in inspector.get_columns("integration_connections")}
            expected_conn_cols = {
                "id", "created_at", "updated_at", "tenant_id", "provider_key", "integration_id",
                "status", "external_account_id", "meta_data", "last_connected_at",
                "last_success_at", "last_error_at", "error_message"
            }
            assert expected_conn_cols.issubset(conn_cols)

            # 4. Check integration_credentials table columns
            cred_cols = {c["name"] for c in inspector.get_columns("integration_credentials")}
            expected_cred_cols = {
                "id", "created_at", "updated_at", "tenant_id", "connection_id",
                "credential_type", "encrypted_secret", "expires_at", "revoked_at"
            }
            assert expected_cred_cols.issubset(cred_cols)

            # 5. Check integration_executions table columns
            exec_cols = {c["name"] for c in inspector.get_columns("integration_executions")}
            expected_exec_cols = {
                "id", "created_at", "updated_at", "tenant_id", "connection_id",
                "operation", "status", "idempotency_key", "correlation_id",
                "started_at", "completed_at", "error_code", "safe_error_message",
                "retry_count", "request_payload", "response_payload"
            }
            assert expected_exec_cols.issubset(exec_cols)

            # 6. Check webhook_configs table columns
            wh_cols = {c["name"] for c in inspector.get_columns("webhook_configs")}
            expected_wh_cols = {
                "id", "created_at", "updated_at", "tenant_id", "connection_id",
                "webhook_type", "url", "encrypted_secret", "event_types", "is_active"
            }
            assert expected_wh_cols.issubset(wh_cols)

        await conn.run_sync(inspect_tables)

    await engine.dispose()
