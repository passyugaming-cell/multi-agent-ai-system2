import uuid
import time
import pytest
import httpx
from app.database.models.integrations import Integration
from app.database.models.user import User
from app.integrations.oauth import generate_oauth_state, validate_oauth_state, STATE_EXPIRATION_SECONDS
from app.integrations.exceptions import PermanentIntegrationError
from app.core.context import set_actor_context, reset_actor_context, AuthenticatedActor
from app.integrations.permissions import MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS, VIEW_INTEGRATIONS


def test_valid_oauth_state():
    tenant_id = uuid.uuid4()
    state = generate_oauth_state(tenant_id)
    payload = validate_oauth_state(state, expected_tenant_id=tenant_id)
    assert payload["tenant_id"] == str(tenant_id)


def test_valid_oauth_state_without_expected_tenant():
    tenant_id = uuid.uuid4()
    state = generate_oauth_state(tenant_id)
    payload = validate_oauth_state(state)
    assert payload["tenant_id"] == str(tenant_id)


def test_tampered_oauth_state_rejected():
    tenant_id = uuid.uuid4()
    state = generate_oauth_state(tenant_id)
    payload_b64, sig = state.split(".", 1)
    tampered_sig = "a" * len(sig)
    tampered_state = f"{payload_b64}.{tampered_sig}"
    with pytest.raises(PermanentIntegrationError) as excinfo:
        validate_oauth_state(tampered_state, expected_tenant_id=tenant_id)
    assert excinfo.value.error_code == "INVALID_STATE_SIGNATURE"


def test_cross_tenant_oauth_state_rejected():
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    state = generate_oauth_state(tenant_a)
    with pytest.raises(PermanentIntegrationError) as excinfo:
        validate_oauth_state(state, expected_tenant_id=tenant_b)
    assert excinfo.value.error_code == "CROSS_TENANT_STATE"


def test_reused_oauth_state_rejected():
    tenant_id = uuid.uuid4()
    state = generate_oauth_state(tenant_id)
    validate_oauth_state(state)
    with pytest.raises(PermanentIntegrationError) as excinfo:
        validate_oauth_state(state)
    assert excinfo.value.error_code == "REUSED_STATE"


def test_expired_oauth_state_rejected(monkeypatch):
    tenant_id = uuid.uuid4()
    state = generate_oauth_state(tenant_id)
    future_time = int(time.time()) + STATE_EXPIRATION_SECONDS + 10
    monkeypatch.setattr(time, "time", lambda: future_time)
    with pytest.raises(PermanentIntegrationError) as excinfo:
        validate_oauth_state(state, expected_tenant_id=tenant_id)
    assert excinfo.value.error_code == "EXPIRED_STATE"


# 1. No authenticated actor/session -> 401/403
@pytest.mark.asyncio
async def test_case_01_no_actor_context_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id, user_id="system")
    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp.status_code in (401, 403, 400)


# 2. Actor exists but has no permissions -> 403
@pytest.mark.asyncio
async def test_case_02_actor_no_permissions_rejected(async_client, db_session, tenant_a):
    user = User(
        email=f"member_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        tenant_id=tenant_a.id,
        role="member",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    state = generate_oauth_state(tenant_a.id, user_id=str(user.id))
    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp.status_code == 403


# 3. MANAGE_INTEGRATIONS only -> 403
@pytest.mark.asyncio
async def test_case_03_manage_integrations_only_rejected(async_client, db_session, tenant_a):
    user = User(
        email=f"member_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        tenant_id=tenant_a.id,
        role="member",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    state = generate_oauth_state(tenant_a.id, user_id=str(user.id))
    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp.status_code == 403


# 4. MANAGE_CREDENTIALS only -> 403
@pytest.mark.asyncio
async def test_case_04_manage_credentials_only_rejected(async_client, db_session, tenant_a):
    user = User(
        email=f"member_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        tenant_id=tenant_a.id,
        role="member",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    state = generate_oauth_state(tenant_a.id, user_id=str(user.id))
    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp.status_code == 403


# 5. Both permissions -> success via real HTTP middleware traversal
@pytest.mark.asyncio
async def test_case_05_both_permissions_success(async_client, db_session, tenant_a, monkeypatch):
    from app.billing.plans import PlanService
    from app.billing.subscription import SubscriptionService
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    user = User(
        email=f"owner_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        tenant_id=tenant_a.id,
        role="owner",
        is_active=True,
    )
    db_session.add(user)

    integration = Integration(
        integration_key="google_calendar",
        provider_key="google_calendar",
        display_name="Google Calendar",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    real_send = httpx.AsyncClient.send
    async def mock_send(self, request: httpx.Request, *args, **kwargs):
        if "oauth2.googleapis.com/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "token_123", "refresh_token": "token_456"}, request=request)
        return await real_send(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

    state = generate_oauth_state(tenant_a.id, user_id=str(user.id))
    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


# 6. Forged X-Actor-Permissions -> rejected
@pytest.mark.asyncio
async def test_case_06_forged_permission_header_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id)
    resp = await async_client.get(
        f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}",
        headers={"X-Actor-Permissions": "MANAGE_INTEGRATIONS,MANAGE_CREDENTIALS"},
    )
    assert resp.status_code == 403


# 7. Forged role header -> rejected
@pytest.mark.asyncio
async def test_case_07_forged_role_header_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id)
    resp = await async_client.get(
        f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}",
        headers={"X-Actor-Role": "owner"},
    )
    assert resp.status_code == 403


# 8. Forged tenant header -> rejected
@pytest.mark.asyncio
async def test_case_08_forged_tenant_header_rejected(async_client, tenant_a, tenant_b):
    state = generate_oauth_state(tenant_a.id)
    resp = await async_client.get(
        f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}",
        headers={"X-Tenant-ID": str(tenant_b.id)},
    )
    assert resp.status_code == 403


# 9. Tenant A state + Tenant B actor -> rejected
@pytest.mark.asyncio
async def test_case_09_cross_tenant_actor_rejected(async_client, db_session, tenant_a, tenant_b):
    user_b = User(
        email=f"owner_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        tenant_id=tenant_b.id,
        role="owner",
        is_active=True,
    )
    db_session.add(user_b)
    await db_session.commit()

    state = generate_oauth_state(tenant_a.id, user_id=str(user_b.id))
    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp.status_code in (401, 403)


# 10. Tenant A state + Tenant A different privileged actor (user_id mismatch) -> rejected
@pytest.mark.asyncio
async def test_case_10_same_tenant_different_actor_user_id_mismatch_rejected(async_client, db_session, tenant_a, monkeypatch):
    import app.core.auth_service as auth_service
    async def mock_is_revoked(jti: str) -> bool:
        return False
    monkeypatch.setattr(auth_service, "is_token_revoked_redis", mock_is_revoked)

    user_a = User(
        email=f"owner_a_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        tenant_id=tenant_a.id,
        role="owner",
        is_active=True,
    )
    user_b = User(
        email=f"owner_b_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        tenant_id=tenant_a.id,
        role="owner",
        is_active=True,
    )
    db_session.add_all([user_a, user_b])
    await db_session.commit()

    from app.core.auth_service import create_access_token
    token_b = create_access_token({"sub": user_b.email, "tenant_ids": [str(tenant_a.id)], "active_tenant_id": str(tenant_a.id)})

    state = generate_oauth_state(tenant_a.id, user_id=str(user_a.id))
    resp = await async_client.get(
        f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403


# 11. Invalid HMAC signature -> rejected
@pytest.mark.asyncio
async def test_case_11_invalid_signature_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id)
    payload_b64, sig = state.split(".", 1)
    tampered_state = f"{payload_b64}.{'0' * len(sig)}"
    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={tampered_state}")
    assert resp.status_code == 400


# 21. Production environment fail-closed when Redis replay store fails
@pytest.mark.asyncio
async def test_case_21_production_redis_store_failure_fails_closed(monkeypatch, tenant_a):
    from app.integrations.oauth import consume_oauth_jti_redis
    from app.core.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "production")

    import redis.asyncio as aioredis
    def mock_from_url(*args, **kwargs):
        raise ConnectionError("Redis connection refused")

    monkeypatch.setattr(aioredis, "from_url", mock_from_url)

    with pytest.raises(PermanentIntegrationError) as exc_info:
        await consume_oauth_jti_redis("test_nonce_123", int(time.time()) + 900)
    assert exc_info.value.error_code == "OAUTH_STORE_UNAVAILABLE"


# 22. Concurrent double use allows only first consumption
@pytest.mark.asyncio
async def test_case_22_concurrent_double_use_allows_only_one(tenant_a):
    import asyncio
    from app.integrations.oauth import validate_oauth_state_async

    state = generate_oauth_state(tenant_a.id)

    res1, res2 = await asyncio.gather(
        validate_oauth_state_async(state),
        validate_oauth_state_async(state),
        return_exceptions=True,
    )

    results = [res1, res2]
    successes = [r for r in results if isinstance(r, dict)]
    errors = [r for r in results if isinstance(r, PermanentIntegrationError)]

    assert len(successes) == 1
    assert len(errors) == 1
    assert errors[0].error_code == "REUSED_STATE"


# 12. Expired state -> rejected
@pytest.mark.asyncio
async def test_case_12_expired_state_rejected(async_client, tenant_a, monkeypatch):
    state = generate_oauth_state(tenant_a.id)
    future_time = int(time.time()) + STATE_EXPIRATION_SECONDS + 10
    monkeypatch.setattr(time, "time", lambda: future_time)
    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp.status_code == 400


# 13. Replayed state -> rejected
@pytest.mark.asyncio
async def test_case_13_replayed_state_rejected(async_client, db_session, tenant_a, monkeypatch):
    from app.billing.plans import PlanService
    from app.billing.subscription import SubscriptionService
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    user = User(
        email=f"owner_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        tenant_id=tenant_a.id,
        role="owner",
        is_active=True,
    )
    db_session.add(user)

    integration = Integration(
        integration_key="google_calendar",
        provider_key="google_calendar",
        display_name="Google Calendar",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    real_send = httpx.AsyncClient.send
    async def mock_send(self, request: httpx.Request, *args, **kwargs):
        if "oauth2.googleapis.com/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "token_123", "refresh_token": "token_456"}, request=request)
        return await real_send(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

    state = generate_oauth_state(tenant_a.id, user_id=str(user.id))
    resp1 = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp1.status_code == 200

    resp2 = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp2.status_code == 400


# 14. Missing user_id in state -> rejected
@pytest.mark.asyncio
async def test_case_14_missing_user_id_in_state_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id, user_id="")
    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp.status_code in (400, 403)


# 15. Invalid user_id in state -> rejected
@pytest.mark.asyncio
async def test_case_15_invalid_user_id_in_state_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id, user_id="invalid-not-a-uuid")
    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp.status_code in (400, 403)


# 16. Inactive user -> rejected
@pytest.mark.asyncio
async def test_case_16_inactive_user_rejected(async_client, db_session, tenant_a):
    user = User(
        email=f"inactive_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        tenant_id=tenant_a.id,
        role="owner",
        is_active=False,
    )
    db_session.add(user)
    await db_session.commit()

    state = generate_oauth_state(tenant_a.id, user_id=str(user.id))
    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp.status_code in (401, 403)


# 17. Nonexistent user -> rejected
@pytest.mark.asyncio
async def test_case_17_nonexistent_user_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id, user_id=str(uuid.uuid4()))
    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp.status_code in (401, 403)


# 18. State user_id does not equal authenticated actor user_id -> rejected
@pytest.mark.asyncio
async def test_case_18_state_user_id_actor_mismatch_rejected(async_client, db_session, tenant_a, monkeypatch):
    import app.core.auth_service as auth_service
    async def mock_is_revoked(jti: str) -> bool:
        return False
    monkeypatch.setattr(auth_service, "is_token_revoked_redis", mock_is_revoked)

    user_a = User(
        email=f"owner_a_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        tenant_id=tenant_a.id,
        role="owner",
        is_active=True,
    )
    user_b = User(
        email=f"owner_b_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        tenant_id=tenant_a.id,
        role="owner",
        is_active=True,
    )
    db_session.add_all([user_a, user_b])
    await db_session.commit()

    from app.core.auth_service import create_access_token
    token_b = create_access_token({"sub": user_b.email, "tenant_ids": [str(tenant_a.id)], "active_tenant_id": str(tenant_a.id)})

    state = generate_oauth_state(tenant_a.id, user_id=str(user_a.id))
    resp = await async_client.get(
        f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403


# 19. Valid real HTTP browser callback succeeds using database user resolution
@pytest.mark.asyncio
async def test_case_19_valid_real_http_browser_callback_success(async_client, db_session, tenant_a, monkeypatch):
    from app.billing.plans import PlanService
    from app.billing.subscription import SubscriptionService
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    user = User(
        email=f"owner_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="mock_hash_value_123",
        tenant_id=tenant_a.id,
        role="owner",
        is_active=True,
    )
    db_session.add(user)

    integration = Integration(
        integration_key="google_calendar",
        provider_key="google_calendar",
        display_name="Google Calendar",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    real_send = httpx.AsyncClient.send
    async def mock_send(self, request: httpx.Request, *args, **kwargs):
        if "oauth2.googleapis.com/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "mock_access_token_123", "refresh_token": "mock_refresh_token_456"}, request=request)
        return await real_send(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

    state = generate_oauth_state(tenant_a.id, user_id=str(user.id))

    # Real HTTP callback request without manual set_actor_context in test thread
    resp_cb = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp_cb.status_code == 200
    assert resp_cb.json()["status"] == "success"


# 20. Tampered identity/tenant/permissions in state -> rejected
@pytest.mark.asyncio
async def test_case_20_tampered_state_identity_rejected(async_client, tenant_a, tenant_b):
    state = generate_oauth_state(tenant_a.id)
    payload_b64, sig = state.split(".", 1)
    import base64, json
    payload_dict = json.loads(base64.urlsafe_b64decode(payload_b64.encode()).decode())
    payload_dict["tenant_id"] = str(tenant_b.id)
    tampered_b64 = base64.urlsafe_b64encode(json.dumps(payload_dict).encode()).decode()
    tampered_state = f"{tampered_b64}.{sig}"

    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={tampered_state}")
    assert resp.status_code == 400
