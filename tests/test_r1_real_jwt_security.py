import uuid
from datetime import timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.user import User
from app.database.models.tenant import Tenant
from app.core.auth_service import hash_password, create_access_token


@pytest.fixture(autouse=True)
def mock_redis_revocation_for_r1_jwt_tests(monkeypatch):
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


@pytest.mark.asyncio
async def test_r1_missing_jwt_rejected(client: AsyncClient, tenant_a: Tenant):
    """1. Requests missing JWT header are rejected with HTTP 403 PERMISSION_DENIED across protected endpoints."""
    headers = {"X-Tenant-ID": str(tenant_a.id)}

    # Protected endpoints across representative domains
    endpoints = [
        ("GET", "/api/v1/customers"),
        ("POST", "/api/v1/customers"),
        ("GET", "/api/v1/orders"),
        ("POST", "/api/v1/orders"),
        ("GET", "/api/v1/conversations"),
        ("GET", "/api/v1/workflows"),
        ("POST", "/api/v1/workflows"),
        ("GET", "/api/v1/tasks"),
        ("POST", "/api/v1/tasks"),
        ("GET", "/api/v1/analytics/financial"),
        ("GET", "/api/v1/analytics/sales"),
        ("GET", "/api/v1/billing/subscription"),
        ("POST", "/api/v1/billing/subscription"),
        ("GET", "/api/v1/billing/invoices"),
        ("GET", "/api/v1/billing/usage"),
        ("GET", "/api/v1/integrations/connections"),
        ("POST", "/api/v1/events"),
    ]

    for method, path in endpoints:
        if method == "GET":
            resp = await client.get(path, headers=headers)
        elif method == "POST":
            resp = await client.post(path, json={}, headers=headers)
        assert resp.status_code == 403, f"Endpoint {method} {path} allowed request without JWT! Status: {resp.status_code}"
        assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_r1_invalid_malformed_jwt_rejected(client: AsyncClient, tenant_a: Tenant):
    """2. Requests with malformed or invalid JWT strings are rejected with HTTP 403 PERMISSION_DENIED."""
    headers = {
        "X-Tenant-ID": str(tenant_a.id),
        "Authorization": "Bearer invalid.malformed.token.value",
    }

    resp_cust = await client.get("/api/v1/customers", headers=headers)
    assert resp_cust.status_code == 403
    assert resp_cust.json()["error"]["code"] == "PERMISSION_DENIED"

    resp_bill = await client.get("/api/v1/billing/subscription", headers=headers)
    assert resp_bill.status_code == 403
    assert resp_bill.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_r1_expired_jwt_rejected(client: AsyncClient, db_session: AsyncSession, tenant_a: Tenant):
    """3. Requests with expired JWT tokens are rejected with HTTP 403 PERMISSION_DENIED."""
    email = f"expired_user_{uuid.uuid4().hex[:6]}@example.com"
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        email=email,
        password_hash=hash_password("Pass123!"),
        role="owner",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    expired_token = create_access_token(
        data={"sub": email, "user_id": str(user.id), "tenant_ids": [str(tenant_a.id)], "active_tenant_id": str(tenant_a.id)},
        expires_delta=timedelta(seconds=-100),
    )

    headers = {
        "X-Tenant-ID": str(tenant_a.id),
        "Authorization": f"Bearer {expired_token}",
    }

    resp = await client.get("/api/v1/customers", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_r1_valid_jwt_correct_tenant_allowed(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_a: Tenant,
):
    """4. Valid JWT with matching tenant and active user allows access to protected tenant endpoints."""
    email = f"valid_owner_{uuid.uuid4().hex[:6]}@example.com"
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        email=email,
        password_hash=hash_password("Pass123!"),
        role="owner",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(
        data={"sub": email, "user_id": str(user.id), "tenant_ids": [str(tenant_a.id)], "active_tenant_id": str(tenant_a.id)}
    )

    headers = {
        "X-Tenant-ID": str(tenant_a.id),
        "Authorization": f"Bearer {token}",
    }

    # Customers list
    resp_cust = await client.get("/api/v1/customers", headers=headers)
    assert resp_cust.status_code == 200

    # Orders list
    resp_ord = await client.get("/api/v1/orders", headers=headers)
    assert resp_ord.status_code == 200

    # Workflows list
    resp_wf = await client.get("/api/v1/workflows", headers=headers)
    assert resp_wf.status_code == 200

    # Financial analytics
    resp_fin = await client.get("/api/v1/analytics/financial", headers=headers)
    assert resp_fin.status_code == 200


@pytest.mark.asyncio
async def test_r1_valid_jwt_wrong_tenant_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
):
    """5. Valid JWT for Tenant A attempting access to Tenant B is rejected with HTTP 403 PERMISSION_DENIED or FORBIDDEN_CROSS_TENANT_ACCESS."""
    email = f"tenant_a_user_{uuid.uuid4().hex[:6]}@example.com"
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        email=email,
        password_hash=hash_password("Pass123!"),
        role="owner",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    # Case A: Token claiming membership only in tenant_a, sent with X-Tenant-ID = tenant_b
    token_a = create_access_token(
        data={"sub": email, "user_id": str(user.id), "tenant_ids": [str(tenant_a.id)], "active_tenant_id": str(tenant_a.id)}
    )
    headers_b1 = {
        "X-Tenant-ID": str(tenant_b.id),
        "Authorization": f"Bearer {token_a}",
    }
    resp1 = await client.get("/api/v1/customers", headers=headers_b1)
    assert resp1.status_code == 403
    assert resp1.json()["error"]["code"] in ("PERMISSION_DENIED", "FORBIDDEN_CROSS_TENANT_ACCESS")

    # Case B: Multi-tenant JWT claiming both tenants, but active actor context created for tenant_a sent with X-Tenant-ID = tenant_b
    token_multi = create_access_token(
        data={"sub": email, "user_id": str(user.id), "tenant_ids": [str(tenant_a.id), str(tenant_b.id)], "active_tenant_id": str(tenant_a.id)}
    )
    headers_b2 = {
        "X-Tenant-ID": str(tenant_b.id),
        "Authorization": f"Bearer {token_multi}",
    }
    # Note: user exists in tenant_a, but user does NOT exist in tenant_b. TenantMiddleware will fail to load user in tenant_b -> active_actor is None -> PERMISSION_DENIED
    resp2 = await client.get("/api/v1/customers", headers=headers_b2)
    assert resp2.status_code == 403
    assert resp2.json()["error"]["code"] in ("PERMISSION_DENIED", "FORBIDDEN_CROSS_TENANT_ACCESS")


@pytest.mark.asyncio
async def test_r1_insufficient_permission_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_a: Tenant,
):
    """6. Valid JWT with 'member' role attempting operations requiring higher permissions is rejected with 403."""
    email = f"member_user_{uuid.uuid4().hex[:6]}@example.com"
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        email=email,
        password_hash=hash_password("Pass123!"),
        role="member",  # Member role lacks business.write, MANAGE_PAYMENTS, etc.
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(
        data={"sub": email, "user_id": str(user.id), "tenant_ids": [str(tenant_a.id)], "active_tenant_id": str(tenant_a.id)}
    )

    headers = {
        "X-Tenant-ID": str(tenant_a.id),
        "Authorization": f"Bearer {token}",
    }

    # Member can READ products
    prod_read = await client.get("/api/v1/products", headers=headers)
    assert prod_read.status_code == 200

    # Member CANNOT mutate business profile (requires business.write)
    biz_write = await client.post("/api/v1/business", json={"business_name": "Member Forged Profile"}, headers=headers)
    assert biz_write.status_code == 403
    assert biz_write.json()["error"]["code"] == "PERMISSION_DENIED"

    # Member CANNOT activate billing subscription (requires MANAGE_PAYMENTS)
    sub_post = await client.post("/api/v1/billing/subscription", json={"plan_code": "pro"}, headers=headers)
    assert sub_post.status_code == 403

    # Member CANNOT request refund (requires REQUEST_REFUND)
    refund_post = await client.post(f"/api/v1/billing/payments/{uuid.uuid4()}/refund", json={"amount": 100, "reason": "Test"}, headers=headers)
    assert refund_post.status_code == 403
