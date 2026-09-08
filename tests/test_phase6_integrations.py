import uuid
import hmac
import hashlib
import time
import pytest
import pytest_asyncio
import httpx
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

    integrations = await service.list_integrations(tenant_a.id, allow_internal=True)
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
        credentials={"access_token": "valid_token"},
        external_account_id="sheet_acc_1",
        allow_internal=True,
    )

    assert conn.status == "ACTIVE"
    assert conn.external_account_id == "sheet_acc_1"
    assert conn.last_connected_at is not None

    disconnected = await service.disconnect_integration(tenant_a.id, conn.id, allow_internal=True)
    assert disconnected.status == "DISCONNECTED"


def test_role_permissions_matrix():
    from app.core.auth import ROLE_PERMISSIONS
    from app.integrations.permissions import (
        VIEW_INTEGRATIONS,
        MANAGE_INTEGRATIONS,
        MANAGE_CREDENTIALS,
        EXECUTE_INTEGRATION,
    )

    owner_perms = ROLE_PERMISSIONS["owner"]
    admin_perms = ROLE_PERMISSIONS["admin"]
    member_perms = ROLE_PERMISSIONS["member"]

    # 1. owner has VIEW_INTEGRATIONS
    assert VIEW_INTEGRATIONS in owner_perms
    # 2. owner has MANAGE_INTEGRATIONS
    assert MANAGE_INTEGRATIONS in owner_perms
    # 3. owner has MANAGE_CREDENTIALS
    assert MANAGE_CREDENTIALS in owner_perms
    # 4. owner has EXECUTE_INTEGRATION
    assert EXECUTE_INTEGRATION in owner_perms

    # 5. admin has VIEW_INTEGRATIONS
    assert VIEW_INTEGRATIONS in admin_perms
    # 6. admin has MANAGE_INTEGRATIONS
    assert MANAGE_INTEGRATIONS in admin_perms
    # 7. admin has MANAGE_CREDENTIALS
    assert MANAGE_CREDENTIALS in admin_perms
    # 8. admin has EXECUTE_INTEGRATION
    assert EXECUTE_INTEGRATION in admin_perms

    # 9. member only has VIEW_INTEGRATIONS
    assert VIEW_INTEGRATIONS in member_perms
    # 10. member does NOT have MANAGE_INTEGRATIONS
    assert MANAGE_INTEGRATIONS not in member_perms
    # 11. member does NOT have MANAGE_CREDENTIALS
    assert MANAGE_CREDENTIALS not in member_perms
    # 12. member does NOT have EXECUTE_INTEGRATION
    assert EXECUTE_INTEGRATION not in member_perms


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

    # Lacks MANAGE_INTEGRATIONS (e.g. member with only VIEW_INTEGRATIONS)
    with pytest.raises(PermissionDeniedError):
        await service.connect_integration(
            tenant_id=tenant_a.id,
            integration_key="rest_api",
            credentials={"api_key": "test_key"},
            actor_permissions={"VIEW_INTEGRATIONS"},
        )

    # Valid permissions (e.g. owner/admin with MANAGE_INTEGRATIONS and MANAGE_CREDENTIALS)
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
async def test_api_forged_permission_headers_rejection(async_client: AsyncClient, tenant_a):
    from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context
    from app.core.auth import ROLE_PERMISSIONS

    # Member role has VIEW_INTEGRATIONS but NOT MANAGE_INTEGRATIONS or MANAGE_CREDENTIALS
    member_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="member",
        permissions=set(ROLE_PERMISSIONS.get("member", {VIEW_INTEGRATIONS})),
    )
    token = set_actor_context(member_actor)
    try:
        # Member attempts to call endpoint requiring MANAGE_INTEGRATIONS by forging client X-Actor-Permissions header
        headers = {
            "X-Tenant-ID": str(tenant_a.id),
            "X-Actor-Permissions": "MANAGE_INTEGRATIONS,MANAGE_CREDENTIALS,VIEW_INTEGRATIONS,EXECUTE_INTEGRATION",
        }
        resp = await async_client.post(
            "/api/v1/integrations/connect/rest_api",
            json={"credentials": {"api_key": "test"}},
            headers=headers,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "PERMISSION_DENIED"
    finally:
        reset_actor_context(token)


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
        allow_internal=True,
    )

    with pytest.raises(ConnectionNotFoundError):
        await service.execute_operation(
            tenant_id=tenant_b.id,
            connection_id=conn_a.id,
            operation="ping",
            params={},
            allow_internal=True,
        )


@pytest.mark.asyncio
async def test_google_sheets_adapter_order_export(monkeypatch, db_session: AsyncSession, tenant_a):
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

    async def mock_send(self, request: httpx.Request, *args, **kwargs):
        return httpx.Response(200, json={"updates": {"updatedRows": 2}}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "fake_access_token"},
        allow_internal=True,
    )

    res = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="export_orders",
        params={"spreadsheet_id": "sheet_xyz_123"},
        allow_internal=True,
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
        allow_internal=True,
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
        allow_internal=True,
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
        allow_internal=True,
    )

    idem_key = f"idem_{uuid.uuid4().hex}"
    res1 = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="ping",
        params={},
        idempotency_key=idem_key,
        allow_internal=True,
    )
    assert res1.status == "COMPLETED"

    # Second call with same idempotency key returns cached execution result
    res2 = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="ping",
        params={},
        idempotency_key=idem_key,
        allow_internal=True,
    )
    assert res2.execution_id == res1.execution_id
    assert res2.status == "COMPLETED"
