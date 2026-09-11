import pytest
import uuid
import hashlib
import hmac
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.integrations.adapters.midtrans import MidtransAdapter, SANDBOX_BASE_URL, PRODUCTION_BASE_URL
from app.integrations.registry import integration_registry
from app.integrations.exceptions import (
    PermanentIntegrationError,
    IntegrationNotFoundError,
    EntitlementDeniedError,
    PermissionDeniedError,
)
from app.billing.provider import MidtransPaymentProvider, PaymentResult, RefundResult
from app.integrations.service import IntegrationService
from app.billing.invoices import InvoiceService
from app.billing.payments import PaymentService
from app.billing.refunds import RefundService
from app.billing.plans import PlanService
from app.billing.subscription import SubscriptionService
from app.integrations.permissions import (
    MANAGE_INTEGRATIONS,
    MANAGE_CREDENTIALS,
    EXECUTE_INTEGRATION,
    VIEW_INTEGRATIONS,
    MANAGE_PAYMENTS,
    VIEW_PAYMENT_STATUS,
    REQUEST_REFUND,
)
from app.core.workflows.actions import ActionExecutor
from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context
from app.agents.owner_ai.tools import tool_get_midtrans_payment_status, tool_execute_integration_operation
from app.agents.base.schemas import ToolRequest
from app.core.approvals import ApprovalService
from app.database.models.workflow import Approval
from app.core.authority.schemas import ActionBinding


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
async def test_01_adapter_registration():
    assert integration_registry.is_registered("midtrans")
    adapter = integration_registry.get_adapter("midtrans")
    assert isinstance(adapter, MidtransAdapter)


@pytest.mark.asyncio
async def test_02_connect_missing_server_key():
    adapter = MidtransAdapter()
    with pytest.raises(PermanentIntegrationError):
        await adapter.connect(uuid.uuid4(), uuid.uuid4(), credentials={})


@pytest.mark.asyncio
async def test_03_connect_valid_server_key():
    adapter = MidtransAdapter()
    res = await adapter.connect(uuid.uuid4(), uuid.uuid4(), credentials={"server_key": "SB-Mid-server-test"})
    assert res is True


@pytest.mark.asyncio
async def test_04_disconnect_adapter():
    adapter = MidtransAdapter()
    res = await adapter.disconnect(uuid.uuid4(), uuid.uuid4(), credentials={"server_key": "SB-Mid-server-test"})
    assert res is True


@pytest.mark.asyncio
async def test_05_sandbox_vs_production_url():
    sandbox_adapter = MidtransAdapter(is_sandbox=True)
    prod_adapter = MidtransAdapter(is_sandbox=False)

    assert sandbox_adapter._get_base_url({"server_key": "sk"}) == SANDBOX_BASE_URL
    assert prod_adapter._get_base_url({"server_key": "sk"}) == PRODUCTION_BASE_URL
    assert sandbox_adapter._get_base_url({"server_key": "sk", "is_sandbox": False}) == PRODUCTION_BASE_URL


@pytest.mark.asyncio
async def test_06_execute_create_payment_success():
    adapter = MidtransAdapter(is_sandbox=True)
    mock_resp_data = {
        "transaction_id": "tx_12345",
        "transaction_status": "pending",
        "order_id": "inv_1001",
        "gross_amount": "150000.00",
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(status_code=200, json=lambda: mock_resp_data, content=b"{}")
        res = await adapter.execute(
            tenant_id=uuid.uuid4(),
            connection_id=uuid.uuid4(),
            credentials={"server_key": "SB-Server-Key"},
            operation="create_payment",
            params={"order_id": "inv_1001", "gross_amount": Decimal("150000.00")},
        )
        assert res["success"] is True
        assert res["transaction_id"] == "tx_12345"
        assert res["gross_amount"] == "150000.00"


@pytest.mark.asyncio
async def test_07_execute_create_payment_failure():
    adapter = MidtransAdapter()
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=400,
            json=lambda: {"status_message": "Access denied due to invalid server key"},
            content=b"{}",
        )
        res = await adapter.execute(
            tenant_id=uuid.uuid4(),
            connection_id=uuid.uuid4(),
            credentials={"server_key": "SB-Server-Key"},
            operation="create_payment",
            params={"order_id": "inv_1001", "gross_amount": Decimal("50000.00")},
        )
        assert res["success"] is False
        assert "Access denied" in res["error_message"]


@pytest.mark.asyncio
async def test_08_get_payment_status_success():
    adapter = MidtransAdapter()
    mock_data = {
        "order_id": "inv_1001",
        "transaction_id": "tx_12345",
        "transaction_status": "settlement",
        "gross_amount": "100000.00",
    }
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(status_code=200, json=lambda: mock_data)
        res = await adapter.get_payment_status({"server_key": "sk"}, "inv_1001")
        assert res["success"] is True
        assert res["normalized_status"] == "SUCCEEDED"


@pytest.mark.asyncio
async def test_09_get_payment_status_not_found():
    adapter = MidtransAdapter()
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(status_code=404, content=b"{}")
        with pytest.raises(IntegrationNotFoundError):
            await adapter.get_payment_status({"server_key": "sk"}, "inv_nonexistent")


@pytest.mark.asyncio
async def test_10_cancel_payment_success():
    adapter = MidtransAdapter()
    mock_data = {"order_id": "inv_1001", "transaction_id": "tx_12345", "transaction_status": "cancel"}
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(status_code=200, json=lambda: mock_data)
        res = await adapter.cancel_payment({"server_key": "sk"}, "inv_1001")
        assert res["success"] is True
        assert res["transaction_status"] == "cancel"


@pytest.mark.asyncio
async def test_11_refund_payment_success():
    adapter = MidtransAdapter()
    mock_data = {"order_id": "inv_1001", "transaction_id": "tx_12345", "transaction_status": "refund"}
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(status_code=200, json=lambda: mock_data)
        res = await adapter.refund_payment({"server_key": "sk"}, "inv_1001", Decimal("50000.00"))
        assert res["success"] is True
        assert res["refund_amount"] == "50000.00"


@pytest.mark.asyncio
async def test_12_decimal_gross_amount_exactness():
    adapter = MidtransAdapter()
    amt = Decimal("123456.78")
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=200,
            json=lambda: {"transaction_id": "tx_dec", "transaction_status": "pending"},
        )
        res = await adapter.create_payment({"server_key": "sk"}, {"order_id": "inv_dec", "gross_amount": amt})
        assert res["gross_amount"] == "123456.78"


@pytest.mark.asyncio
async def test_13_zero_or_negative_amount_rejected():
    adapter = MidtransAdapter()
    with pytest.raises(PermanentIntegrationError):
        await adapter.create_payment({"server_key": "sk"}, {"order_id": "inv_0", "gross_amount": Decimal("0.00")})

    with pytest.raises(PermanentIntegrationError):
        await adapter.create_payment({"server_key": "sk"}, {"order_id": "inv_neg", "gross_amount": Decimal("-10.00")})


@pytest.mark.asyncio
async def test_14_zero_or_negative_refund_rejected():
    adapter = MidtransAdapter()
    with pytest.raises(PermanentIntegrationError):
        await adapter.refund_payment({"server_key": "sk"}, "inv_1", Decimal("0.00"))


@pytest.mark.asyncio
async def test_15_valid_sha512_signature_verification():
    adapter = MidtransAdapter()
    server_key = "test_server_key_secret"
    order_id = "inv_sha512_1"
    status_code = "200"
    gross_amount = "100000.00"

    raw_str = f"{order_id}{status_code}{gross_amount}{server_key}"
    sig = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()

    payload = {
        "order_id": order_id,
        "status_code": status_code,
        "gross_amount": gross_amount,
        "signature_key": sig,
    }

    assert adapter.verify_notification(payload, server_key) is True


@pytest.mark.asyncio
async def test_16_invalid_sha512_signature_rejected():
    adapter = MidtransAdapter()
    payload = {
        "order_id": "inv_1",
        "status_code": "200",
        "gross_amount": "100.00",
        "signature_key": "invalid_signature_hash_here",
    }
    assert adapter.verify_notification(payload, "secret") is False


@pytest.mark.asyncio
async def test_17_missing_signature_key_returns_false():
    adapter = MidtransAdapter()
    payload = {"order_id": "inv_1", "status_code": "200"}
    assert adapter.verify_notification(payload, "secret") is False


@pytest.mark.asyncio
async def test_18_status_normalization_mappings():
    adapter = MidtransAdapter()
    assert adapter.normalize_notification({"transaction_status": "capture", "fraud_status": "accept"}) == "SUCCEEDED"
    assert adapter.normalize_notification({"transaction_status": "capture", "fraud_status": "challenge"}) == "PENDING"
    assert adapter.normalize_notification({"transaction_status": "settlement"}) == "SUCCEEDED"
    assert adapter.normalize_notification({"transaction_status": "pending"}) == "PENDING"
    assert adapter.normalize_notification({"transaction_status": "deny"}) == "FAILED"
    assert adapter.normalize_notification({"transaction_status": "cancel"}) == "CANCELLED"
    assert adapter.normalize_notification({"transaction_status": "expire"}) == "EXPIRED"
    assert adapter.normalize_notification({"transaction_status": "refund"}) == "REFUNDED"


@pytest.mark.asyncio
async def test_19_provider_wrapper_create_and_verify():
    provider = MidtransPaymentProvider(server_key="SB-Mid-key-123", is_sandbox=True)
    tenant_id = uuid.uuid4()
    invoice_id = uuid.uuid4()

    with patch.object(
        provider.adapter,
        "create_payment",
        new=AsyncMock(return_value={"success": True, "transaction_id": "tx_p1", "transaction_status": "pending"}),
    ):
        p_res = await provider.create_payment(tenant_id, invoice_id, Decimal("99000.00"))
        assert p_res.success is True
        assert p_res.provider_payment_id == "tx_p1"
        assert p_res.status == "PENDING"


@pytest.mark.asyncio
async def test_20_provider_wrapper_refund():
    provider = MidtransPaymentProvider(server_key="SB-Mid-key-123")
    with patch.object(
        provider.adapter,
        "refund_payment",
        new=AsyncMock(return_value={"success": True, "transaction_id": "ref_p1"}),
    ):
        r_res = await provider.refund("tx_p1", Decimal("50000.00"), "Damaged goods")
        assert r_res.success is True
        assert r_res.refund_id == "ref_p1"


@pytest.mark.asyncio
async def test_21_integration_service_get_connection_by_provider(db_session, tenant_a):
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "SB-Mid-test-key"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS, EXECUTE_INTEGRATION, VIEW_INTEGRATIONS},
    )
    assert conn.status == "ACTIVE"

    fetched = await service.get_connection_by_provider(
        tenant_a.id, "midtrans", actor_permissions={VIEW_INTEGRATIONS}
    )
    assert fetched is not None
    assert fetched.id == conn.id


@pytest.mark.asyncio
async def test_22_cross_tenant_connection_isolation(db_session, tenant_a, tenant_b):
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "SB-Mid-tenant-a"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    fetched_for_b = await service.get_connection_by_provider(
        tenant_b.id, "midtrans", actor_permissions={VIEW_INTEGRATIONS}
    )
    assert fetched_for_b is None


@pytest.mark.asyncio
async def test_23_connect_integration_entitlement_denied(db_session, tenant_a):
    service = IntegrationService(db_session)
    with patch.object(service.entitlement, "has_feature", new=AsyncMock(return_value=False)):
        with pytest.raises(EntitlementDeniedError):
            await service.connect_integration(
                tenant_id=tenant_a.id,
                integration_key="midtrans",
                credentials={"server_key": "sk"},
                actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
            )


@pytest.mark.asyncio
async def test_24_permission_denied_on_connect(db_session, tenant_a):
    service = IntegrationService(db_session)
    with pytest.raises(PermissionDeniedError):
        await service.connect_integration(
            tenant_id=tenant_a.id,
            integration_key="midtrans",
            credentials={"server_key": "sk"},
            actor_permissions={VIEW_INTEGRATIONS},
        )


@pytest.mark.asyncio
async def test_25_api_create_payment_route(async_client, tenant_a, db_session):
    inv_service = InvoiceService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "SB-Mid-key"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Pro Plan", "unit_price": Decimal("799000.00"), "quantity": 1}],
    )

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={MANAGE_PAYMENTS, MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )
    token = set_actor_context(actor)
    try:
        resp = await async_client.post(
            "/api/v1/integrations/midtrans/payments",
            json={"invoice_id": str(invoice.id)},
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
    finally:
        reset_actor_context(token)

    assert resp.status_code == 200
    data = resp.json()
    assert data["invoice_id"] == str(invoice.id)
    assert data["status"] == "PENDING"


@pytest.mark.asyncio
async def test_26_api_get_payment_status_route(async_client, tenant_a, db_session):
    pay_service = PaymentService(db_session)
    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item 1", "unit_price": Decimal("100000.00"), "quantity": 1}],
    )
    payment = await pay_service.create_payment_intent(tenant_id=tenant_a.id, invoice_id=invoice.id, amount=invoice.total)
    await db_session.commit()

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="member",
        permissions={VIEW_PAYMENT_STATUS, VIEW_INTEGRATIONS},
    )
    token = set_actor_context(actor)
    try:
        resp = await async_client.get(
            f"/api/v1/integrations/midtrans/payments/{payment.id}",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
    finally:
        reset_actor_context(token)

    assert resp.status_code == 200
    data = resp.json()
    assert data["payment_id"] == str(payment.id)
    assert data["status"] == "PENDING"


@pytest.mark.asyncio
async def test_27_api_refund_payment_creates_approval_request(async_client, tenant_a, db_session):
    pay_service = PaymentService(db_session)
    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item 1", "unit_price": Decimal("100000.00"), "quantity": 1}],
    )
    payment = await pay_service.create_payment_intent(tenant_id=tenant_a.id, invoice_id=invoice.id, amount=invoice.total)
    await pay_service.confirm_payment_success(tenant_a.id, payment.id, "tx_settled")

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="admin",
        permissions={REQUEST_REFUND, MANAGE_INTEGRATIONS},
    )
    token = set_actor_context(actor)
    try:
        resp = await async_client.post(
            f"/api/v1/integrations/midtrans/payments/{payment.id}/refund",
            json={"amount": "100000.00", "reason": "Customer request"},
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
    finally:
        reset_actor_context(token)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "APPROVAL_REQUIRED"
    assert "approval_id" in data


@pytest.mark.asyncio
async def test_28_webhook_trusted_tenant_mapping(async_client, tenant_a, db_session):
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "test_server_key"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS, EXECUTE_INTEGRATION},
    )

    inv_service = InvoiceService(db_session)
    invoice_a = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Starter Plan", "unit_price": Decimal("299000.00"), "quantity": 1}],
    )

    server_key = "test_server_key"
    order_id = str(invoice_a.id)
    status_code = "200"
    gross_amount = "299000.00"

    raw_str = f"{order_id}{status_code}{gross_amount}{server_key}"
    sig = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()

    payload = {
        "order_id": order_id,
        "status_code": status_code,
        "gross_amount": gross_amount,
        "signature_key": sig,
        "transaction_status": "settlement",
    }

    resp = await async_client.post("/api/v1/webhooks/midtrans", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "PROCESSED"

    await db_session.refresh(invoice_a)
    assert invoice_a.status == "PAID"


@pytest.mark.asyncio
async def test_29_webhook_invalid_signature_rejected(async_client, tenant_a, db_session):
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
        items_data=[{"description": "Item 1", "unit_price": Decimal("100000.00"), "quantity": 1}],
    )

    payload = {
        "order_id": str(invoice.id),
        "status_code": "200",
        "gross_amount": "100000.00",
        "signature_key": "invalid_sig_hash",
        "transaction_status": "settlement",
    }

    resp = await async_client.post("/api/v1/webhooks/midtrans", json=payload)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_30_cross_tenant_webhook_isolation(async_client, tenant_a, tenant_b, db_session):
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_a"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    inv_service = InvoiceService(db_session)
    invoice_a = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Tenant A Item", "unit_price": Decimal("50000.00"), "quantity": 1}],
    )

    raw_str = f"{invoice_a.id}20050000.00key_a"
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
    assert resp.status_code == 200

    await db_session.refresh(invoice_a)
    assert invoice_a.status == "PAID"


@pytest.mark.asyncio
async def test_31_webhook_idempotency(async_client, tenant_a, db_session):
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_idemp"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item 1", "unit_price": Decimal("10000.00"), "quantity": 1}],
    )

    raw_str = f"{invoice.id}20010000.00key_idemp"
    sig = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()

    payload = {
        "order_id": str(invoice.id),
        "transaction_id": "tx_idemp_100",
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
async def test_32_workflow_action_midtrans_check_status(db_session, tenant_a):
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_wf"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200,
            json=lambda: {"order_id": "inv_wf_1", "transaction_status": "settlement"},
        )
        res = await ActionExecutor.execute(
            action_type="midtrans_check_status",
            params={"order_id": "inv_wf_1"},
            context={},
            session=db_session,
            tenant_id=str(tenant_a.id),
        )
        assert res.success is True
        assert res.output["normalized_status"] == "SUCCEEDED"


@pytest.mark.asyncio
async def test_33_owner_ai_read_only_tool_get_payment_status(db_session, tenant_a):
    pay_service = PaymentService(db_session)
    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item 1", "unit_price": Decimal("50000.00"), "quantity": 1}],
    )
    payment = await pay_service.create_payment_intent(tenant_id=tenant_a.id, invoice_id=invoice.id, amount=invoice.total)

    tool_req = ToolRequest(
        tenant_id=str(tenant_a.id),
        tool_name="get_midtrans_payment_status",
        parameters={"payment_id": str(payment.id)},
    )
    tool_res = await tool_get_midtrans_payment_status(tool_req, db_session)
    assert tool_res.success is True
    assert tool_res.data["payment_id"] == str(payment.id)
    assert tool_res.data["status"] == "PENDING"


@pytest.mark.asyncio
async def test_34_tenant_isolation_api_access_denied(async_client, tenant_a, tenant_b, db_session):
    pay_service = PaymentService(db_session)
    inv_service = InvoiceService(db_session)
    invoice_b = await inv_service.create_invoice(
        tenant_id=tenant_b.id,
        items_data=[{"description": "Tenant B Item", "unit_price": Decimal("50000.00"), "quantity": 1}],
    )
    payment_b = await pay_service.create_payment_intent(tenant_id=tenant_b.id, invoice_id=invoice_b.id, amount=invoice_b.total)
    await db_session.commit()

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={VIEW_PAYMENT_STATUS, VIEW_INTEGRATIONS},
    )
    token = set_actor_context(actor)
    try:
        # Tenant A attempts to view Tenant B's payment using Tenant A's tenant header
        resp = await async_client.get(
            f"/api/v1/integrations/midtrans/payments/{payment_b.id}",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
    finally:
        reset_actor_context(token)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_35_tenant_isolation_refund_denied(async_client, tenant_a, tenant_b, db_session):
    pay_service = PaymentService(db_session)
    inv_service = InvoiceService(db_session)
    invoice_b = await inv_service.create_invoice(
        tenant_id=tenant_b.id,
        items_data=[{"description": "Tenant B Item", "unit_price": Decimal("50000.00"), "quantity": 1}],
    )
    payment_b = await pay_service.create_payment_intent(tenant_id=tenant_b.id, invoice_id=invoice_b.id, amount=invoice_b.total)
    await db_session.commit()

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={REQUEST_REFUND, MANAGE_INTEGRATIONS},
    )
    token = set_actor_context(actor)
    try:
        # Tenant A attempts to refund Tenant B's payment using Tenant A's tenant header
        resp = await async_client.post(
            f"/api/v1/integrations/midtrans/payments/{payment_b.id}/refund",
            json={"amount": "50000.00"},
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
    finally:
        reset_actor_context(token)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_36_execute_cancel_payment_via_adapter():
    adapter = MidtransAdapter()
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(status_code=200, json=lambda: {"transaction_status": "cancel", "order_id": "inv_c"})
        res = await adapter.execute(
            tenant_id=uuid.uuid4(),
            connection_id=uuid.uuid4(),
            credentials={"server_key": "sk"},
            operation="cancel_payment",
            params={"order_id": "inv_c"},
        )
        assert res["success"] is True
        assert res["transaction_status"] == "cancel"


@pytest.mark.asyncio
async def test_37_execute_refund_payment_via_adapter():
    adapter = MidtransAdapter()
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(status_code=200, json=lambda: {"transaction_status": "refund", "order_id": "inv_r"})
        res = await adapter.execute(
            tenant_id=uuid.uuid4(),
            connection_id=uuid.uuid4(),
            credentials={"server_key": "sk"},
            operation="refund_payment",
            params={"order_id": "inv_r", "amount": "50000.00", "reason": "Defective"},
        )
        assert res["success"] is True
        assert res["refund_amount"] == "50000.00"


@pytest.mark.asyncio
async def test_38_execute_unsupported_operation_raises_error():
    adapter = MidtransAdapter()
    with pytest.raises(PermanentIntegrationError):
        await adapter.execute(
            tenant_id=uuid.uuid4(),
            connection_id=uuid.uuid4(),
            credentials={"server_key": "sk"},
            operation="unsupported_op",
            params={},
        )


@pytest.mark.asyncio
async def test_39_provider_handle_webhook_invalid_sig():
    provider = MidtransPaymentProvider(server_key="secret_key")
    payload = {"order_id": "inv_1", "gross_amount": "100.00", "signature_key": "invalid_sig"}
    with pytest.raises(Exception):
        await provider.handle_webhook(payload, {})


@pytest.mark.asyncio
async def test_40_workflow_action_midtrans_create_payment(db_session, tenant_a):
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_wf_create"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "WF Item", "unit_price": Decimal("25000.00"), "quantity": 1}],
    )

    res = await ActionExecutor.execute(
        action_type="midtrans_create_payment",
        params={"invoice_id": str(invoice.id)},
        context={},
        session=db_session,
        tenant_id=str(tenant_a.id),
    )
    assert res.success is True
    assert "payment_id" in res.output


@pytest.mark.asyncio
async def test_41_workflow_action_midtrans_cancel_payment(db_session, tenant_a):
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_cancel"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    params = {"order_id": "inv_cancel_1"}
    action_hash = ActionBinding.compute_hash(
        action_type="midtrans_cancel_payment",
        target="midtrans_cancel_payment",
        tenant_id=tenant_a.id,
        params=params,
    )
    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="owner",
        action_type="midtrans_cancel_payment",
        target="midtrans_cancel_payment",
        reason="Test cancel",
        risk_level="HIGH",
        status="APPROVED",
        meta_data={"params": params, "action_hash": action_hash},
    )
    db_session.add(appr)
    await db_session.commit()

    exec_params = dict(params)
    exec_params["approval_id"] = str(appr.id)

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(status_code=200, json=lambda: {"transaction_status": "cancel"})
        res = await ActionExecutor.execute(
            action_type="midtrans_cancel_payment",
            params=exec_params,
            context={},
            session=db_session,
            tenant_id=str(tenant_a.id),
        )
        assert res.success is True


@pytest.mark.asyncio
async def test_42_workflow_action_midtrans_request_refund(db_session, tenant_a):
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_refund"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    params = {"order_id": "inv_ref_1", "amount": "50000.00"}
    action_hash = ActionBinding.compute_hash(
        action_type="midtrans_request_refund",
        target="midtrans_request_refund",
        tenant_id=tenant_a.id,
        params=params,
    )
    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="owner",
        action_type="midtrans_request_refund",
        target="midtrans_request_refund",
        reason="Test refund",
        risk_level="HIGH",
        status="APPROVED",
        meta_data={"params": params, "action_hash": action_hash},
    )
    db_session.add(appr)
    await db_session.commit()

    exec_params = dict(params)
    exec_params["approval_id"] = str(appr.id)

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(status_code=200, json=lambda: {"transaction_status": "refund"})
        res = await ActionExecutor.execute(
            action_type="midtrans_request_refund",
            params=exec_params,
            context={},
            session=db_session,
            tenant_id=str(tenant_a.id),
        )
        assert res.success is True


@pytest.mark.asyncio
async def test_43_webhook_failure_status_updates_invoice(async_client, tenant_a, db_session):
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_fail"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item 1", "unit_price": Decimal("100000.00"), "quantity": 1}],
    )

    raw_str = f"{invoice.id}407100000.00key_fail"
    sig = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()

    payload = {
        "order_id": str(invoice.id),
        "status_code": "407",
        "gross_amount": "100000.00",
        "signature_key": sig,
        "transaction_status": "deny",
    }

    resp = await async_client.post("/api/v1/webhooks/midtrans", json=payload)
    assert resp.status_code == 200
    assert resp.json()["normalized_status"] == "FAILED"


@pytest.mark.asyncio
async def test_44_webhook_expire_status_updates_payment(async_client, tenant_a, db_session):
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_expire"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item 1", "unit_price": Decimal("100000.00"), "quantity": 1}],
    )

    raw_str = f"{invoice.id}202100000.00key_expire"
    sig = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()

    payload = {
        "order_id": str(invoice.id),
        "status_code": "202",
        "gross_amount": "100000.00",
        "signature_key": sig,
        "transaction_status": "expire",
    }

    resp = await async_client.post("/api/v1/webhooks/midtrans", json=payload)
    assert resp.status_code == 200
    assert resp.json()["normalized_status"] == "EXPIRED"


@pytest.mark.asyncio
async def test_45_webhook_refund_status_updates_payment(async_client, tenant_a, db_session):
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_refund"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item 1", "unit_price": Decimal("100000.00"), "quantity": 1}],
    )

    raw_str = f"{invoice.id}200100000.00key_refund"
    sig = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()

    payload = {
        "order_id": str(invoice.id),
        "status_code": "200",
        "gross_amount": "100000.00",
        "signature_key": sig,
        "transaction_status": "refund",
    }

    resp = await async_client.post("/api/v1/webhooks/midtrans", json=payload)
    assert resp.status_code == 200
    assert resp.json()["normalized_status"] == "REFUNDED"


@pytest.mark.asyncio
async def test_46_api_cancel_payment_route(async_client, tenant_a, db_session):
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_api_cancel"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )
    await db_session.commit()

    pay_service = PaymentService(db_session)
    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item 1", "unit_price": Decimal("100000.00"), "quantity": 1}],
    )
    payment = await pay_service.create_payment_intent(tenant_id=tenant_a.id, invoice_id=invoice.id, amount=invoice.total)
    await db_session.commit()

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={MANAGE_PAYMENTS, MANAGE_INTEGRATIONS, EXECUTE_INTEGRATION},
    )
    token = set_actor_context(actor)
    try:
        with patch.object(
            MidtransAdapter,
            "cancel_payment",
            new=AsyncMock(return_value={"success": True, "order_id": str(invoice.id), "transaction_status": "cancel"}),
        ):
            resp = await async_client.post(
                f"/api/v1/integrations/midtrans/payments/{payment.id}/cancel",
                headers={"X-Tenant-ID": str(tenant_a.id)},
            )
    finally:
        reset_actor_context(token)

    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_49_midtrans_cancel_payment_permission_enforced(async_client, tenant_a, db_session):
    """Verifies that midtrans_cancel_payment enforces caller permissions and does not hardcode bypass."""
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "key_cancel_perm"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )
    await db_session.commit()

    pay_service = PaymentService(db_session)
    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item 1", "unit_price": Decimal("100000.00"), "quantity": 1}],
    )
    payment = await pay_service.create_payment_intent(tenant_id=tenant_a.id, invoice_id=invoice.id, amount=invoice.total)
    await db_session.commit()

    # Actor has MANAGE_PAYMENTS but lacks EXECUTE_INTEGRATION required by IntegrationService.execute_operation
    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="member",
        permissions={MANAGE_PAYMENTS},
    )
    token = set_actor_context(actor)
    try:
        resp = await async_client.post(
            f"/api/v1/integrations/midtrans/payments/{payment.id}/cancel",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
    finally:
        reset_actor_context(token)

    # Must be 403 because EXECUTE_INTEGRATION permission is missing in actor_permissions
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_50_onboarding_endpoints_reject_forged_headers(async_client, tenant_a):
    """Verifies onboarding endpoints reject forged X-Actor-Permissions headers when unauthenticated."""
    resp = await async_client.post(
        f"/api/v1/tenants/{tenant_a.id}/onboarding/whatsapp/connect",
        json={"phone_number_id": "123", "app_secret": "secret", "access_token": "token"},
        headers={"X-Tenant-ID": str(tenant_a.id), "X-Actor-Permissions": "MANAGE_INTEGRATIONS,MANAGE_CREDENTIALS"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_51_owner_ai_tool_execute_integration_operation_redacts_secrets(db_session, tenant_a):
    """Verifies that Owner AI tool_execute_integration_operation redacts sensitive credential fields in tool output."""
    service = IntegrationService(db_session)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="midtrans",
        credentials={"server_key": "SUPER_SECRET_SERVER_KEY_123"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )
    await db_session.commit()

    # Mock execute_operation returning raw secrets
    with patch.object(
        IntegrationService,
        "execute_operation",
        new=AsyncMock(return_value=AsyncMock(
            status="COMPLETED",
            result={"access_token": "secret_access_token_abc", "server_key": "SUPER_SECRET_SERVER_KEY_123", "status": "ok"},
            safe_error_message=None,
        )),
    ):
        tool_req = ToolRequest(
            tenant_id=str(tenant_a.id),
            tool_name="execute_integration_operation",
            parameters={"connection_id": str(conn.id), "operation": "refresh_token"},
        )
        res = await tool_execute_integration_operation(tool_req, db_session)
        assert res.success is True
        assert res.data["access_token"] in ("[REDACTED]", "[REDACTED_SECRET]")
        assert res.data["server_key"] in ("[REDACTED]", "[REDACTED_SECRET]")
        assert res.data["status"] == "ok"


@pytest.mark.asyncio
async def test_47_no_secret_leakage_in_adapter_error():
    adapter = MidtransAdapter()
    server_key_secret = "SUPER_SECRET_KEY_12345"
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=500,
            json=lambda: {"status_message": "Internal error"},
            content=b"{}",
        )
        with pytest.raises(Exception) as exc_info:
            await adapter.get_payment_status({"server_key": server_key_secret}, "order_123")
        assert server_key_secret not in str(exc_info.value)


@pytest.mark.asyncio
async def test_48_owner_ai_read_only_tool_list_recent_payments(db_session, tenant_a):
    pay_service = PaymentService(db_session)
    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Item 1", "unit_price": Decimal("50000.00"), "quantity": 1}],
    )
    await pay_service.create_payment_intent(tenant_id=tenant_a.id, invoice_id=invoice.id, amount=invoice.total)

    tool_req = ToolRequest(
        tenant_id=str(tenant_a.id),
        tool_name="get_midtrans_payment_status",
        parameters={},
    )
    tool_res = await tool_get_midtrans_payment_status(tool_req, db_session)
    assert tool_res.success is True
    assert tool_res.data["total_payments"] >= 1
