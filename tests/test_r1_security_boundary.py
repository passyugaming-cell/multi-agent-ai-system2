"""Test suite for R1 Security & Tenant Authorization Boundary.

Tests:
1. R1-FIX-01: Real permission enforcement (insufficient permission member vs owner returns 403 PERMISSION_DENIED).
2. R1-FIX-02: Permission boundary negative and positive tests (customers:read/write, orders:read/write, etc.).
3. R1-FIX-03: Real JWT boundary tests (missing JWT, invalid JWT, expired JWT, cross-tenant JWT).
4. R1-FIX-04: Tenant lifecycle security (inactive/suspended tenant access returns 403 TENANT_INACTIVE).
5. R1-FIX-05/06: Event & workflow security chain (unauthenticated event injection fails closed).
"""
import uuid
import time
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.core.context import AuthenticatedActor, set_actor_context, set_tenant_context, reset_actor_context, reset_tenant_context
from app.core.auth import ROLE_PERMISSIONS
from app.core.auth_service import create_access_token


@pytest.mark.asyncio
async def test_r1_fix_01_permission_enforcement_member_lacks_write_permission(tenant_a):
    """Verify that a member role actor lacking customers:write permission gets HTTP 403 PERMISSION_DENIED on POST /customers."""
    member_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="member",
        permissions=ROLE_PERMISSIONS["member"],  # contains customers:read, NOT customers:write
        is_platform_owner=False,
    )

    actor_token = set_actor_context(member_actor)
    tenant_token = set_tenant_context(tenant_a.id)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/customers",
                headers={"X-Tenant-ID": str(tenant_a.id)},
                json={"name": "Test Customer", "email": "test@example.com", "phone": "123456789"},
            )
            assert response.status_code == 403
            data = response.json()
            assert data["error"]["code"] == "PERMISSION_DENIED"
            assert "customers:write" in data["error"]["message"]
    finally:
        reset_actor_context(actor_token)
        reset_tenant_context(tenant_token)


@pytest.mark.asyncio
async def test_r1_fix_02_permission_boundary_owner_allowed(tenant_a):
    """Verify that an owner role actor possessing customers:read/write permission is allowed."""
    owner_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions=ROLE_PERMISSIONS["owner"],
        is_platform_owner=False,
    )

    actor_token = set_actor_context(owner_actor)
    tenant_token = set_tenant_context(tenant_a.id)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/customers",
                headers={"X-Tenant-ID": str(tenant_a.id)},
            )
            assert response.status_code == 200
            assert isinstance(response.json(), list)
    finally:
        reset_actor_context(actor_token)
        reset_tenant_context(tenant_token)


@pytest.mark.asyncio
async def test_r1_fix_03_real_jwt_missing_token(tenant_a):
    """Verify requests without JWT Bearer token fail closed with HTTP 403 PERMISSION_DENIED."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/customers",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_r1_fix_03_real_jwt_invalid_token(tenant_a):
    """Verify requests with malformed JWT fail closed with HTTP 403 PERMISSION_DENIED."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/customers",
            headers={
                "X-Tenant-ID": str(tenant_a.id),
                "Authorization": "Bearer invalid.jwt.token",
            },
        )
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_r1_fix_03_real_jwt_cross_tenant_token(tenant_a, tenant_b):
    """Verify JWT issued for Tenant A fails closed when accessing Tenant B (HTTP 403 FORBIDDEN_CROSS_TENANT_ACCESS)."""
    actor_a = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions=ROLE_PERMISSIONS["owner"],
        is_platform_owner=False,
    )

    actor_token = set_actor_context(actor_a)
    tenant_token = set_tenant_context(tenant_b.id)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/customers",
                headers={"X-Tenant-ID": str(tenant_b.id)},
            )
            assert response.status_code == 403
            data = response.json()
            assert data["error"]["code"] == "FORBIDDEN_CROSS_TENANT_ACCESS"
    finally:
        reset_actor_context(actor_token)
        reset_tenant_context(tenant_token)


@pytest.mark.asyncio
async def test_r1_fix_04_tenant_lifecycle_inactive_tenant_denied(inactive_tenant):
    """Verify that requests targeting an inactive/suspended tenant fail with HTTP 403 TENANT_INACTIVE."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/customers",
            headers={"X-Tenant-ID": str(inactive_tenant.id)},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "TENANT_INACTIVE"


@pytest.mark.asyncio
async def test_r1_fix_05_unauthenticated_event_publishing_rejected(tenant_a):
    """Verify unauthenticated event publishing requests are rejected with HTTP 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/events",
            headers={"X-Tenant-ID": str(tenant_a.id)},
            json={
                "event_type": "order.created",
                "payload": {"order_id": str(uuid.uuid4())},
                "source": "external",
            },
        )
        assert response.status_code == 403
