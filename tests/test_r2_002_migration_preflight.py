import os
import uuid
from decimal import Decimal
import pytest
from sqlalchemy import select, text
from alembic.config import Config
from alembic import command
from app.core.config import settings

from app.database.models.tenant import Tenant
from app.database.models.billing import Payment, Invoice
from app.billing.invoices import InvoiceService
from app.billing.state_machine import PaymentStatus


# MIGRATION PREFLIGHT TEST FOR DUPLICATE DATA (FINDINGS 3 & 5)
@pytest.mark.asyncio
async def test_r2_002_migration_preflight_duplicate_data_rejection(test_session_factory, tenant_a: Tenant, tenant_b: Tenant):
    """FINDINGS 3 & 5: Verifies that Alembic migration upgrade preflight blocks deployment when duplicate payment records exist (including empty strings)."""
    async with test_session_factory() as db_session:
        # Re-create payments table without unique constraint to simulate pre-migration state on SQLite/PostgreSQL
        if db_session.bind.dialect.name == "sqlite":
            await db_session.execute(text("PRAGMA foreign_keys=OFF;"))
            await db_session.execute(text("DROP TABLE IF EXISTS payments;"))
            await db_session.execute(text("""
                CREATE TABLE payments (
                    id CHAR(32) NOT NULL PRIMARY KEY,
                    tenant_id CHAR(32) NOT NULL,
                    invoice_id CHAR(32) NOT NULL,
                    amount NUMERIC(14, 2) NOT NULL,
                    refunded_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
                    currency VARCHAR(10) NOT NULL DEFAULT 'IDR',
                    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                    provider VARCHAR(100) NOT NULL DEFAULT 'fake',
                    provider_payment_id VARCHAR(255),
                    attempted_at DATETIME,
                    paid_at DATETIME,
                    failed_at DATETIME,
                    failure_reason TEXT,
                    metadata JSON,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                );
            """))
            await db_session.execute(text("PRAGMA foreign_keys=ON;"))
        else:
            await db_session.execute(text("ALTER TABLE payments DROP CONSTRAINT IF EXISTS uq_payments_tenant_provider_payment_id;"))
        await db_session.commit()

        # Stamp alembic_version to revision prior to uq_payments_tenant_provider_payment_id
        await db_session.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num));"))
        await db_session.execute(text("DELETE FROM alembic_version;"))
        await db_session.execute(text("INSERT INTO alembic_version (version_num) VALUES ('add_phase_a_parent_comp_uniq');"))
        await db_session.commit()

        # Insert duplicate payment records with empty-string provider_payment_id
        inv_service = InvoiceService(db_session)
        inv1 = await inv_service.create_invoice(tenant_id=tenant_a.id, items_data=[{"description": "Inv 1", "unit_price": "100000.00"}])
        inv2 = await inv_service.create_invoice(tenant_id=tenant_a.id, items_data=[{"description": "Inv 2", "unit_price": "100000.00"}])

        p1_id = uuid.uuid4()
        p2_id = uuid.uuid4()

        p1 = Payment(
            id=p1_id,
            tenant_id=tenant_a.id,
            invoice_id=inv1.id,
            amount=Decimal("100000.00"),
            currency="IDR",
            status=PaymentStatus.PENDING,
            provider="midtrans",
            provider_payment_id="",
        )
        p2 = Payment(
            id=p2_id,
            tenant_id=tenant_a.id,
            invoice_id=inv2.id,
            amount=Decimal("100000.00"),
            currency="IDR",
            status=PaymentStatus.PENDING,
            provider="midtrans",
            provider_payment_id="",
        )
        db_session.add_all([p1, p2])
        await db_session.commit()

    # Invoke Alembic upgrade head against active DB engine
    alembic_cfg = Config("alembic.ini")
    active_db_url = os.getenv("TEST_DATABASE_URL") or settings.DATABASE_URL
    alembic_cfg.set_main_option("sqlalchemy.url", active_db_url)

    with pytest.raises(Exception) as exc_info:
        command.upgrade(alembic_cfg, "head")

    assert "Deployment blocked: Duplicate payment records found before migration" in str(exc_info.value)

    # Verify duplicate records were NOT silently deleted
    async with test_session_factory() as check_session:
        stmt = select(Payment).where(Payment.id.in_([p1_id, p2_id]))
        pmts = (await check_session.execute(stmt)).scalars().all()
        assert len(pmts) == 2

        # Clean up duplicates and re-run migration to verify clean-data upgrade succeeds
        for p in pmts:
            await check_session.delete(p)
        await check_session.commit()

    # Clean upgrade re-run
    command.upgrade(alembic_cfg, "head")
