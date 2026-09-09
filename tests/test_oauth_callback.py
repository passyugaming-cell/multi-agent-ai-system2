import uuid
import time
import pytest
import httpx
from app.database.models.integrations import Integration
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


@pytest.mark.asyncio
async def test_oauth_callback_unauthenticated_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id)
    # Without active actor context, callback MUST fail-closed with HTTP 403
    resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
    assert resp.status_code == 403
    assert "Authentication required" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_oauth_callback_insufficient_permissions_rejected(async_client, tenant_a):
    state = generate_oauth_state(tenant_a.id)
    # Actor missing MANAGE_CREDENTIALS
    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="member",
        permissions={MANAGE_INTEGRATIONS, VIEW_INTEGRATIONS},
    )
    token = set_actor_context(actor)
    try:
        resp = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}")
        assert resp.status_code == 403
        assert "Permission denied" in resp.json()["error"]["message"]
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_oauth_callback_flow_integration(async_client, db_session, tenant_a, tenant_b, monkeypatch):
    from app.billing.plans import PlanService
    from app.billing.subscription import SubscriptionService
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    # Seed Google Calendar integration record in DB
    integration = Integration(
        integration_key="google_calendar",
        provider_key="google_calendar",
        display_name="Google Calendar",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    # Intercept send on httpx.AsyncClient to return mock token response for google OAuth token exchange
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

    # 1. Authorize for Tenant A
    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS, VIEW_INTEGRATIONS},
    )
    token = set_actor_context(actor)
    try:
        resp = await async_client.get(
            "/api/v1/integrations/google-calendar/authorize",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        state = data["state"]

        # 2. Callback with active actor context should succeed using state tenant context
        resp_cb = await async_client.get(
            f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state}",
        )
        assert resp_cb.status_code == 200
        assert resp_cb.json()["status"] == "success"

        # 3. Callback with Tenant B header mismatch should be REJECTED (HTTP 403)
        state_b = generate_oauth_state(tenant_a.id)
        actor_b = AuthenticatedActor(
            user_id=uuid.uuid4(),
            tenant_id=tenant_b.id,
            role="owner",
            permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
        )
        token_b = set_actor_context(actor_b)
        try:
            resp_mismatch = await async_client.get(
                f"/api/v1/integrations/google-calendar/callback?code=mock_code&state={state_b}",
                headers={"X-Tenant-ID": str(tenant_b.id)},
            )
            assert resp_mismatch.status_code == 403
        finally:
            reset_actor_context(token_b)
    finally:
        reset_actor_context(token)
