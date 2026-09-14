"""Test suite for R1 Security & Tenant Authorization Boundary.

Tests:
1. Unauthenticated tenant API requests fail closed (HTTP 401/403).
2. Forged client permission headers (X-Actor-Permissions, X-Actor-Role) are rejected.
3. Cross-tenant authorization attempts (actor tenant_id != request tenant_id) fail closed (HTTP 403 FORBIDDEN_CROSS_TENANT_ACCESS).
4. Billing mutation endpoints require authenticated actor context.
5. Event publishing endpoints reject unauthenticated event injection.
6. Product and conversation tenant endpoints require authenticated actor context.
"""
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.core.context import AuthenticatedActor, set_actor_context, set_tenant_context, reset_actor_context, reset_tenant_context
from app.core.auth import ROLE_PERMISSIONS


@pytest.mark.asyncio
async def test_unauthenticated_tenant_api_access_rejected(tenant_a):
    """Verify unauthenticated tenant API requests without JWT fail closed."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Request /customers without Authorization header
        response = await client.get(
            "/api/v1/customers",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_unauthenticated_conversations_access_rejected(tenant_a):
    """Verify unauthenticated requests to /conversations fail closed."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/conversations",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_unauthenticated_products_access_rejected(tenant_a):
    """Verify unauthenticated requests to /products fail closed."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/products",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_forged_permission_headers_rejected(tenant_a):
    """Verify forged client permission/role headers are rejected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/orders",
            headers={
                "X-Tenant-ID": str(tenant_a.id),
                "X-Actor-Role": "owner",
                "X-Actor-Permissions": "orders:read,orders:write",
            },
        )
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_cross_tenant_access_rejected(tenant_a, tenant_b):
    """Verify actor from Tenant A cannot access Tenant B resources."""
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
async def test_unauthenticated_billing_mutation_rejected(tenant_a):
    """Verify billing mutation endpoints reject unauthenticated calls."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/billing/subscription",
            headers={"X-Tenant-ID": str(tenant_a.id)},
            json={"plan_code": "pro", "billing_cycle": "MONTHLY"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_event_injection_rejected(tenant_a):
    """Verify event publishing endpoint rejects unauthenticated event injection."""
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
