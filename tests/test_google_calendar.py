import uuid
import time
import pytest
import pytest_asyncio
import httpx
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.integrations import Integration, IntegrationConnection, IntegrationCredential
from app.integrations.service import IntegrationService
from app.integrations.exceptions import (
    EntitlementDeniedError,
    ConnectionNotFoundError,
    PermissionDeniedError,
    PermanentIntegrationError,
    TransientIntegrationError,
)
from app.integrations.credentials import CredentialVault, redact_secrets
from app.integrations.permissions import (
    VIEW_INTEGRATIONS,
    MANAGE_INTEGRATIONS,
    MANAGE_CREDENTIALS,
    EXECUTE_INTEGRATION,
)
from app.integrations.oauth import generate_oauth_state, validate_oauth_state
from app.billing.plans import PlanService
from app.billing.subscription import SubscriptionService
from app.core.workflows.actions import ActionExecutor
from app.agents.base.schemas import ToolRequest


@pytest.fixture
def mock_google_http(monkeypatch):
    """Mocks httpx.AsyncClient requests to Google API endpoints for unit tests."""
    original_send = httpx.AsyncClient.send

    async def mock_send(self, request: httpx.Request, *args, **kwargs):
        url_str = str(request.url)

        # 1. OAuth Code Exchange / Token Refresh
        if "oauth2.googleapis.com/token" in url_str:
            return httpx.Response(
                200,
                json={
                    "access_token": "mock_real_access_token_123",
                    "refresh_token": "mock_real_refresh_token_123",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
                request=request,
            )

        # 2. Calendar List
        if "/users/me/calendarList" in url_str:
            return httpx.Response(
                200,
                json={"items": [{"id": "primary", "summary": "Primary Calendar", "timeZone": "Asia/Jakarta", "primary": True}]},
                request=request,
            )

        # 3. Get Calendar
        if "/calendars/primary" in url_str and not url_str.endswith("/events") and request.method == "GET":
            return httpx.Response(
                200,
                json={"id": "primary", "summary": "Primary Calendar", "timeZone": "Asia/Jakarta"},
                request=request,
            )

        # 4. FreeBusy Check
        if "/freeBusy" in url_str:
            return httpx.Response(
                200,
                json={"calendars": {"primary": {"busy": []}}},
                request=request,
            )

        # 5. Create Event
        if "/events" in url_str and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "id": "evt_real_google_123",
                    "summary": "Jakarta Meeting",
                    "start": {"dateTime": "2026-09-10T14:00:00+07:00", "timeZone": "Asia/Jakarta"},
                    "end": {"dateTime": "2026-09-10T15:00:00+07:00", "timeZone": "Asia/Jakarta"},
                    "status": "confirmed",
                },
                request=request,
            )

        # 6. Get Event
        if "/events/evt_real_google_123" in url_str and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "evt_real_google_123",
                    "summary": "Team Sync",
                    "start": {"dateTime": "2026-09-10T10:00:00Z"},
                    "end": {"dateTime": "2026-09-10T11:00:00Z"},
                    "status": "confirmed",
                },
                request=request,
            )

        # 7. Update Event
        if "/events/evt_real_google_123" in url_str and request.method == "PATCH":
            return httpx.Response(
                200,
                json={"id": "evt_real_google_123", "summary": "Updated Team Sync", "status": "confirmed"},
                request=request,
            )

        # 8. Delete Event
        if "/events/evt_real_google_123" in url_str and request.method == "DELETE":
            return httpx.Response(204, request=request)

        return await original_send(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)


@pytest.mark.asyncio
async def test_google_calendar_adapter_registration(db_session: AsyncSession, tenant_a):
    from app.integrations.registry import integration_registry
    adapter = integration_registry.get_adapter("google_calendar")
    assert adapter is not None
    assert adapter.provider_key == "google_calendar"


@pytest.mark.asyncio
async def test_google_calendar_connection_and_entitlement(db_session: AsyncSession, tenant_a):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    integration = Integration(
        integration_key="google_calendar",
        provider_key="google_calendar",
        display_name="Google Calendar",
        category="calendar",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_calendar",
        credentials={"access_token": "mock_access_123", "refresh_token": "mock_refresh_123"},
    )

    assert conn.status == "ACTIVE"
    assert conn.last_connected_at is not None

    disc = await service.disconnect_integration(tenant_a.id, conn.id)
    assert disc.status == "DISCONNECTED"


@pytest.mark.asyncio
async def test_oauth_state_security_and_negative_tests(tenant_a, tenant_b):
    # 1. Valid state generation & validation
    state = generate_oauth_state(tenant_id=tenant_a.id)
    payload = validate_oauth_state(state, expected_tenant_id=tenant_a.id)
    assert payload["tenant_id"] == str(tenant_a.id)

    # 2. Reused state rejected
    with pytest.raises(PermanentIntegrationError) as exc_info:
        validate_oauth_state(state, expected_tenant_id=tenant_a.id)
    assert "REUSED_STATE" in str(exc_info.value.error_code)

    # 3. Cross-tenant state rejected
    state_b = generate_oauth_state(tenant_id=tenant_b.id)
    with pytest.raises(PermanentIntegrationError) as exc_info:
        validate_oauth_state(state_b, expected_tenant_id=tenant_a.id)
    assert "CROSS_TENANT_STATE" in str(exc_info.value.error_code)

    # 4. Tampered state rejected
    parts = state_b.split(".")
    tampered_state = f"{parts[0]}.invalid_signature"
    with pytest.raises(PermanentIntegrationError) as exc_info:
        validate_oauth_state(tampered_state, expected_tenant_id=tenant_b.id)
    assert "INVALID_STATE_SIGNATURE" in str(exc_info.value.error_code)


@pytest.mark.asyncio
async def test_timezone_handling_and_asia_jakarta(mock_google_http, db_session: AsyncSession, tenant_a):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    integration = Integration(
        integration_key="google_calendar",
        provider_key="google_calendar",
        display_name="Google Calendar",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_calendar",
        credentials={"access_token": "mock_access_123"},
    )

    start_str = "2026-09-10T14:00:00+07:00"
    end_str = "2026-09-10T15:00:00+07:00"

    res = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="create_event",
        params={
            "summary": "Jakarta Meeting",
            "start": {"dateTime": start_str, "timeZone": "Asia/Jakarta"},
            "end": {"dateTime": end_str, "timeZone": "Asia/Jakarta"},
        },
    )

    assert res.status == "COMPLETED"
    event = res.result["event"]
    assert event["start"]["timeZone"] == "Asia/Jakarta"


@pytest.mark.asyncio
async def test_check_availability_freebusy(mock_google_http, db_session: AsyncSession, tenant_a):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    integration = Integration(
        integration_key="google_calendar",
        provider_key="google_calendar",
        display_name="Google Calendar",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_calendar",
        credentials={"access_token": "mock_access_123"},
    )

    res_avail = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="check_availability",
        params={
            "time_min": "2026-09-10T14:00:00+07:00",
            "time_max": "2026-09-10T15:00:00+07:00",
            "timezone": "Asia/Jakarta",
        },
    )
    assert res_avail.status == "COMPLETED"
    assert res_avail.result["available"] is True


@pytest.mark.asyncio
async def test_token_refresh_on_401_error(monkeypatch, db_session: AsyncSession, tenant_a):
    """Test 401 response triggers automatic token refresh, updates vault, and retries request."""
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    integration = Integration(
        integration_key="google_calendar",
        provider_key="google_calendar",
        display_name="Google Calendar",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_calendar",
        credentials={"access_token": "expired_access_token", "refresh_token": "valid_refresh_token"},
    )

    token_refreshed = False

    async def mock_send_refresh(self, request: httpx.Request, *args, **kwargs):
        nonlocal token_refreshed
        url_str = str(request.url)

        if "oauth2.googleapis.com/token" in url_str:
            token_refreshed = True
            return httpx.Response(200, json={"access_token": "new_refreshed_access_token_999"}, request=request)

        if "/users/me/calendarList" in url_str:
            auth_header = request.headers.get("Authorization", "")
            if "expired_access_token" in auth_header:
                return httpx.Response(401, json={"error": "invalid_grant"}, request=request)
            if "new_refreshed_access_token_999" in auth_header:
                return httpx.Response(200, json={"items": [{"id": "primary", "summary": "Refreshed Calendar"}]}, request=request)

        return httpx.Response(404, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send_refresh)

    res = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="list_calendars",
        params={},
    )

    assert res.status == "COMPLETED"
    assert token_refreshed is True
    assert res.result["calendars"][0]["summary"] == "Refreshed Calendar"


@pytest.mark.asyncio
async def test_google_calendar_crud_and_idempotency(mock_google_http, db_session: AsyncSession, tenant_a):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    integration = Integration(
        integration_key="google_calendar",
        provider_key="google_calendar",
        display_name="Google Calendar",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_calendar",
        credentials={"access_token": "mock_access_123"},
    )

    # 1. Create
    idem_key = f"idem_gcal_{uuid.uuid4().hex}"
    res_create = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="create_event",
        params={
            "summary": "Team Sync",
            "start": {"dateTime": "2026-09-10T10:00:00Z"},
            "end": {"dateTime": "2026-09-10T11:00:00Z"},
        },
        idempotency_key=idem_key,
    )
    assert res_create.status == "COMPLETED"
    event_id = res_create.result["event_id"]

    # 2. Duplicate Create (Idempotent)
    res_create_dup = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="create_event",
        params={
            "summary": "Team Sync",
            "start": {"dateTime": "2026-09-10T10:00:00Z"},
            "end": {"dateTime": "2026-09-10T11:00:00Z"},
        },
        idempotency_key=idem_key,
    )
    assert res_create_dup.execution_id == res_create.execution_id

    # 3. Get Event
    res_get = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="get_event",
        params={"event_id": event_id},
    )
    assert res_get.status == "COMPLETED"

    # 4. Update Event
    res_update = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="update_event",
        params={"event_id": event_id, "summary": "Updated Team Sync"},
    )
    assert res_update.status == "COMPLETED"

    # 5. Delete Event
    res_del = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="delete_event",
        params={"event_id": event_id},
    )
    assert res_del.status == "COMPLETED"
    assert res_del.result["deleted"] is True


@pytest.mark.asyncio
async def test_tenant_isolation_cross_tenant_gcal(db_session: AsyncSession, tenant_a, tenant_b):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)
    await sub_srv.create_trial_subscription(tenant_b.id)

    integration = Integration(
        integration_key="google_calendar",
        provider_key="google_calendar",
        display_name="Google Calendar",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    conn_a = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_calendar",
        credentials={"access_token": "tenant_a_token"},
    )

    with pytest.raises(ConnectionNotFoundError):
        await service.execute_operation(
            tenant_id=tenant_b.id,
            connection_id=conn_a.id,
            operation="list_calendars",
            params={},
        )


@pytest.mark.asyncio
async def test_workflow_engine_google_calendar_action(mock_google_http, db_session: AsyncSession, tenant_a):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    integration = Integration(
        integration_key="google_calendar",
        provider_key="google_calendar",
        display_name="Google Calendar",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_calendar",
        credentials={"access_token": "mock_access_123"},
    )

    res = await ActionExecutor.execute(
        action_type="google_calendar_create_event",
        params={
            "connection_id": str(conn.id),
            "summary": "Jakarta Meeting",
            "start": {"dateTime": "2026-09-10T14:00:00+07:00"},
            "end": {"dateTime": "2026-09-10T15:00:00+07:00"},
        },
        context={},
        session=db_session,
        tenant_id=str(tenant_a.id),
    )

    assert res.success is True


@pytest.mark.asyncio
async def test_owner_ai_tool_google_calendar(mock_google_http, db_session: AsyncSession, tenant_a):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    integration = Integration(
        integration_key="google_calendar",
        provider_key="google_calendar",
        display_name="Google Calendar",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_calendar",
        credentials={"access_token": "mock_access_123"},
    )

    from app.agents.owner_ai.tools import tool_execute_integration_operation

    req = ToolRequest(
        tenant_id=tenant_a.id,
        tool_name="execute_integration_operation",
        parameters={
            "connection_id": str(conn.id),
            "operation": "list_calendars",
            "params": {},
        },
    )

    result = await tool_execute_integration_operation(req, db_session)
    assert result.success is True


@pytest.mark.asyncio
async def test_google_calendar_api_routes(mock_google_http, async_client: AsyncClient, db_session: AsyncSession, tenant_a):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    integration = Integration(
        integration_key="google_calendar",
        provider_key="google_calendar",
        display_name="Google Calendar",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_calendar",
        credentials={"access_token": "mock_access_123"},
    )

    headers = {
        "X-Tenant-ID": str(tenant_a.id),
        "X-Actor-Permissions": f"{EXECUTE_INTEGRATION},{MANAGE_INTEGRATIONS},{MANAGE_CREDENTIALS}",
    }

    # 1. Authorize route
    resp_auth = await async_client.get("/api/v1/integrations/google-calendar/authorize", headers=headers)
    assert resp_auth.status_code == 200
    state = resp_auth.json()["state"]

    # 2. Permission Negative Tests for Authorize Route
    # Case A: Missing header / permissions = None
    headers_no_perm = {"X-Tenant-ID": str(tenant_a.id)}
    resp_none = await async_client.get("/api/v1/integrations/google-calendar/authorize", headers=headers_no_perm)
    assert resp_none.status_code == 403

    # Case B: Empty permissions string
    headers_empty = {"X-Tenant-ID": str(tenant_a.id), "X-Actor-Permissions": ""}
    resp_empty = await async_client.get("/api/v1/integrations/google-calendar/authorize", headers=headers_empty)
    assert resp_empty.status_code == 403

    # Case C: Lacks MANAGE_INTEGRATIONS permission
    headers_wrong = {"X-Tenant-ID": str(tenant_a.id), "X-Actor-Permissions": "VIEW_INTEGRATIONS"}
    resp_wrong = await async_client.get("/api/v1/integrations/google-calendar/authorize", headers=headers_wrong)
    assert resp_wrong.status_code == 403

    # 3. Callback route
    resp_cb = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=testcode&state={state}", headers=headers)
    assert resp_cb.status_code == 200

    # 4. Calendars route
    resp_cal = await async_client.get(f"/api/v1/integrations/google-calendar/calendars?connection_id={conn.id}", headers=headers)
    assert resp_cal.status_code == 200

    # 5. Availability route
    resp_avail = await async_client.post(
        f"/api/v1/integrations/google-calendar/availability?connection_id={conn.id}",
        json={
            "time_min": "2026-09-10T14:00:00+07:00",
            "time_max": "2026-09-10T15:00:00+07:00",
            "timezone": "Asia/Jakarta",
        },
        headers=headers,
    )
    assert resp_avail.status_code == 200
    assert resp_avail.json()["available"] is True
