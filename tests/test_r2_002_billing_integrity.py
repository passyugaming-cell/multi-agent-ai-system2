import asyncio
import os
import uuid
from decimal import Decimal
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from alembic.config import Config
from alembic import command
from app.core.config import settings

from app.database.models.tenant import Tenant
from app.database.models.user import User
from app.database.models.billing import Payment, Invoice, Subscription
from app.database.models.workflow import Approval
from app.billing.plans import PlanService
from app.billing.subscription import SubscriptionService
from app.billing.invoices import InvoiceService, RevenueType
from app.billing.payments import PaymentService
from app.billing.refunds import RefundService
from app.billing.state_machine import PaymentStatus, InvoiceStatus, SubscriptionStatus
from app.billing.exceptions import BillingError, PaymentFailedError, InvalidPaymentStateError
from app.billing.provider import PaymentProvider, PaymentResult, WebhookResult, RefundResult
from app.core.auth_service import hash_password, create_access_token


class MockFailingRefundProvider(PaymentProvider):
    provider_name = "mock_failing_refund"

    async def create_payment(self, tenant_id: uuid.UUID, invoice_id: uuid.UUID, amount: Decimal, currency: str = "IDR") -> PaymentResult:
        return PaymentResult(success=True, provider_payment_id=f"pay_fail_ref_{uuid.uuid4().hex[:8]}", status="PENDING")

    async def verify_payment(self, provider_payment_id: str) -> PaymentResult:
        return PaymentResult(success=True, provider_payment_id=provider_payment_id, status="SUCCEEDED")

    async def handle_webhook(self, payload: dict, headers: dict, secret: str = None) -> WebhookResult:
        return WebhookResult(
            event_type="payment.succeeded",
            provider_payment_id=payload.get("provider_payment_id", "pay_test"),
            tenant_id=uuid.UUID(payload["tenant_id"]),
            invoice_id=uuid.UUID(payload["invoice_id"]),
            amount=Decimal(str(payload.get("amount", "100000.00"))),
            status="SUCCEEDED",
        )

    async def refund(self, provider_payment_id: str, amount: Decimal, reason: str | None = None) -> RefundResult:
        return RefundResult(
            success=False,
            refund_id=f"ref_fail_{uuid.uuid4().hex[:8]}",
            amount=amount,
            error_message="Simulated bank timeout during refund execution.",
        )


@pytest.fixture(autouse=True)
def mock_redis_revocation(monkeypatch):
    revoked_jtis = set()

    async def mock_is_revoked(jti: str) -> bool:
        return jti in revoked_jtis

    async def mock_revoke(jti: str, exp_timestamp: int | None = None, ttl: int = 86400):
        revoked_jtis.add(jti)

    import app.core.auth_service as auth_srv
    import app.api.v1.auth as auth_api
    monkeypatch.setattr(auth_srv, "is_token_revoked_redis", mock_is_revoked)
    monkeypatch.setattr(auth_srv, "revoke_token_redis", mock_revoke)
    monkeypatch.setattr(auth_api, "revoke_token_redis", mock_revoke)


# PHASE 3 & 4: SECURITY & TENANT ISOLATION TESTS
@pytest.mark.asyncio
async def test_r2_002_security_negative_scenarios(client: AsyncClient, db_session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant):
    # Setup owner and member users
    owner_a = User(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        email=f"sec_owner_{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("Owner123!"),
        role="owner",
        is_active=True,
    )
    member_a = User(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        email=f"sec_member_{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("Member123!"),
        role="member",
        is_active=True,
    )
    db_session.add_all([owner_a, member_a])
    await db_session.commit()

    token_owner_a = create_access_token(
        data={"sub": owner_a.email, "user_id": str(owner_a.id), "tenant_ids": [str(tenant_a.id)], "active_tenant_id": str(tenant_a.id)}
    )
    token_member_a = create_access_token(
        data={"sub": member_a.email, "user_id": str(member_a.id), "tenant_ids": [str(tenant_a.id)], "active_tenant_id": str(tenant_a.id)}
    )

    # 1. Missing authentication -> DENIED (401 or 403)
    res = await client.get("/api/v1/billing/subscription", headers={"X-Tenant-ID": str(tenant_a.id)})
    assert res.status_code in (401, 403)

    # 2. Invalid authentication -> DENIED (401 or 403)
    res = await client.get("/api/v1/billing/subscription", headers={"X-Tenant-ID": str(tenant_a.id), "Authorization": "Bearer invalid_token"})
    assert res.status_code in (401, 403)

    # 3. Wrong tenant mismatch -> DENIED (403)
    res = await client.get("/api/v1/billing/subscription", headers={"X-Tenant-ID": str(tenant_b.id), "Authorization": f"Bearer {token_owner_a}"})
    assert res.status_code == 403

    # 4. Insufficient permission for subscription change -> DENIED (403)
    res = await client.post(
        "/api/v1/billing/subscription/change-plan",
        headers={"X-Tenant-ID": str(tenant_a.id), "Authorization": f"Bearer {token_member_a}"},
        json={"new_plan_code": "pro"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_r2_002_amount_currency_tampering_rejection(db_session: AsyncSession, tenant_a: Tenant):
    inv_service = InvoiceService(db_session)
    pay_service = PaymentService(db_session)

    inv = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Pro Plan", "unit_price": "799000.00", "quantity": 1}],
        currency="IDR",
    )

    # Requested amount differs from invoice total -> rejected
    with pytest.raises(PaymentFailedError) as exc_amount:
        await pay_service.create_payment_intent(tenant_a.id, inv.id, amount=Decimal("100000.00"))
    assert "amount mismatch" in str(exc_amount.value)

    # Requested currency differs from invoice currency -> rejected
    with pytest.raises(PaymentFailedError) as exc_curr:
        await pay_service.create_payment_intent(tenant_a.id, inv.id, amount=inv.total, currency="USD")
    assert "currency mismatch" in str(exc_curr.value)


# PHASE 2: GATED PAID ACTIVATION & PLAN CHANGE
@pytest.mark.asyncio
async def test_r2_002_paid_plan_activation_and_change_gating(db_session: AsyncSession, tenant_a: Tenant):
    sub_service = SubscriptionService(db_session)

    # Paid plan activation without verified payment -> throws BillingError (402)
    with pytest.raises(BillingError) as exc:
        await sub_service.activate_subscription(tenant_a.id, "pro", verified_payment=False)
    assert exc.value.status_code == 402

    # Paid plan change without verified payment -> throws BillingError (402)
    await sub_service.create_trial_subscription(tenant_a.id)
    with pytest.raises(BillingError) as exc_change:
        await sub_service.change_plan(tenant_a.id, "business", verified_payment=False)
    assert exc_change.value.status_code == 402


# MIGRATION PREFLIGHT TEST FOR DUPLICATE DATA (FINDING 3)
@pytest.mark.asyncio
async def test_r2_002_migration_preflight_duplicate_data_rejection(test_session_factory, tenant_a: Tenant, tenant_b: Tenant):
    """FINDING 3: Verifies that Alembic migration upgrade preflight blocks deployment when duplicate payment records exist."""
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

        # Insert duplicate payment records for same (tenant_id, provider, provider_payment_id)
        inv_service = InvoiceService(db_session)
        inv1 = await inv_service.create_invoice(tenant_id=tenant_a.id, items_data=[{"description": "Inv 1", "unit_price": "100000.00"}])
        inv2 = await inv_service.create_invoice(tenant_id=tenant_a.id, items_data=[{"description": "Inv 2", "unit_price": "100000.00"}])

        now_str = datetime.now(timezone.utc).isoformat()
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
            provider_payment_id="dup_provider_pay_123",
        )
        p2 = Payment(
            id=p2_id,
            tenant_id=tenant_a.id,
            invoice_id=inv2.id,
            amount=Decimal("100000.00"),
            currency="IDR",
            status=PaymentStatus.PENDING,
            provider="midtrans",
            provider_payment_id="dup_provider_pay_123",
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


# PHASE 5: IDEMPOTENCY & UNMATCHED WEBHOOK TESTS
@pytest.mark.asyncio
async def test_r2_002_unmatched_webhook_rejection(db_session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant):
    inv_service = InvoiceService(db_session)
    pay_service = PaymentService(db_session)

    inv_a = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item", "unit_price": "100000.00"}],
    )

    headers = {"X-Signature": "valid_test_signature"}

    # 1. Unmatched webhook: existing invoice + NO internal Payment intent -> REJECTED, NO Payment created
    no_payment_intent_payload = {
        "event": "payment.succeeded",
        "provider_payment_id": "pay_no_intent_123",
        "amount": "100000.00",
        "currency": "IDR",
        "status": "SUCCEEDED",
        "tenant_id": str(tenant_a.id),
        "invoice_id": str(inv_a.id),
    }
    with pytest.raises(PaymentFailedError) as exc_no_intent:
        await pay_service.handle_provider_webhook(no_payment_intent_payload, headers)
    assert "Unmatched webhook rejected" in str(exc_no_intent.value)

    # Verify NO payment row was created
    stmt_pmt = select(Payment).where(Payment.invoice_id == inv_a.id)
    assert (await db_session.execute(stmt_pmt)).scalar_one_or_none() is None

    # 2. Currency mismatch: 100000 USD vs 100000 IDR -> REJECTED
    # Create legitimate Payment intent first
    pmt_intent = await pay_service.create_payment_intent(tenant_a.id, inv_a.id, Decimal("100000.00"), "IDR")
    currency_mismatch_payload = {
        "event": "payment.succeeded",
        "provider_payment_id": pmt_intent.provider_payment_id,
        "amount": "100000.00",
        "currency": "USD",
        "status": "SUCCEEDED",
        "tenant_id": str(tenant_a.id),
        "invoice_id": str(inv_a.id),
    }
    with pytest.raises(PaymentFailedError) as exc_curr:
        await pay_service.handle_provider_webhook(currency_mismatch_payload, headers)
    assert "currency mismatch" in str(exc_curr.value).lower()

    # Verify Payment status remains PENDING and Invoice status remains ISSUED
    stmt_pmt_chk = select(Payment).where(Payment.id == pmt_intent.id)
    assert (await db_session.execute(stmt_pmt_chk)).scalar_one().status == PaymentStatus.PENDING
    stmt_inv_chk = select(Invoice).where(Invoice.id == inv_a.id)
    assert (await db_session.execute(stmt_inv_chk)).scalar_one().status == InvoiceStatus.ISSUED

    # 3. Unmatched webhook: fake non-existent invoice_id
    fake_payload = {
        "event": "payment.succeeded",
        "provider_payment_id": "pay_unmatched_123",
        "amount": "100000.00",
        "status": "SUCCEEDED",
        "tenant_id": str(tenant_a.id),
        "invoice_id": str(uuid.uuid4()),
    }
    with pytest.raises(PaymentFailedError) as exc_fake:
        await pay_service.handle_provider_webhook(fake_payload, headers)
    assert "Unmatched webhook rejected" in str(exc_fake.value)

    # 4. Unmatched webhook: tenant mismatch
    mismatch_payload = {
        "event": "payment.succeeded",
        "provider_payment_id": "pay_unmatched_456",
        "amount": "100000.00",
        "status": "SUCCEEDED",
        "tenant_id": str(tenant_b.id),
        "invoice_id": str(inv_a.id),
    }
    with pytest.raises(PaymentFailedError) as exc_mismatch:
        await pay_service.handle_provider_webhook(mismatch_payload, headers)
    assert "Unmatched webhook rejected" in str(exc_mismatch.value)


@pytest.mark.asyncio
async def test_r2_002_webhook_atomic_idempotency_and_concurrency(test_session_factory, tenant_a: Tenant):
    # Setup invoice AND legitimate internal payment intent first
    async with test_session_factory() as setup_session:
        inv_service = InvoiceService(setup_session)
        pay_service = PaymentService(setup_session)
        inv = await inv_service.create_invoice(
            tenant_id=tenant_a.id,
            items_data=[{"description": "Concurrent Item", "unit_price": "500000.00"}],
        )
        pmt = await pay_service.create_payment_intent(tenant_a.id, inv.id, Decimal("500000.00"))
        await setup_session.commit()
        inv_id = inv.id
        pmt_provider_id = pmt.provider_payment_id

    # Simulate concurrent webhook workers processing the exact same webhook payload
    async with test_session_factory() as session_1, test_session_factory() as session_2:
        webhook_payload = {
            "event": "payment.succeeded",
            "provider_payment_id": pmt_provider_id,
            "amount": "500000.00",
            "currency": "IDR",
            "status": "SUCCEEDED",
            "tenant_id": str(tenant_a.id),
            "invoice_id": str(inv_id),
        }
        headers = {"X-Signature": "valid_test_signature"}

        pay_service_1 = PaymentService(session_1)
        pay_service_2 = PaymentService(session_2)

        results = await asyncio.gather(
            pay_service_1.handle_provider_webhook(webhook_payload, headers),
            pay_service_2.handle_provider_webhook(webhook_payload, headers),
        )

        assert results[0].id == results[1].id
        assert results[0].status == PaymentStatus.SUCCEEDED
        assert results[1].status == PaymentStatus.SUCCEEDED

    async with test_session_factory() as session_check:
        stmt = select(Payment).where(
            and_(
                Payment.tenant_id == tenant_a.id,
                Payment.provider_payment_id == pmt_provider_id,
            )
        )
        payments = (await session_check.execute(stmt)).scalars().all()
        assert len(payments) == 1


# PHASE 7: REFUND TESTS
@pytest.mark.asyncio
async def test_r2_002_refund_full_and_partial_integrity(db_session: AsyncSession, tenant_a: Tenant):
    inv_service = InvoiceService(db_session)
    pay_service = PaymentService(db_session)
    refund_service = RefundService(db_session)

    inv = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Enterprise Plan", "unit_price": "100000.00"}],
    )
    pmt = await pay_service.create_payment_intent(tenant_a.id, inv.id, Decimal("100000.00"))
    await pay_service.confirm_payment_success(tenant_a.id, pmt.id)

    # 1. Partial refund 30,000 IDR
    app1 = await refund_service.request_refund(tenant_a.id, pmt.id, Decimal("30000.00"), "Partial refund 1")
    app1.status = "APPROVED"
    await db_session.flush()

    p_ref1 = await refund_service.execute_approved_refund(tenant_a.id, app1.id)
    assert p_ref1.status == PaymentStatus.PARTIALLY_REFUNDED
    assert p_ref1.refunded_amount == Decimal("30000.00")

    # 2. Exceeding remaining refundable amount (80,000 > 70,000) -> rejected
    with pytest.raises(BillingError) as exc_exceed:
        await refund_service.request_refund(tenant_a.id, pmt.id, Decimal("80000.00"), "Excess refund")
    assert "exceeds remaining refundable amount" in str(exc_exceed.value)

    # 3. Final partial refund 70,000 IDR -> brings total to 100,000 IDR -> status REFUNDED
    app2 = await refund_service.request_refund(tenant_a.id, pmt.id, Decimal("70000.00"), "Final partial refund")
    app2.status = "APPROVED"
    await db_session.flush()

    p_ref2 = await refund_service.execute_approved_refund(tenant_a.id, app2.id)
    assert p_ref2.status == PaymentStatus.REFUNDED
    assert p_ref2.refunded_amount == Decimal("100000.00")


@pytest.mark.asyncio
async def test_r2_002_refund_failure_persistence_and_concurrency(test_session_factory, tenant_a: Tenant):
    """FINDING 6: Verify refund failure persistence across independent DB sessions."""
    async with test_session_factory() as setup_session:
        inv_service = InvoiceService(setup_session)
        failing_provider = MockFailingRefundProvider()
        pay_service = PaymentService(setup_session, provider=failing_provider)
        refund_service = RefundService(setup_session)
        refund_service.payment_service = pay_service

        inv = await inv_service.create_invoice(
            tenant_id=tenant_a.id,
            items_data=[{"description": "Product", "unit_price": "200000.00"}],
        )
        pmt = await pay_service.create_payment_intent(tenant_a.id, inv.id, Decimal("200000.00"))
        await pay_service.confirm_payment_success(tenant_a.id, pmt.id)

        app = await refund_service.request_refund(tenant_a.id, pmt.id, Decimal("100000.00"), "Refund test")
        app.status = "APPROVED"
        await setup_session.commit()
        app_id, pmt_id = app.id, pmt.id

    async with test_session_factory() as exec_session:
        ref_srv = RefundService(exec_session)
        ref_srv.payment_service = PaymentService(exec_session, provider=MockFailingRefundProvider())

        with pytest.raises(PaymentFailedError):
            await ref_srv.execute_approved_refund(tenant_a.id, app_id)

    # Verify Approval status is persisted as FAILED with error message across a NEW independent session
    async with test_session_factory() as check_session:
        stmt = select(Approval).where(Approval.id == app_id)
        app_db = (await check_session.execute(stmt)).scalar_one()
        assert app_db.status == "FAILED"
        assert "Simulated bank timeout" in app_db.meta_data.get("failure_reason", "")

        stmt_pmt = select(Payment).where(Payment.id == pmt_id)
        pmt_db = (await check_session.execute(stmt_pmt)).scalar_one()
        assert pmt_db.refunded_amount == Decimal("0.00")
        assert pmt_db.status == PaymentStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_r2_002_concurrent_over_refund_prevention(test_session_factory, tenant_a: Tenant):
    """FINDING 1: Test two distinct refund approvals (60,000 and 50,000) on a 100,000 payment executed concurrently.

    Expectation: System MUST NOT over-refund (110,000). Total refunded must equal 60,000 or 50,000,
    and one operation must fail with remaining balance rejection.
    """
    async with test_session_factory() as setup_session:
        inv_service = InvoiceService(setup_session)
        pay_service = PaymentService(setup_session)
        refund_service = RefundService(setup_session)

        inv = await inv_service.create_invoice(
            tenant_id=tenant_a.id,
            items_data=[{"description": "Product", "unit_price": "100000.00"}],
        )
        pmt = await pay_service.create_payment_intent(tenant_a.id, inv.id, Decimal("100000.00"))
        await pay_service.confirm_payment_success(tenant_a.id, pmt.id)

        app1 = await refund_service.request_refund(tenant_a.id, pmt.id, Decimal("60000.00"), "Refund 60k")
        app1.status = "APPROVED"

        app2 = await refund_service.request_refund(tenant_a.id, pmt.id, Decimal("50000.00"), "Refund 50k")
        app2.status = "APPROVED"

        await setup_session.commit()
        pmt_id = pmt.id
        app1_id = app1.id
        app2_id = app2.id
        is_postgresql = setup_session.bind.dialect.name == "postgresql"

    async with test_session_factory() as session_1, test_session_factory() as session_2:
        ref_srv_1 = RefundService(session_1)
        ref_srv_2 = RefundService(session_2)

        if is_postgresql:
            results = await asyncio.gather(
                ref_srv_1.execute_approved_refund(tenant_a.id, app1_id),
                ref_srv_2.execute_approved_refund(tenant_a.id, app2_id),
                return_exceptions=True,
            )
            exceptions = [r for r in results if isinstance(r, Exception)]
            assert len(exceptions) >= 1
        else:
            # SQLite does not support FOR UPDATE row locks across concurrent async connections.
            # Test sequential execution on SQLite to prove business logic balance validation.
            p1 = await ref_srv_1.execute_approved_refund(tenant_a.id, app1_id)
            assert p1.refunded_amount == Decimal("60000.00")
            with pytest.raises(BillingError) as exc_info:
                await ref_srv_2.execute_approved_refund(tenant_a.id, app2_id)
            assert "exceeds remaining refundable amount" in str(exc_info.value)

    async with test_session_factory() as check_session:
        pmt_check = await PaymentService(check_session).get_payment(tenant_a.id, pmt_id)
        # Total refunded MUST NOT exceed 100,000 (must be 60,000 or 50,000)
        assert pmt_check.refunded_amount in (Decimal("60000.00"), Decimal("50000.00"))
        assert pmt_check.refunded_amount <= Decimal("100000.00")
        assert pmt_check.status == PaymentStatus.PARTIALLY_REFUNDED


@pytest.mark.asyncio
async def test_r2_002_concurrent_valid_partial_refunds(test_session_factory, tenant_a: Tenant):
    """FINDING 2: Test two valid partial refund approvals (60,000 and 40,000) on a 100,000 payment executed concurrently across independent DB sessions.

    Expectation: Both succeed, final refunded_amount == 100,000, Payment status == REFUNDED, no over-refund.
    """
    async with test_session_factory() as setup_session:
        inv_service = InvoiceService(setup_session)
        pay_service = PaymentService(setup_session)
        refund_service = RefundService(setup_session)

        inv = await inv_service.create_invoice(
            tenant_id=tenant_a.id,
            items_data=[{"description": "Product", "unit_price": "100000.00"}],
        )
        pmt = await pay_service.create_payment_intent(tenant_a.id, inv.id, Decimal("100000.00"))
        await pay_service.confirm_payment_success(tenant_a.id, pmt.id)

        app1 = await refund_service.request_refund(tenant_a.id, pmt.id, Decimal("60000.00"), "Refund 60k")
        app1.status = "APPROVED"

        app2 = await refund_service.request_refund(tenant_a.id, pmt.id, Decimal("40000.00"), "Refund 40k")
        app2.status = "APPROVED"

        await setup_session.commit()
        pmt_id = pmt.id
        app1_id = app1.id
        app2_id = app2.id
        is_postgresql = setup_session.bind.dialect.name == "postgresql"

    async with test_session_factory() as session_1, test_session_factory() as session_2:
        ref_srv_1 = RefundService(session_1)
        ref_srv_2 = RefundService(session_2)

        if is_postgresql:
            results = await asyncio.gather(
                ref_srv_1.execute_approved_refund(tenant_a.id, app1_id),
                ref_srv_2.execute_approved_refund(tenant_a.id, app2_id),
                return_exceptions=True,
            )
            for r in results:
                assert not isinstance(r, Exception), f"Unexpected exception in concurrent refund: {r}"
        else:
            await ref_srv_1.execute_approved_refund(tenant_a.id, app1_id)
            await ref_srv_2.execute_approved_refund(tenant_a.id, app2_id)

    async with test_session_factory() as check_session:
        pmt_check = await PaymentService(check_session).get_payment(tenant_a.id, pmt_id)
        assert pmt_check.refunded_amount == Decimal("100000.00")
        assert pmt_check.status == PaymentStatus.REFUNDED
