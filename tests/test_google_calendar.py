import uuid
import time
import pytest
import pytest_asyncio
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


@pytest.mark.asyncio
async def test_google_calendar_adapter_registration(db_session: AsyncSession, tenant_a):
    from app.integrations.registry import integration_registry
    adapter = integration_registry.get_adapter("google_calendar")
    assert adapter is not None
    assert adapter.provider_key == "google_calendar"


@pytest.mark.asyncio
async def test_google_calendar_connection_and_entitlement(db_session: AsyncSession, tenant_a, tenant_b):
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

    # Disconnect
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
async def test_timezone_handling_and_asia_jakarta(db_session: AsyncSession, tenant_a):
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

    # Create event with explicit Asia/Jakarta timezone
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
    assert "2026-09-10T14:00:00" in event["start"]["dateTime"]


@pytest.mark.asyncio
async def test_check_availability_freebusy(db_session: AsyncSession, tenant_a):
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

    # 1. Available check
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

    # 2. Busy check
    res_busy = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="check_availability",
        params={
            "time_min": "2026-09-10T14:00:00+07:00",
            "time_max": "2026-09-10T15:00:00+07:00",
            "timezone": "Asia/Jakarta",
            "mock_busy_periods": [{"start": "2026-09-10T14:00:00+07:00", "end": "2026-09-10T14:30:00+07:00"}],
        },
    )
    assert res_busy.status == "COMPLETED"
    assert res_busy.result["available"] is False
    assert len(res_busy.result["busy_periods"]) == 1


@pytest.mark.asyncio
async def test_google_calendar_crud_and_idempotency(db_session: AsyncSession, tenant_a):
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

    mock_store = {}

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
            "_mock_events_store": mock_store,
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
            "_mock_events_store": mock_store,
        },
        idempotency_key=idem_key,
    )
    assert res_create_dup.execution_id == res_create.execution_id

    # 3. Get Event
    res_get = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="get_event",
        params={"event_id": event_id, "_mock_events_store": mock_store},
    )
    assert res_get.status == "COMPLETED"
    assert res_get.result["event"]["summary"] == "Team Sync"

    # 4. Update Event
    res_update = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="update_event",
        params={"event_id": event_id, "summary": "Updated Team Sync", "_mock_events_store": mock_store},
    )
    assert res_update.status == "COMPLETED"
    assert res_update.result["event"]["summary"] == "Updated Team Sync"

    # 5. Delete Event
    res_del = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="delete_event",
        params={"event_id": event_id, "_mock_events_store": mock_store},
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

    # Tenant B attempt to execute Tenant A connection fails
    with pytest.raises(ConnectionNotFoundError):
        await service.execute_operation(
            tenant_id=tenant_b.id,
            connection_id=conn_a.id,
            operation="list_calendars",
            params={},
        )


@pytest.mark.asyncio
async def test_workflow_engine_google_calendar_action(db_session: AsyncSession, tenant_a):
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
            "summary": "Workflow Meeting",
            "start": {"dateTime": "2026-09-10T14:00:00+07:00"},
            "end": {"dateTime": "2026-09-10T15:00:00+07:00"},
        },
        context={},
        session=db_session,
        tenant_id=str(tenant_a.id),
    )

    assert res.success is True
    assert res.output["event"]["summary"] == "Workflow Meeting"


@pytest.mark.asyncio
async def test_owner_ai_tool_google_calendar(db_session: AsyncSession, tenant_a):
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
    assert "calendars" in result.data


@pytest.mark.asyncio
async def test_google_calendar_api_routes(async_client: AsyncClient, db_session: AsyncSession, tenant_a):
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

    # 2. Callback route
    resp_cb = await async_client.get(f"/api/v1/integrations/google-calendar/callback?code=testcode&state={state}", headers=headers)
    assert resp_cb.status_code == 200

    # 3. Calendars route
    resp_cal = await async_client.get(f"/api/v1/integrations/google-calendar/calendars?connection_id={conn.id}", headers=headers)
    assert resp_cal.status_code == 200
    assert len(resp_cal.json()["calendars"]) >= 1

    # 4. Availability route
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
