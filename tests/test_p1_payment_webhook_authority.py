import uuid
import hashlib
from decimal import Decimal
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.integrations.adapters.midtrans import MidtransAdapter

from app.integrations.service import IntegrationService
from app.billing.invoices import InvoiceService
from app.billing.payments import PaymentService
from app.billing.plans import PlanService
from app.billing.subscription import SubscriptionService
from app.billing.provider import FakePaymentProvider, MidtransPaymentProvider
from app.integrations.permissions import MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS


@pytest.fixture(autouse=True)
async def seed_midtrans_catalog(db_session):
    from app.database.models.integrations import Integration
    from sqlalchemy import select
    stmt = select(Integration).where(Integration.integration_key == "midtrans")
    existing = (await db_session.execute(stmt)).scalar_one_or_none()
    if not existing:
        midtrans_int = Integration(
            integration_key="midtrans",
            provider_key="midtrans",
            display_name="Midtrans Payment Gateway",
            category="payment",
            is_enabled=True,
        )
        db_session.add(midtrans_int)
        await db_session.commit()


@pytest.mark.asyncio
async def test_01_valid_webhook_updates_payment_state(async_client: AsyncClient, tenant_a, db_session: AsyncSession):
    """Valid webhook payload delegates strictly to PaymentService and updates state."""
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "test_server_key_1"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Pro Plan", "unit_price": Decimal("100000.00"), "quantity": 1}],
    )

    midtrans_prov = MidtransPaymentProvider(server_key="test_server_key_1")
    pay_service = PaymentService(db_session, provider=midtrans_prov)
    with patch.object(MidtransAdapter, "create_payment", new=AsyncMock(return_value={"success": True, "transaction_id": str(invoice.id), "transaction_status": "pending"})):
        payment = await pay_service.create_payment_intent(
            tenant_id=tenant_a.id,
            invoice_id=invoice.id,
            amount=invoice.total,
        )
    await db_session.commit()

    raw_str = f"{invoice.id}200100000.00test_server_key_1"
    sig = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()

    payload = {
        "order_id": str(invoice.id),
        "status_code": "200",
        "gross_amount": "100000.00",
        "signature_key": sig,
        "transaction_status": "settlement",
        "transaction_id": "tx_midtrans_999",
    }

    resp = await async_client.post("/api/v1/webhooks/midtrans", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "PROCESSED"

    await db_session.refresh(payment)
    assert payment.status == "SUCCEEDED"


@pytest.mark.asyncio
async def test_02_invalid_signature_rejected(async_client: AsyncClient, tenant_a, db_session: AsyncSession):
    """Invalid signature payload is rejected with HTTP 401 UNAUTHORIZED."""
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "real_server_key"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item 1", "unit_price": Decimal("50000.00"), "quantity": 1}],
    )

    payload = {
        "order_id": str(invoice.id),
        "status_code": "200",
        "gross_amount": "50000.00",
        "signature_key": "invalid_forged_signature",
        "transaction_status": "settlement",
    }

    resp = await async_client.post("/api/v1/webhooks/midtrans", json=payload)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_03_unmatched_webhook_no_internal_intent_rejected(async_client: AsyncClient, tenant_a, db_session: AsyncSession):
    """Webhook for an invoice without an internal payment intent is REJECTED without creating payment truth."""
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_no_intent"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item 1", "unit_price": Decimal("75000.00"), "quantity": 1}],
    )

    raw_str = f"{invoice.id}20075000.00key_no_intent"
    sig = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()

    payload = {
        "order_id": str(invoice.id),
        "status_code": "200",
        "gross_amount": "75000.00",
        "signature_key": sig,
        "transaction_status": "settlement",
        "transaction_id": "tx_unmatched_123",
    }

    resp = await async_client.post("/api/v1/webhooks/midtrans", json=payload)
    assert resp.status_code == 400
    err_msg = str(resp.json())
    assert "Unmatched webhook rejected" in err_msg


@pytest.mark.asyncio
async def test_04_amount_mismatch_rejected(async_client: AsyncClient, tenant_a, db_session: AsyncSession):
    """Webhook amount mismatch against authoritative invoice is rejected."""
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_amt_mismatch"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item 1", "unit_price": Decimal("100000.00"), "quantity": 1}],
    )

    midtrans_prov = MidtransPaymentProvider(server_key="key_amt_mismatch")
    pay_service = PaymentService(db_session, provider=midtrans_prov)
    with patch.object(MidtransAdapter, "create_payment", new=AsyncMock(return_value={"success": True, "transaction_id": str(invoice.id), "transaction_status": "pending"})):
        await pay_service.create_payment_intent(
            tenant_id=tenant_a.id,
            invoice_id=invoice.id,
            amount=invoice.total,
        )
    await db_session.commit()

    raw_str = f"{invoice.id}200200000.00key_amt_mismatch"
    sig = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()

    payload = {
        "order_id": str(invoice.id),
        "status_code": "200",
        "gross_amount": "200000.00",  # Mismatch: Invoice is 100000.00
        "signature_key": sig,
        "transaction_status": "settlement",
    }

    resp = await async_client.post("/api/v1/webhooks/midtrans", json=payload)
    assert resp.status_code == 400
    err_msg = str(resp.json()).lower()
    assert "amount" in err_msg


@pytest.mark.asyncio
async def test_05_cross_tenant_payload_override_rejected(async_client: AsyncClient, tenant_a, tenant_b, db_session: AsyncSession):
    """Attempting cross-tenant payment reference or override fails closed."""
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_cross"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    inv_service = InvoiceService(db_session)
    invoice_a = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Tenant A Item", "unit_price": Decimal("50000.00"), "quantity": 1}],
    )

    midtrans_prov = MidtransPaymentProvider(server_key="key_cross")
    pay_service = PaymentService(db_session, provider=midtrans_prov)
    with patch.object(MidtransAdapter, "create_payment", new=AsyncMock(return_value={"success": True, "transaction_id": str(invoice_a.id), "transaction_status": "pending"})):
        await pay_service.create_payment_intent(
            tenant_id=tenant_a.id,
            invoice_id=invoice_a.id,
            amount=invoice_a.total,
        )
    await db_session.commit()

    raw_str = f"{invoice_a.id}20050000.00key_cross"
    sig = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()

    payload = {
        "order_id": str(invoice_a.id),
        "status_code": "200",
        "gross_amount": "50000.00",
        "signature_key": sig,
        "transaction_status": "settlement",
        "tenant_id": str(tenant_b.id),  # Attempting to override tenant_id in payload
    }

    resp = await async_client.post("/api/v1/webhooks/midtrans", json=payload)
    assert resp.status_code == 400
    err_msg = str(resp.json())
    assert "Unmatched webhook rejected" in err_msg


@pytest.mark.asyncio
async def test_06_idempotent_duplicate_webhooks(async_client: AsyncClient, tenant_a, db_session: AsyncSession):
    """Duplicate webhooks return idempotent response without duplicating state mutations."""
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_idemp_1"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item 1", "unit_price": Decimal("10000.00"), "quantity": 1}],
    )

    midtrans_prov = MidtransPaymentProvider(server_key="key_idemp_1")
    pay_service = PaymentService(db_session, provider=midtrans_prov)
    with patch.object(MidtransAdapter, "create_payment", new=AsyncMock(return_value={"success": True, "transaction_id": "tx_idemp_fixed_100", "transaction_status": "pending"})):
        await pay_service.create_payment_intent(
            tenant_id=tenant_a.id,
            invoice_id=invoice.id,
            amount=invoice.total,
        )
    await db_session.commit()

    raw_str = f"{invoice.id}20010000.00key_idemp_1"
    sig = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()

    payload = {
        "order_id": str(invoice.id),
        "transaction_id": "tx_idemp_fixed_100",
        "status_code": "200",
        "gross_amount": "10000.00",
        "signature_key": sig,
        "transaction_status": "settlement",
    }

    resp1 = await async_client.post("/api/v1/webhooks/midtrans", json=payload)
    assert resp1.status_code == 200
    assert resp1.json().get("idempotent") is not True

    resp2 = await async_client.post("/api/v1/webhooks/midtrans", json=payload)
    assert resp2.status_code == 200
    assert resp2.json().get("idempotent") is True


@pytest.mark.asyncio
async def test_07_unknown_invoice_id_rejected(async_client: AsyncClient, tenant_a, db_session: AsyncSession):
    """Webhook targeting an unknown non-existent order_id/invoice_id is rejected with HTTP 404."""
    unknown_id = str(uuid.uuid4())
    payload = {
        "order_id": unknown_id,
        "status_code": "200",
        "gross_amount": "10000.00",
        "signature_key": "some_sig",
        "transaction_status": "settlement",
    }

    resp = await async_client.post("/api/v1/webhooks/midtrans", json=payload)
    assert resp.status_code == 404
