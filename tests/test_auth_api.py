import uuid
from datetime import timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.user import User
from app.database.models.tenant import Tenant
from app.core.auth_service import hash_password, create_access_token, is_token_revoked_redis
from app.core.exceptions import AppException


@pytest.fixture(autouse=True)
def mock_redis_revocation_for_auth_tests(monkeypatch):
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
async def test_get_me_hardened_db_membership_and_stale_jwt_clearing(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
    inactive_tenant: Tenant,
):
    """/me rebuilds active tenant list from DB truth, clears stale active_tenant_id, and strictly follows user_id."""
    email = f"hardened_me_{uuid.uuid4().hex[:6]}@example.com"
    hashed = hash_password("Pass123!")

    # u1 in tenant_a (active), u2 in tenant_b (deactivated), u3 in inactive_tenant (active user, inactive tenant)
    u1 = User(id=uuid.uuid4(), tenant_id=tenant_a.id, email=email, password_hash=hashed, role="owner", is_active=True)
    u2 = User(id=uuid.uuid4(), tenant_id=tenant_b.id, email=email, password_hash=hashed, role="member", is_active=False)
    u3 = User(id=uuid.uuid4(), tenant_id=inactive_tenant.id, email=email, password_hash=hashed, role="admin", is_active=True)
    db_session.add_all([u1, u2, u3])
    await db_session.commit()

    # Create token claiming membership in all 3 tenants and active_tenant_id = tenant_b (inactive membership)
    stale_token = create_access_token({
        "sub": email,
        "user_id": str(u1.id),
        "tenant_ids": [str(tenant_a.id), str(tenant_b.id), str(inactive_tenant.id)],
        "active_tenant_id": str(tenant_b.id),
    })

    me_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {stale_token}"})
    assert me_res.status_code == 200
    data = me_res.json()

    # Primary user identity comes strictly from u1.id
    assert data["user"]["id"] == str(u1.id)
    assert data["user"]["email"] == email

    # Tenant list contains ONLY tenant_a (tenant_b membership inactive, inactive_tenant is inactive)
    tenant_ids = [t["id"] for t in data["tenants"]]
    assert tenant_ids == [str(tenant_a.id)]

    # Stale active_tenant_id (tenant_b) was cleared and updated to tenant_a (single remaining valid tenant)
    assert data["active_tenant_id"] == str(tenant_a.id)


@pytest.mark.asyncio
async def test_get_me_user_id_mismatch_and_deactivated_primary_user(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_a: Tenant,
):
    """/me rejects tokens where primary user_id is deactivated or email mismatches."""
    email = f"mismatch_{uuid.uuid4().hex[:6]}@example.com"
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        email=email,
        password_hash=hash_password("Pass123!"),
        role="owner",
        is_active=False,  # Deactivated
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token({
        "sub": email,
        "user_id": str(user.id),
        "tenant_ids": [str(tenant_a.id)],
    })

    # Deactivated primary user -> 401 UNAUTHORIZED
    res1 = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res1.status_code == 401

    # User email mismatch in sub claim -> 401 UNAUTHORIZED
    user.is_active = True
    await db_session.commit()
    mismatch_token = create_access_token({
        "sub": "forged_email@example.com",
        "user_id": str(user.id),
        "tenant_ids": [str(tenant_a.id)],
    })

    res2 = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {mismatch_token}"})
    assert res2.status_code == 401


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
async def test_select_tenant_db_membership_revocation(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
):
    """Tenant present in old JWT claim but deactivated or deleted in DB cannot be selected."""
    email = f"revoked_member_{uuid.uuid4().hex[:6]}@example.com"
    hashed = hash_password("Pass123!")

    u1 = User(id=uuid.uuid4(), tenant_id=tenant_a.id, email=email, password_hash=hashed, role="owner", is_active=True)
    u2 = User(id=uuid.uuid4(), tenant_id=tenant_b.id, email=email, password_hash=hashed, role="member", is_active=True)
    db_session.add_all([u1, u2])
    await db_session.commit()

    # User logs in and gets JWT containing both tenant_a and tenant_b in tenant_ids claim
    login_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "Pass123!"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Admin deactivates user u2 in tenant_b
    u2.is_active = False
    await db_session.commit()

    # User attempts to select tenant_b -> rejected with 403 FORBIDDEN_TENANT_ACCESS
    res = await client.post("/api/v1/auth/select-tenant", json={"tenant_id": str(tenant_b.id)}, headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN_TENANT_ACCESS"


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
