import uuid
import hmac
import hashlib
import time
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.integrations import Integration, IntegrationConnection, IntegrationCredential, WebhookConfig
from app.integrations.service import IntegrationService
from app.integrations.exceptions import (
    EntitlementDeniedError,
    ConnectionNotFoundError,
    PermissionDeniedError,
    WebhookVerificationError,
    TransientIntegrationError,
    PermanentIntegrationError,
)
from app.integrations.credentials import CredentialVault, redact_secrets
from app.integrations.permissions import (
    VIEW_INTEGRATIONS,
    MANAGE_INTEGRATIONS,
    MANAGE_CREDENTIALS,
    EXECUTE_INTEGRATION,
)
from app.billing.plans import PlanService
from app.billing.subscription import SubscriptionService
from app.database.models.order import Order
from app.database.models.customer import Customer


@pytest.mark.asyncio
async def test_integration_seeding_and_list(db_session: AsyncSession, tenant_a):
    service = IntegrationService(db_session)
    int_a = Integration(
        tenant_id=tenant_a.id,
        integration_key="rest_api",
        provider_key="rest_api",
        display_name="REST API Connector",
        category="api",
        is_enabled=True,
    )
    db_session.add(int_a)
    await db_session.commit()

    integrations = await service.list_integrations(tenant_a.id)
    assert len(integrations) >= 1
    assert any(i.integration_key == "rest_api" for i in integrations)


@pytest.mark.asyncio
async def test_connection_lifecycle_and_entitlement_gating(db_session: AsyncSession, tenant_a):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    integration = Integration(
        integration_key="google_sheets",
        provider_key="google_sheets",
        display_name="Google Sheets Sync",
        category="analytics",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"service_account_json": "{\"type\": \"service_account\"}"},
        external_account_id="sheet_acc_1",
    )

    assert conn.status == "ACTIVE"
    assert conn.external_account_id == "sheet_acc_1"
    assert conn.last_connected_at is not None

    disconnected = await service.disconnect_integration(tenant_a.id, conn.id)
    assert disconnected.status == "DISCONNECTED"


@pytest.mark.asyncio
async def test_permission_enforcement(db_session: AsyncSession, tenant_a):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    integration = Integration(
        integration_key="rest_api",
        provider_key="rest_api",
        display_name="REST Connector",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)

    # Lacks MANAGE_INTEGRATIONS
    with pytest.raises(PermissionDeniedError):
        await service.connect_integration(
            tenant_id=tenant_a.id,
            integration_key="rest_api",
            credentials={"api_key": "test_key"},
            actor_permissions={"VIEW_INTEGRATIONS"},
        )

    # Valid permissions
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="rest_api",
        credentials={"api_key": "test_key"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )
    assert conn.status == "ACTIVE"

    # Lacks EXECUTE_INTEGRATION
    with pytest.raises(PermissionDeniedError):
        await service.execute_operation(
            tenant_id=tenant_a.id,
            connection_id=conn.id,
            operation="ping",
            params={},
            actor_permissions={VIEW_INTEGRATIONS},
        )


@pytest.mark.asyncio
async def test_credential_encryption_and_zero_leakage_in_redaction():
    vault = CredentialVault()
    secret_data = {
        "api_key": "super_secret_key_12345",
        "access_token": "bearer_secret_token_9999",
        "description": "normal_field",
    }

    encrypted = vault.encrypt_credentials(secret_data)
    assert encrypted != str(secret_data)
    assert "super_secret_key_12345" not in encrypted

    decrypted = vault.decrypt_credentials(encrypted)
    assert decrypted["api_key"] == "super_secret_key_12345"

    redacted = redact_secrets(secret_data)
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["access_token"] == "[REDACTED]"
    assert redacted["description"] == "normal_field"


@pytest.mark.asyncio
async def test_strict_tenant_isolation(db_session: AsyncSession, tenant_a, tenant_b):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)
    await sub_srv.create_trial_subscription(tenant_b.id)

    integration = Integration(
        integration_key="rest_api",
        provider_key="rest_api",
        display_name="REST Connector",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)

    conn_a = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="rest_api",
        credentials={"api_key": "tenant_a_secret_key"},
    )

    with pytest.raises(ConnectionNotFoundError):
        await service.execute_operation(
            tenant_id=tenant_b.id,
            connection_id=conn_a.id,
            operation="ping",
            params={},
        )


@pytest.mark.asyncio
async def test_google_sheets_adapter_order_export(db_session: AsyncSession, tenant_a):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    customer = Customer(tenant_id=tenant_a.id, name="Test Customer", phone="628123456789")
    db_session.add(customer)
    await db_session.flush()

    order1 = Order(
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        status="PAID",
        total=150000.0,
        currency="IDR",
    )
    db_session.add(order1)
    await db_session.commit()

    integration = Integration(
        integration_key="google_sheets",
        provider_key="google_sheets",
        display_name="Google Sheets",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"api_key": "fake_google_api_key"},
    )

    res = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="export_orders",
        params={"spreadsheet_id": "sheet_xyz_123"},
    )

    assert res.status == "COMPLETED"
    assert res.result["exported_orders_count"] == 1
    assert res.result["spreadsheet_id"] == "sheet_xyz_123"


@pytest.mark.asyncio
async def test_webhook_security_negative_tests(async_client: AsyncClient, db_session: AsyncSession, tenant_a, tenant_b):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    from app.integrations import integration_registry
    from app.integrations.adapters import WebhookAdapter
    integration_registry.register("stripe", WebhookAdapter())

    integration = Integration(
        integration_key="stripe",
        provider_key="stripe",
        display_name="Stripe Connector",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="stripe",
        credentials={"webhook_secret": "tenant_a_stripe_secret"},
    )

    headers = {"X-Tenant-ID": str(tenant_a.id)}
    raw_body = "{\"event\": \"payment_intent.succeeded\"}"

    # 1. Missing signature
    resp = await async_client.post(
        "/api/v1/webhooks/inbound/stripe",
        content=raw_body,
        headers={**headers, "Content-Type": "application/json"},
    )
    assert resp.status_code == 401

    # 2. Invalid signature
    resp_bad_sig = await async_client.post(
        "/api/v1/webhooks/inbound/stripe",
        content=raw_body,
        headers={**headers, "X-Signature": "invalid_sig", "Content-Type": "application/json"},
    )
    assert resp_bad_sig.status_code == 401

    # 3. Valid signature with Tenant A secret
    sig_a = hmac.new("tenant_a_stripe_secret".encode("utf-8"), raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
    resp_valid = await async_client.post(
        "/api/v1/webhooks/inbound/stripe",
        content=raw_body,
        headers={**headers, "X-Signature": sig_a, "Content-Type": "application/json"},
    )
    assert resp_valid.status_code == 200

    # 4. Cross-tenant attempt: Tenant B headers using Tenant A's signature
    headers_b = {"X-Tenant-ID": str(tenant_b.id)}
    resp_cross = await async_client.post(
        "/api/v1/webhooks/inbound/stripe",
        content=raw_body,
        headers={**headers_b, "X-Signature": sig_a, "Content-Type": "application/json"},
    )
    assert resp_cross.status_code == 401


@pytest.mark.asyncio
async def test_webhook_replay_protection(async_client: AsyncClient, db_session: AsyncSession, tenant_a):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    integration = Integration(
        integration_key="stripe",
        provider_key="stripe",
        display_name="Stripe Connector",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="stripe",
        credentials={"webhook_secret": "tenant_a_secret"},
    )

    headers = {"X-Tenant-ID": str(tenant_a.id)}
    raw_body = "{\"event\": \"charge.succeeded\"}"
    sig = hmac.new("tenant_a_secret".encode("utf-8"), raw_body.encode("utf-8"), hashlib.sha256).hexdigest()

    # Expired timestamp (1 hour ago)
    old_ts = str(time.time() - 3600)
    resp_old = await async_client.post(
        "/api/v1/webhooks/inbound/stripe",
        content=raw_body,
        headers={**headers, "X-Signature": sig, "X-Timestamp": old_ts, "Content-Type": "application/json"},
    )
    assert resp_old.status_code == 401


@pytest.mark.asyncio
async def test_operation_idempotency_and_retries(db_session: AsyncSession, tenant_a):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    integration = Integration(
        integration_key="rest_api",
        provider_key="rest_api",
        display_name="REST Connector",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="rest_api",
        credentials={"api_key": "key_1"},
    )

    idem_key = f"idem_{uuid.uuid4().hex}"
    res1 = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="ping",
        params={},
        idempotency_key=idem_key,
    )
    assert res1.status == "COMPLETED"

    # Second call with same idempotency key returns cached execution result
    res2 = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="ping",
        params={},
        idempotency_key=idem_key,
    )
    assert res2.execution_id == res1.execution_id
    assert res2.status == "COMPLETED"
