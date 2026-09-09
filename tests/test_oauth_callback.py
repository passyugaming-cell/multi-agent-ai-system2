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
async def test_oauth_callback_no_actor_context_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id, user_id="system")
    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp.status_code in (401, 403)
    assert "Authentication required" in resp.json()["error"]["message"]


# 2. Actor exists but has no permissions -> 403
@pytest.mark.asyncio
async def test_oauth_callback_actor_no_permissions_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id)
    actor = AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=tenant_a.id, role="member", permissions=set())
    token = set_actor_context(actor)
    try:
        resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
        assert resp.status_code == 403
    finally:
        reset_actor_context(token)


# 3. Actor has only MANAGE_INTEGRATIONS -> 403
@pytest.mark.asyncio
async def test_oauth_callback_actor_manage_integrations_only_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id)
    actor = AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=tenant_a.id, role="member", permissions={MANAGE_INTEGRATIONS})
    token = set_actor_context(actor)
    try:
        resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
        assert resp.status_code == 403
    finally:
        reset_actor_context(token)


# 4. Actor has only MANAGE_CREDENTIALS -> 403
@pytest.mark.asyncio
async def test_oauth_callback_actor_manage_credentials_only_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id)
    actor = AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=tenant_a.id, role="member", permissions={MANAGE_CREDENTIALS})
    token = set_actor_context(actor)
    try:
        resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
        assert resp.status_code == 403
    finally:
        reset_actor_context(token)


# 6. Forged X-Actor-Permissions -> rejected
@pytest.mark.asyncio
async def test_oauth_callback_forged_permission_header_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id)
    resp = await async_client.get(
        f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}",
        headers={"X-Actor-Permissions": "MANAGE_INTEGRATIONS,MANAGE_CREDENTIALS"},
    )
    assert resp.status_code == 403


# 7. Forged role header -> rejected
@pytest.mark.asyncio
async def test_oauth_callback_forged_role_header_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id)
    resp = await async_client.get(
        f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}",
        headers={"X-Actor-Role": "owner"},
    )
    assert resp.status_code == 403


# 8. Forged tenant header -> rejected
@pytest.mark.asyncio
async def test_oauth_callback_forged_tenant_header_rejected(async_client, tenant_a, tenant_b):
    state = generate_oauth_state(tenant_a.id)
    resp = await async_client.get(
        f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}",
        headers={"X-Tenant-ID": str(tenant_b.id)},
    )
    assert resp.status_code == 403


# 9. Tenant A OAuth state + Tenant B authenticated actor -> rejected
@pytest.mark.asyncio
async def test_oauth_callback_cross_tenant_actor_rejected(async_client, tenant_a, tenant_b):
    state = generate_oauth_state(tenant_a.id)
    actor_b = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_b.id,
        role="owner",
        permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )
    token = set_actor_context(actor_b)
    try:
        resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
        assert resp.status_code == 403
    finally:
        reset_actor_context(token)


# 18. Valid authenticated browser callback succeeds using real HTTP flow through database user lookup
@pytest.mark.asyncio
async def test_oauth_callback_real_http_authenticated_flow(async_client, db_session, tenant_a, monkeypatch):
    from app.billing.plans import PlanService
    from app.billing.subscription import SubscriptionService
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    # 1. Create active owner User in DB for Tenant A
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

    # Intercept Google OAuth code exchange
    real_send = httpx.AsyncClient.send
    async def mock_send(self, request: httpx.Request, *args, **kwargs):
        if "oauth2.googleapis.com/token" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "access_token": "mock_access_token_123",
                    "refresh_token": "mock_refresh_token_456",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
                request=request,
            )
        return await real_send(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

    # Generate state token containing active DB user's ID
    state = generate_oauth_state(tenant_a.id, user_id=str(user.id))

    # Perform callback request through HTTP client WITHOUT manual set_actor_context() in test thread!
    resp_cb = await async_client.get(
        f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}",
    )
    assert resp_cb.status_code == 200
    assert resp_cb.json()["status"] == "success"
