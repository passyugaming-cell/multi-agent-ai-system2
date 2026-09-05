import asyncio
import uuid
import pytest
from httpx import AsyncClient

from app.core.context import get_tenant_context
from app.database.models.tenant import Tenant
from app.main import app


# Register a temporary test route on FastAPI app for verifying tenant context behavior
@app.get("/api/v1/test-tenant-context")
async def sample_protected_route():
    tenant_id = get_tenant_context()
    # Simulate async work
    await asyncio.sleep(0.01)
    # Re-verify context after async pause
    current_context = get_tenant_context()
    return {
        "tenant_id": str(tenant_id),
        "post_async_context": str(current_context),
    }


@pytest.mark.asyncio
async def test_missing_tenant_header_rejected(client: AsyncClient) -> None:
    """Request without X-Tenant-ID header should be rejected with HTTP 400."""
    response = await client.get("/api/v1/test-tenant-context")
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "MISSING_TENANT_HEADER"


@pytest.mark.asyncio
async def test_invalid_tenant_id_rejected(client: AsyncClient) -> None:
    """Request with malformed UUID in X-Tenant-ID header should be rejected with HTTP 400."""
    response = await client.get(
        "/api/v1/test-tenant-context",
        headers={"X-Tenant-ID": "invalid-uuid-format"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "INVALID_TENANT_ID"


@pytest.mark.asyncio
async def test_unknown_tenant_rejected(client: AsyncClient) -> None:
    """Request with non-existent tenant UUID should be rejected with HTTP 404."""
    random_uuid = str(uuid.uuid4())
    response = await client.get(
        "/api/v1/test-tenant-context",
        headers={"X-Tenant-ID": random_uuid},
    )
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "TENANT_NOT_FOUND"


@pytest.mark.asyncio
async def test_inactive_tenant_rejected(
    client: AsyncClient, inactive_tenant: Tenant
) -> None:
    """Request with inactive tenant UUID should be rejected with HTTP 403."""
    response = await client.get(
        "/api/v1/test-tenant-context",
        headers={"X-Tenant-ID": str(inactive_tenant.id)},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "TENANT_INACTIVE"


@pytest.mark.asyncio
async def test_valid_tenant_context_set(
    client: AsyncClient, tenant_a: Tenant
) -> None:
    """Request with valid active tenant UUID sets tenant_context during request."""
    response = await client.get(
        "/api/v1/test-tenant-context",
        headers={"X-Tenant-ID": str(tenant_a.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == str(tenant_a.id)
    assert data["post_async_context"] == str(tenant_a.id)


@pytest.mark.asyncio
async def test_tenant_context_reset_after_request(
    client: AsyncClient, tenant_a: Tenant
) -> None:
    """Verify tenant context is reset back to None after the request finishes."""
    assert get_tenant_context() is None

    response = await client.get(
        "/api/v1/test-tenant-context",
        headers={"X-Tenant-ID": str(tenant_a.id)},
    )
    assert response.status_code == 200

    assert get_tenant_context() is None


@pytest.mark.asyncio
async def test_tenant_isolation(
    client: AsyncClient, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    """Verify Tenant A request returns Tenant A context and Tenant B request returns Tenant B context."""
    res_a = await client.get(
        "/api/v1/test-tenant-context",
        headers={"X-Tenant-ID": str(tenant_a.id)},
    )
    assert res_a.status_code == 200
    assert res_a.json()["tenant_id"] == str(tenant_a.id)

    res_b = await client.get(
        "/api/v1/test-tenant-context",
        headers={"X-Tenant-ID": str(tenant_b.id)},
    )
    assert res_b.status_code == 200
    assert res_b.json()["tenant_id"] == str(tenant_b.id)


@pytest.mark.asyncio
async def test_concurrent_tenant_context_safety(
    client: AsyncClient, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    """Verify concurrent async requests maintain separate tenant contexts without context leakage."""
    async def request_tenant(tenant_id: uuid.UUID):
        return await client.get(
            "/api/v1/test-tenant-context",
            headers={"X-Tenant-ID": str(tenant_id)},
        )

    # Launch 10 concurrent requests alternating between Tenant A and Tenant B
    tasks = []
    for i in range(10):
        t = tenant_a if i % 2 == 0 else tenant_b
        tasks.append(request_tenant(t.id))

    results = await asyncio.gather(*tasks)

    for i, res in enumerate(results):
        expected_tenant_id = str(tenant_a.id) if i % 2 == 0 else str(tenant_b.id)
        assert res.status_code == 200
        assert res.json()["tenant_id"] == expected_tenant_id
        assert res.json()["post_async_context"] == expected_tenant_id

    # Verify context remains clean after concurrent operations
    assert get_tenant_context() is None
