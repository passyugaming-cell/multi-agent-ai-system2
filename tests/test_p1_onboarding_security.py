import uuid
import pytest
from httpx import AsyncClient
from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context


@pytest.mark.asyncio
async def test_01_unauthenticated_request_rejected(async_client: AsyncClient, tenant_a):
    """Unauthenticated request (no JWT / no actor context) is rejected with HTTP 403 PERMISSION_DENIED."""
    res = await async_client.get(
        f"/api/v1/tenants/{tenant_a.id}/onboarding",
        headers={"X-Tenant-ID": str(tenant_a.id)},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_02_forged_x_tenant_id_header_rejected(async_client: AsyncClient, tenant_a, tenant_b):
    """Sending X-Tenant-ID for tenant_a without actor context -> HTTP 403 PERMISSION_DENIED."""
    res = await async_client.post(
        f"/api/v1/tenants/{tenant_a.id}/onboarding/start",
        headers={"X-Tenant-ID": str(tenant_a.id)},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_03_forged_x_actor_permissions_header_rejected(async_client: AsyncClient, tenant_a):
    """Client attempting to forge X-Actor-Permissions without server actor context -> HTTP 403 PERMISSION_DENIED."""
    res = await async_client.post(
        f"/api/v1/tenants/{tenant_a.id}/onboarding/start",
        headers={
            "X-Tenant-ID": str(tenant_a.id),
            "X-Actor-Permissions": "business.read,business.write",
        },
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_04_cross_tenant_access_rejected(async_client: AsyncClient, tenant_a, tenant_b):
    """Actor authenticated for Tenant A attempting to mutate Tenant B -> HTTP 403 FORBIDDEN_CROSS_TENANT_ACCESS."""
    actor_a = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.read", "business.write"},
    )
    token = set_actor_context(actor_a)
    try:
        res = await async_client.post(
            f"/api/v1/tenants/{tenant_b.id}/onboarding/start",
            headers={"X-Tenant-ID": str(tenant_b.id)},
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FORBIDDEN_CROSS_TENANT_ACCESS"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_05_legitimate_authenticated_actor_allowed(async_client: AsyncClient, tenant_a):
    """Authenticated actor for Tenant A with required permissions -> HTTP 200 OK."""
    actor_a = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.read", "business.write"},
    )
    token = set_actor_context(actor_a)
    try:
        res = await async_client.get(
            f"/api/v1/tenants/{tenant_a.id}/onboarding",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert res.status_code == 200
        assert "readiness_score" in res.json()
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_06_unauthorized_member_write_denied(async_client: AsyncClient, tenant_a):
    """Member actor with only read permissions trying to execute write operation -> HTTP 403 PERMISSION_DENIED."""
    actor_member = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="member",
        permissions={"business.read"},
    )
    token = set_actor_context(actor_member)
    try:
        res = await async_client.post(
            f"/api/v1/tenants/{tenant_a.id}/onboarding/start",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "PERMISSION_DENIED"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_07_existing_legitimate_onboarding_flow(async_client: AsyncClient, tenant_a):
    """Full onboarding flow execution with trusted actor context."""
    actor_a = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.read", "business.write"},
    )
    token = set_actor_context(actor_a)
    try:
        start_res = await async_client.post(
            f"/api/v1/tenants/{tenant_a.id}/onboarding/start",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert start_res.status_code == 200

        chk_res = await async_client.get(
            f"/api/v1/tenants/{tenant_a.id}/onboarding/checklist",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert chk_res.status_code == 200
        assert isinstance(chk_res.json(), list)
    finally:
        reset_actor_context(token)
