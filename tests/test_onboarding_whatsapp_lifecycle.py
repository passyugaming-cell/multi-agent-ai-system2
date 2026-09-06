import pytest
import uuid
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models.tenant import Tenant
from app.database.models.business_profile import BusinessProfile
from app.database.models.product import Product
from app.database.models.audit import ProvisioningAudit
from app.database.models.integrations import IntegrationConnection
from app.tenants.onboarding_service import OnboardingService
from app.tenants.provisioning.provisioner import TenantProvisioner
from app.billing.subscription import SubscriptionService
from app.billing.plans import PlanService
from app.agents.owner_ai.tools import tool_get_onboarding_status, tool_get_whatsapp_connection_status
from app.agents.base.schemas import ToolRequest
from app.core.ai_gateway.schemas import AIResponse

AUTH_HEADERS = lambda tenant_id: {
    "X-Tenant-ID": str(tenant_id),
    "X-Actor-Permissions": "MANAGE_INTEGRATIONS,MANAGE_CREDENTIALS,VIEW_INTEGRATIONS",
}


@pytest.fixture
async def active_tenant(db_session: AsyncSession, tenant_a: Tenant) -> Tenant:
    """Fixture ensuring tenant_a has an active subscription."""
    plan_svc = PlanService(db_session)
    await plan_svc.seed_plans()
    sub_svc = SubscriptionService(db_session)
    await sub_svc.create_trial_subscription(tenant_a.id)
    await db_session.commit()
    return tenant_a


@pytest.mark.asyncio
async def test_01_onboarding_start_and_checklist(db_session: AsyncSession, active_tenant: Tenant) -> None:
    svc = OnboardingService(db_session)
    summary = await svc.start_onboarding(active_tenant.id)
    assert summary.tenant_id == active_tenant.id
    assert summary.lifecycle_state in ("ONBOARDING", "CONFIGURING", "PROSPECT")
    assert summary.checklist_summary.total == 17
    assert summary.readiness_status in ("NOT_READY", "NEARLY_READY")


@pytest.mark.asyncio
async def test_02_tenant_isolation_cross_tenant_protection(
    client: AsyncClient, active_tenant: Tenant, tenant_b: Tenant
) -> None:
    res = await client.get(
        f"/api/v1/tenants/{tenant_b.id}/onboarding",
        headers=AUTH_HEADERS(active_tenant.id),
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN_CROSS_TENANT_ACCESS"


@pytest.mark.asyncio
async def test_03_subscription_gate_validation(db_session: AsyncSession, tenant_b: Tenant) -> None:
    svc = OnboardingService(db_session)
    conn_req = {
        "phone_number_id": "100200300",
        "access_token": "mock_token_123",
    }
    from app.tenants.provisioning.schemas import WhatsAppConnectRequest
    req = WhatsAppConnectRequest(**conn_req)

    with pytest.raises(Exception) as exc_info:
        await svc.connect_whatsapp(tenant_b.id, req)
    assert "subscription" in str(exc_info.value).lower() or "SUBSCRIPTION_INVALID" in str(exc_info.value)


@pytest.mark.asyncio
async def test_04_whatsapp_connect_and_verification(
    client: AsyncClient, db_session: AsyncSession, active_tenant: Tenant
) -> None:
    headers = AUTH_HEADERS(active_tenant.id)

    conn_payload = {
        "phone_number_id": "123456789",
        "access_token": "mock_valid_token_abc",
        "waba_id": "waba_999",
        "app_secret": "app_secret_abc",
        "webhook_secret": "wh_secret_abc",
    }

    res = await client.post(
        f"/api/v1/tenants/{active_tenant.id}/onboarding/whatsapp/connect",
        headers=headers,
        json=conn_payload,
    )
    assert res.status_code == 200, res.json()
    data = res.json()
    assert data["status"] in ("ACTIVE", "CONNECTED")
    assert data["phone_number_id"] == "123456789"
    assert data["is_verified"] is True
    conn_id = data["connection_id"]

    v_res = await client.post(
        f"/api/v1/tenants/{active_tenant.id}/onboarding/whatsapp/verify?connection_id={conn_id}",
        headers=headers,
    )
    assert v_res.status_code == 200
    v_data = v_res.json()
    assert v_data["is_verified"] is True


@pytest.mark.asyncio
async def test_05_whatsapp_reconnect_and_disconnect(
    client: AsyncClient, db_session: AsyncSession, active_tenant: Tenant
) -> None:
    headers = AUTH_HEADERS(active_tenant.id)

    conn_payload = {
        "phone_number_id": "123456789",
        "access_token": "mock_valid_token_abc",
    }
    c_res = await client.post(
        f"/api/v1/tenants/{active_tenant.id}/onboarding/whatsapp/connect",
        headers=headers,
        json=conn_payload,
    )
    assert c_res.status_code == 200, c_res.json()
    conn_id = c_res.json()["connection_id"]

    recon_payload = {
        "phone_number_id": "123456789",
        "access_token": "mock_updated_token_xyz",
    }
    r_res = await client.post(
        f"/api/v1/tenants/{active_tenant.id}/onboarding/whatsapp/reconnect?connection_id={conn_id}",
        headers=headers,
        json=recon_payload,
    )
    assert r_res.status_code == 200
    assert r_res.json()["is_verified"] is True

    d_res = await client.post(
        f"/api/v1/tenants/{active_tenant.id}/onboarding/whatsapp/disconnect?connection_id={conn_id}",
        headers=headers,
    )
    assert d_res.status_code == 200
    assert d_res.json()["status"] == "DISCONNECTED"


@pytest.mark.asyncio
async def test_06_ai_test_gate(
    client: AsyncClient, active_tenant: Tenant
) -> None:
    headers = AUTH_HEADERS(active_tenant.id)
    mock_resp = AIResponse(
        text="AI Store Assistant is ready and operational.",
        model="gemini-3.1-flash-lite",
        input_tokens=10,
        output_tokens=15,
        total_tokens=25,
        estimated_cost=0.0001,
        request_id="req_test_123",
        usage_status="EXACT",
    )
    with patch("app.core.ai_gateway.gateway.AIGateway.generate", new_callable=AsyncMock, return_value=mock_resp):
        res = await client.post(
            f"/api/v1/tenants/{active_tenant.id}/onboarding/ai-test",
            headers=headers,
            json={"test_message": "Hello AI assistant test"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["ai_gateway_status"] == "REACHABLE"


@pytest.mark.asyncio
async def test_07_activation_blocked_when_requirements_missing(
    client: AsyncClient, active_tenant: Tenant
) -> None:
    headers = AUTH_HEADERS(active_tenant.id)
    res = await client.post(
        f"/api/v1/tenants/{active_tenant.id}/onboarding/activate",
        headers=headers,
    )
    assert res.status_code in (400, 422)
    err = res.json()
    assert "ACTIVATION_BLOCKED" in str(err) or "TENANT_NOT_READY" in str(err) or "Readiness score" in str(err)


@pytest.mark.asyncio
async def test_08_activation_success_and_idempotency(
    client: AsyncClient, db_session: AsyncSession, active_tenant: Tenant
) -> None:
    headers = AUTH_HEADERS(active_tenant.id)

    provisioner = TenantProvisioner(db_session)
    await provisioner.provision_tenant(active_tenant.id)

    bp = BusinessProfile(
        tenant_id=active_tenant.id,
        business_name="Beta Shop",
        business_type="E-commerce",
        description="Beta Shop store description",
        operating_hours={"mon": "09:00-18:00"},
        payment_methods={"bank_transfer": True},
        shipping_information={"regular": True},
        return_policy="Return within 14 days",
        exchange_policy="Exchange within 7 days",
        refund_policy="Refund within 30 days",
    )
    db_session.add(bp)

    p1 = Product(
        tenant_id=active_tenant.id,
        name="Product B",
        price=150.00,
        stock=20,
        is_active=True,
    )
    db_session.add(p1)
    await db_session.commit()

    conn_payload = {
        "phone_number_id": "987654321",
        "access_token": "mock_token_beta",
    }
    await client.post(
        f"/api/v1/tenants/{active_tenant.id}/onboarding/whatsapp/connect",
        headers=headers,
        json=conn_payload,
    )

    await client.post(
        f"/api/v1/tenants/{active_tenant.id}/onboarding/validate",
        headers=headers,
    )

    act_res = await client.post(
        f"/api/v1/tenants/{active_tenant.id}/onboarding/activate",
        headers=headers,
    )
    assert act_res.status_code == 200
    act_data = act_res.json()
    assert act_data["current_state"] == "ACTIVE"

    # Idempotent second call
    act_res2 = await client.post(
        f"/api/v1/tenants/{active_tenant.id}/onboarding/activate",
        headers=headers,
    )
    assert act_res2.status_code == 200
    assert act_res2.json()["current_state"] == "ACTIVE"


@pytest.mark.asyncio
async def test_09_owner_ai_read_only_tools(
    db_session: AsyncSession, active_tenant: Tenant
) -> None:
    tool_req = ToolRequest(
        tenant_id=str(active_tenant.id),
        source="owner_ai",
        tool_name="get_onboarding_status",
    )
    res = await tool_get_onboarding_status(tool_req, db_session)
    assert res.success is True
    assert "readiness_score" in res.data

    tool_req2 = ToolRequest(
        tenant_id=str(active_tenant.id),
        source="owner_ai",
        tool_name="get_whatsapp_connection_status",
    )
    res2 = await tool_get_whatsapp_connection_status(tool_req2, db_session)
    assert res2.success is True
    assert "is_connected" in res2.data


@pytest.mark.asyncio
async def test_10_credential_security_no_secret_leakage(
    client: AsyncClient, active_tenant: Tenant
) -> None:
    headers = AUTH_HEADERS(active_tenant.id)
    conn_payload = {
        "phone_number_id": "123456789",
        "access_token": "super_secret_access_token_123",
        "app_secret": "super_secret_app_secret_456",
        "webhook_secret": "super_secret_wh_secret_789",
    }
    c_res = await client.post(
        f"/api/v1/tenants/{active_tenant.id}/onboarding/whatsapp/connect",
        headers=headers,
        json=conn_payload,
    )
    body_str = c_res.text
    assert "super_secret_access_token_123" not in body_str
    assert "super_secret_app_secret_456" not in body_str
    assert "super_secret_wh_secret_789" not in body_str


@pytest.mark.asyncio
async def test_11_permission_fail_closed(
    client: AsyncClient, active_tenant: Tenant
) -> None:
    headers_no_perms = {"X-Tenant-ID": str(active_tenant.id)}
    conn_payload = {
        "phone_number_id": "123456789",
        "access_token": "mock_valid_token_abc",
    }
    res = await client.post(
        f"/api/v1/tenants/{active_tenant.id}/onboarding/whatsapp/connect",
        headers=headers_no_perms,
        json=conn_payload,
    )
    assert res.status_code in (401, 403)
    assert "PERMISSION_DENIED" in str(res.json()) or "Permission" in str(res.json())
