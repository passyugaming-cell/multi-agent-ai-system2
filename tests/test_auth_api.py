import uuid
from datetime import timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.user import User
from app.database.models.tenant import Tenant
from app.core.auth_service import hash_password, create_access_token, is_token_revoked_redis
from app.core.exceptions import AppException


@pytest.mark.asyncio
async def test_a_invalid_credentials(client: AsyncClient):
    """A. Attempting login with nonexistent email or bad password fails with 401."""
    resp = await client.post("/api/v1/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "wrongpassword"
    })
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_b_valid_single_tenant_login(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_a: Tenant,
):
    """B. Single-tenant user logs in successfully and receives token and 1 tenant."""
    email = f"single_{uuid.uuid4().hex[:6]}@example.com"
    password = "SecurePassword123!"
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        email=email,
        password_hash=hash_password(password),
        role="owner",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == email
    assert len(data["tenants"]) == 1
    assert data["tenants"][0]["id"] == str(tenant_a.id)
    assert data["active_tenant_id"] == str(tenant_a.id)


@pytest.mark.asyncio
async def test_c_valid_multi_tenant_login(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
):
    """C. Multi-tenant user receives all authorized active tenants."""
    email = f"multi_{uuid.uuid4().hex[:6]}@example.com"
    password = "MultiPassword123!"
    hashed = hash_password(password)

    u1 = User(id=uuid.uuid4(), tenant_id=tenant_a.id, email=email, password_hash=hashed, role="owner", is_active=True)
    u2 = User(id=uuid.uuid4(), tenant_id=tenant_b.id, email=email, password_hash=hashed, role="member", is_active=True)
    db_session.add_all([u1, u2])
    await db_session.commit()

    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tenants"]) == 2
    assert data["active_tenant_id"] is None  # User must pick a business


@pytest.mark.asyncio
async def test_d_e_f_get_me_token_validations(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_a: Tenant,
):
    """D, E, F. /me endpoint with valid token, expired token, and invalid token."""
    email = f"me_{uuid.uuid4().hex[:6]}@example.com"
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

    # D. Valid token
    login_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "Pass123!"})
    valid_token = login_resp.json()["access_token"]
    res_d = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {valid_token}"})
    assert res_d.status_code == 200
    assert res_d.json()["user"]["email"] == email

    # E. Expired token
    expired_token = create_access_token(
        {"sub": email, "user_id": str(user.id), "tenant_ids": [str(tenant_a.id)]},
        expires_delta=timedelta(seconds=-10),
    )
    res_e = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res_e.status_code == 401
    assert res_e.json()["error"]["code"] == "SESSION_EXPIRED"

    # F. Malformed token
    res_f = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer malformed.jwt.token"})
    assert res_f.status_code == 401


@pytest.mark.asyncio
async def test_g_h_i_select_tenant_authorization(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
):
    """G, H, I. Select authorized vs unauthorized tenant and cross-tenant prevention."""
    email = f"select_{uuid.uuid4().hex[:6]}@example.com"
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

    login_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "Pass123!"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # G. Authorized tenant selection
    res_g = await client.post("/api/v1/auth/select-tenant", json={"tenant_id": str(tenant_a.id)}, headers=headers)
    assert res_g.status_code == 200
    new_token = res_g.json()["access_token"]
    assert res_g.json()["active_tenant_id"] == str(tenant_a.id)

    # H & I. Unauthorized tenant selection attempt
    res_h = await client.post("/api/v1/auth/select-tenant", json={"tenant_id": str(tenant_b.id)}, headers={"Authorization": f"Bearer {new_token}"})
    assert res_h.status_code == 403
    assert res_h.json()["error"]["code"] == "FORBIDDEN_TENANT_ACCESS"


@pytest.mark.asyncio
async def test_j_logout_server_side_token_revocation(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_a: Tenant,
):
    """J. Logging out revokes the server-side JWT token so it cannot be reused."""
    email = f"logout_{uuid.uuid4().hex[:6]}@example.com"
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

    # Login
    login_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "Pass123!"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify token works before logout
    me_1 = await client.get("/api/v1/auth/me", headers=headers)
    assert me_1.status_code == 200

    # Logout
    logout_resp = await client.post("/api/v1/auth/logout", headers=headers)
    assert logout_resp.status_code == 200

    # Verify same token is now rejected after logout
    me_2 = await client.get("/api/v1/auth/me", headers=headers)
    assert me_2.status_code == 401
    assert me_2.json()["error"]["code"] == "SESSION_EXPIRED"


@pytest.mark.asyncio
async def test_roles_and_privilege_escalation_prevention(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_a: Tenant,
):
    """Member user cannot escalate privileges to owner write operations or via forged headers."""
    email_member = f"member_{uuid.uuid4().hex[:6]}@example.com"
    user_member = User(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        email=email_member,
        password_hash=hash_password("Pass123!"),
        role="member",
        is_active=True,
    )
    db_session.add(user_member)
    await db_session.commit()

    login_resp = await client.post("/api/v1/auth/login", json={"email": email_member, "password": "Pass123!"})
    token = login_resp.json()["access_token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": str(tenant_a.id),
    }

    # Member can read business profile
    read_res = await client.get("/api/v1/business", headers=headers)
    assert read_res.status_code in (200, 404)

    # Member CANNOT mutate business profile (requires business.write)
    write_res = await client.post("/api/v1/business", json={"business_name": "Member Forged Profile"}, headers=headers)
    assert write_res.status_code == 403
    assert write_res.json()["error"]["code"] == "PERMISSION_DENIED"

    # Member CANNOT escalate privileges by passing forged X-Actor-Role header
    forged_headers = {
        **headers,
        "X-Actor-Role": "owner",
        "X-Actor-Permissions": "business.read,business.write",
    }
    forged_res = await client.post("/api/v1/business", json={"business_name": "Forged Profile"}, headers=forged_headers)
    assert forged_res.status_code == 403
    assert forged_res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_redis_failure_fails_closed(monkeypatch: pytest.MonkeyPatch):
    """When Redis is unavailable or fails, token revocation verification fails closed with AppException."""
    class FailingRedisClient:
        async def get(self, key):
            raise ConnectionError("Redis cluster unreachable")
        async def aclose(self):
            pass

    def mock_from_url(*args, **kwargs):
        return FailingRedisClient()

    monkeypatch.setattr("redis.asyncio.from_url", mock_from_url)

    with pytest.raises(AppException) as exc_info:
        await is_token_revoked_redis("some-jti-uuid")

    assert exc_info.value.code == "REVOCATION_CHECK_FAILED"
    assert exc_info.value.status_code == 401
