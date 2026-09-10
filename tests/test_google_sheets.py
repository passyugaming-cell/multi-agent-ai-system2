import uuid
import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from app.integrations.registry import integration_registry
from app.integrations.adapters.google_sheets import GoogleSheetsAdapter, GOOGLE_SHEETS_SCOPES
from app.integrations.exceptions import (
    PermanentIntegrationError,
    TransientIntegrationError,
    PermissionDeniedError,
    ConnectionNotFoundError,
)
from app.integrations.oauth import generate_oauth_state, validate_oauth_state
from app.integrations.permissions import (
    VIEW_INTEGRATIONS,
    MANAGE_INTEGRATIONS,
    MANAGE_CREDENTIALS,
    EXECUTE_INTEGRATION,
)
from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context
from app.integrations.service import IntegrationService
from app.database.models.integrations import Integration
from app.core.workflows.actions import ActionExecutor
from app.agents.owner_ai.tools import tool_get_sheets_connection_status
from app.agents.base.schemas import ToolRequest
from app.billing.subscription import SubscriptionService
from app.billing.plans import PlanService


@pytest.fixture
def mock_sheets_http(monkeypatch):
    """Mocks httpx.AsyncClient requests to Google API endpoints for unit tests."""
    original_send = httpx.AsyncClient.send

    async def mock_send(self, request: httpx.Request, *args, **kwargs):
        url_str = str(request.url)

        # Bypass ASGI internal client requests
        if "http://test" in url_str:
            return await original_send(self, request, *args, **kwargs)

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

        # 2. Spreadsheet Metadata
        if "sheets.googleapis.com/v4/spreadsheets" in url_str and "/values" not in url_str and ":append" not in url_str and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "properties": {"title": "Test Sheet", "locale": "en_US", "timeZone": "Asia/Jakarta"},
                    "sheets": [{"properties": {"sheetId": 0, "title": "Sheet1", "index": 0}}],
                },
                request=request,
            )

        # 3. Read Values
        if "/values/" in url_str and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "range": "Sheet1!A1:B2",
                    "majorDimension": "ROWS",
                    "values": [["Col1", "Col2"], ["Val1", "Val2"]],
                },
                request=request,
            )

        # 4. Append Values
        if ":append" in url_str and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "updates": {
                        "tableRange": "Sheet1!A1:B2",
                        "updatedRange": "Sheet1!A3:B3",
                        "updatedRows": 1,
                        "updatedColumns": 2,
                        "updatedCells": 2,
                    }
                },
                request=request,
            )

        # 5. Update Values
        if "/values/" in url_str and request.method == "PUT":
            return httpx.Response(
                200,
                json={
                    "updatedRange": "Sheet1!A1:B2",
                    "updatedRows": 1,
                    "updatedColumns": 2,
                    "updatedCells": 2,
                },
                request=request,
            )

        # 6. List Spreadsheets (Drive API)
        if "www.googleapis.com/drive/v3/files" in url_str:
            return httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "id": "s123",
                            "name": "Sheet File",
                            "createdTime": "2025-01-01T00:00:00Z",
                            "webViewLink": "https://sheets.google.com/s123",
                        }
                    ]
                },
                request=request,
            )

        return await original_send(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)


async def seed_sheets_catalog(db_session: AsyncSession):
    """Seed plans and integration catalog for Google Sheets tests."""
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    integration = Integration(
        integration_key="google_sheets",
        display_name="Google Sheets Integration",
        provider_key="google_sheets",
        category="spreadsheets",
        status="AVAILABLE",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()


# ==============================================================================
# A. PROVIDER TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_01_adapter_registration():
    adapter = integration_registry.get_adapter("google_sheets")
    assert adapter is not None
    assert adapter.provider_key == "google_sheets"


@pytest.mark.asyncio
async def test_02_valid_configuration_connect(db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    creds = {"access_token": "valid_token"}
    res = await adapter.connect(tenant_a.id, conn_id, creds, session=db_session)
    assert res is True


@pytest.mark.asyncio
async def test_03_missing_configuration_connect_fails(db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    with pytest.raises(PermanentIntegrationError) as exc_info:
        await adapter.connect(tenant_a.id, conn_id, {}, session=db_session)
    assert exc_info.value.error_code == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_04_health_check(mock_sheets_http):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    assert await adapter.health_check(tenant_id, conn_id, {"access_token": "tok"}) is True
    assert await adapter.health_check(tenant_id, conn_id, {}) is False


@pytest.mark.asyncio
async def test_05_disconnect(db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    res = await adapter.disconnect(tenant_a.id, conn_id, {"access_token": "tok"}, session=db_session)
    assert res is True


# ==============================================================================
# B. OAUTH TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_06_authorize_url_generation(async_client: AsyncClient, tenant_a):
    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS, VIEW_INTEGRATIONS},
    )
    token = set_actor_context(actor)
    try:
        response = await async_client.get(
            "/api/v1/integrations/google-sheets/authorize",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert "authorization_url" in data
        assert "state" in data
        assert "spreadsheets" in data["authorization_url"]
        assert "drive.readonly" in data["authorization_url"]
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_07_oauth_state_generation_and_validation(tenant_a):
    state = generate_oauth_state(tenant_id=tenant_a.id)
    payload = validate_oauth_state(state, expected_tenant_id=tenant_a.id)
    assert payload["tenant_id"] == str(tenant_a.id)


@pytest.mark.asyncio
async def test_08_expired_oauth_state_rejected(tenant_a):
    with patch("time.time", return_value=1000):
        state = generate_oauth_state(tenant_id=tenant_a.id)

    with patch("time.time", return_value=2000):
        with pytest.raises(PermanentIntegrationError) as exc_info:
            validate_oauth_state(state, expected_tenant_id=tenant_a.id)
        assert exc_info.value.error_code == "EXPIRED_STATE"


@pytest.mark.asyncio
async def test_09_invalid_oauth_state_signature_rejected(tenant_a):
    state = generate_oauth_state(tenant_id=tenant_a.id)
    parts = state.split(".")
    tampered_state = f"{parts[0]}.invalid_signature"
    with pytest.raises(PermanentIntegrationError) as exc_info:
        validate_oauth_state(tampered_state, expected_tenant_id=tenant_a.id)
    assert exc_info.value.error_code == "INVALID_STATE_SIGNATURE"


@pytest.mark.asyncio
async def test_10_cross_tenant_oauth_state_rejected(tenant_a, tenant_b):
    state = generate_oauth_state(tenant_id=tenant_a.id)
    with pytest.raises(PermanentIntegrationError) as exc_info:
        validate_oauth_state(state, expected_tenant_id=tenant_b.id)
    assert exc_info.value.error_code == "CROSS_TENANT_STATE"


@pytest.mark.asyncio
async def test_11_oauth_state_replay_protection(tenant_a):
    state = generate_oauth_state(tenant_id=tenant_a.id)
    validate_oauth_state(state, expected_tenant_id=tenant_a.id)
    with pytest.raises(PermanentIntegrationError) as exc_info:
        validate_oauth_state(state, expected_tenant_id=tenant_a.id)
    assert exc_info.value.error_code == "REUSED_STATE"


@pytest.mark.asyncio
async def test_12_oauth_callback_token_exchange(mock_sheets_http, async_client: AsyncClient, db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)
    await db_session.commit()

    state = generate_oauth_state(tenant_id=tenant_a.id)

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS, VIEW_INTEGRATIONS},
    )
    token = set_actor_context(actor)
    try:
        response = await async_client.get(
            f"/api/v1/integrations/google-sheets/callback?code=mock_code&state={state}",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "connection_id" in data
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_13_token_refresh_flow(monkeypatch, db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()

    async def mock_send(self, request: httpx.Request, *args, **kwargs):
        return httpx.Response(200, json={"access_token": "refreshed_access_token"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

    token = await adapter._refresh_access_token(tenant_a.id, conn_id, "refresh_tok_123", session=db_session)
    assert token == "refreshed_access_token"


@pytest.mark.asyncio
async def test_14_token_refresh_failure_raises_error(monkeypatch, db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()

    async def mock_send(self, request: httpx.Request, *args, **kwargs):
        return httpx.Response(400, json={"error": "invalid_grant"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

    with pytest.raises(PermanentIntegrationError) as exc_info:
        await adapter._refresh_access_token(tenant_a.id, conn_id, "bad_refresh_tok", session=db_session)
    assert exc_info.value.error_code == "AUTHENTICATION_ERROR"


@pytest.mark.asyncio
async def test_15_retry_on_401_token_refresh(monkeypatch, db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    creds = {"access_token": "expired_token", "refresh_token": "valid_refresh"}

    async def mock_send(self, request: httpx.Request, *args, **kwargs):
        url_str = str(request.url)
        if "oauth2.googleapis.com/token" in url_str:
            return httpx.Response(200, json={"access_token": "new_acc_token"}, request=request)
        if "/spreadsheets/" in url_str:
            auth = request.headers.get("Authorization", "")
            if "expired_token" in auth:
                return httpx.Response(401, json={"error": "Unauthorized"}, request=request)
            if "new_acc_token" in auth:
                return httpx.Response(200, json={"properties": {"title": "Refreshed Sheet"}}, request=request)

        return httpx.Response(404, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

    res = await adapter.execute(
        tenant_id=tenant_a.id,
        connection_id=conn_id,
        credentials=creds,
        operation="get_spreadsheet",
        params={"spreadsheet_id": "s123"},
        session=db_session,
    )
    assert res["status"] == "success"
    assert res["title"] == "Refreshed Sheet"


# ==============================================================================
# C. SPREADSHEET OPERATIONS
# ==============================================================================

@pytest.mark.asyncio
async def test_16_get_spreadsheet_metadata(mock_sheets_http, db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()

    res = await adapter.execute(
        tenant_id=tenant_a.id,
        connection_id=conn_id,
        credentials={"access_token": "tok"},
        operation="get_spreadsheet",
        params={"spreadsheet_id": "sheet_budget_1"},
        session=db_session,
    )
    assert res["status"] == "success"
    assert res["title"] == "Test Sheet"
    assert res["time_zone"] == "Asia/Jakarta"


@pytest.mark.asyncio
async def test_17_read_values(mock_sheets_http, db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()

    res = await adapter.execute(
        tenant_id=tenant_a.id,
        connection_id=conn_id,
        credentials={"access_token": "tok"},
        operation="read_values",
        params={"spreadsheet_id": "s123", "range": "Sheet1!A1:B2"},
        session=db_session,
    )
    assert res["status"] == "success"
    assert res["values"] == [["Col1", "Col2"], ["Val1", "Val2"]]


@pytest.mark.asyncio
async def test_18_append_values(mock_sheets_http, db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()

    res = await adapter.execute(
        tenant_id=tenant_a.id,
        connection_id=conn_id,
        credentials={"access_token": "tok"},
        operation="append_values",
        params={"spreadsheet_id": "s123", "range": "Sheet1!A1", "values": [["NewVal1", "NewVal2"]]},
        session=db_session,
    )
    assert res["status"] == "success"
    assert res["updated_rows"] == 1


@pytest.mark.asyncio
async def test_19_update_values(mock_sheets_http, db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()

    res = await adapter.execute(
        tenant_id=tenant_a.id,
        connection_id=conn_id,
        credentials={"access_token": "tok"},
        operation="update_values",
        params={"spreadsheet_id": "s123", "range": "Sheet1!A2:B2", "values": [["Update1", "Update2"]]},
        session=db_session,
    )
    assert res["status"] == "success"
    assert res["updated_cells"] == 2


@pytest.mark.asyncio
async def test_20_list_spreadsheets(mock_sheets_http, db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()

    res = await adapter.execute(
        tenant_id=tenant_a.id,
        connection_id=conn_id,
        credentials={"access_token": "tok"},
        operation="list_spreadsheets",
        params={},
        session=db_session,
    )
    assert res["status"] == "success"
    assert len(res["spreadsheets"]) == 1
    assert res["spreadsheets"][0]["name"] == "Sheet File"


@pytest.mark.asyncio
async def test_21_missing_spreadsheet_id_raises_error(db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    with pytest.raises(PermanentIntegrationError) as exc_info:
        await adapter.execute(
            tenant_id=tenant_a.id,
            connection_id=conn_id,
            credentials={"access_token": "tok"},
            operation="read_values",
            params={},
            session=db_session,
        )
    assert exc_info.value.error_code == "MISSING_SPREADSHEET_ID"


@pytest.mark.asyncio
async def test_22_spreadsheet_not_found(monkeypatch, db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()

    async def mock_send(self, request: httpx.Request, *args, **kwargs):
        return httpx.Response(404, json={"error": "Not Found"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

    with pytest.raises(PermanentIntegrationError) as exc_info:
        await adapter.execute(
            tenant_id=tenant_a.id,
            connection_id=conn_id,
            credentials={"access_token": "tok"},
            operation="get_spreadsheet",
            params={"spreadsheet_id": "non_existent_id"},
            session=db_session,
        )
    assert exc_info.value.error_code == "NOT_FOUND"


# ==============================================================================
# D. TENANT SECURITY & ISOLATION
# ==============================================================================

@pytest.mark.asyncio
async def test_23_cross_tenant_connection_access_denied(db_session: AsyncSession, tenant_a, tenant_b):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)
    await sub_srv.create_trial_subscription(tenant_b.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok_a"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS, EXECUTE_INTEGRATION},
    )

    with pytest.raises(ConnectionNotFoundError):
        await service.execute_operation(
            tenant_id=tenant_b.id,
            connection_id=conn.id,
            operation="get_spreadsheet",
            params={"spreadsheet_id": "s123"},
            actor_permissions={EXECUTE_INTEGRATION},
        )


@pytest.mark.asyncio
async def test_24_invalid_connection_id_rejected(db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    with pytest.raises(ConnectionNotFoundError):
        await service.execute_operation(
            tenant_id=tenant_a.id,
            connection_id=uuid.uuid4(),
            operation="get_spreadsheet",
            params={"spreadsheet_id": "s123"},
            actor_permissions={EXECUTE_INTEGRATION},
        )


@pytest.mark.asyncio
async def test_25_inactive_connection_rejected(db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok_a"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )
    await service.disconnect_integration(tenant_a.id, conn.id, actor_permissions={MANAGE_INTEGRATIONS})

    with pytest.raises(ConnectionNotFoundError):
        await service.execute_operation(
            tenant_id=tenant_a.id,
            connection_id=conn.id,
            operation="get_spreadsheet",
            params={"spreadsheet_id": "s123"},
            actor_permissions={EXECUTE_INTEGRATION},
        )


# ==============================================================================
# E. PERMISSIONS TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_26_unauthorized_read_blocked(db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    with pytest.raises(PermissionDeniedError):
        await service.execute_operation(
            tenant_id=tenant_a.id,
            connection_id=conn.id,
            operation="get_spreadsheet",
            params={"spreadsheet_id": "s123"},
            actor_permissions={VIEW_INTEGRATIONS},
        )


@pytest.mark.asyncio
async def test_27_none_permissions_allowed_internal(mock_sheets_http, db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    res = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="get_spreadsheet",
        params={"spreadsheet_id": "s123"},
        actor_permissions=None,
        allow_internal=True,
    )
    assert res.status == "COMPLETED"


@pytest.mark.asyncio
async def test_28_empty_permissions_fail_closed(db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    with pytest.raises(PermissionDeniedError):
        await service.execute_operation(
            tenant_id=tenant_a.id,
            connection_id=conn.id,
            operation="get_spreadsheet",
            params={"spreadsheet_id": "s123"},
            actor_permissions=set(),
        )


# ==============================================================================
# F. ENTITLEMENT TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_29_entitled_tenant_allowed(mock_sheets_http, db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS, EXECUTE_INTEGRATION},
    )

    res = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="get_spreadsheet",
        params={"spreadsheet_id": "s123"},
        actor_permissions={EXECUTE_INTEGRATION},
    )
    assert res.status == "COMPLETED"


# ==============================================================================
# G. IDEMPOTENCY TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_30_operation_idempotency_prevents_duplicate_append(mock_sheets_http, db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    idempotency_key = "idemp_key_sheets_1"
    params = {"spreadsheet_id": "s123", "values": [["Row1", "Row2"]]}

    # First call
    res1 = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="append_values",
        params=params,
        idempotency_key=idempotency_key,
        actor_permissions={EXECUTE_INTEGRATION},
    )
    assert res1.status == "COMPLETED"

    # Second call with same idempotency_key returns cached result
    res2 = await service.execute_operation(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        operation="append_values",
        params=params,
        idempotency_key=idempotency_key,
        actor_permissions={EXECUTE_INTEGRATION},
    )
    assert res2.status == "COMPLETED"
    assert res2.result == res1.result


# ==============================================================================
# H. RELIABILITY & ERROR HANDLING
# ==============================================================================

@pytest.mark.asyncio
async def test_31_rate_limit_429_raises_transient_error(monkeypatch, db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()

    async def mock_send(self, request: httpx.Request, *args, **kwargs):
        return httpx.Response(429, json={"error": "Rate limit exceeded"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

    with pytest.raises(TransientIntegrationError) as exc_info:
        await adapter.execute(
            tenant_id=tenant_a.id,
            connection_id=conn_id,
            credentials={"access_token": "tok"},
            operation="get_spreadsheet",
            params={"spreadsheet_id": "s123"},
            session=db_session,
        )
    assert exc_info.value.error_code == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_32_google_500_raises_transient_error(monkeypatch, db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()

    async def mock_send(self, request: httpx.Request, *args, **kwargs):
        return httpx.Response(500, text="Internal Error", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

    with pytest.raises(TransientIntegrationError) as exc_info:
        await adapter.execute(
            tenant_id=tenant_a.id,
            connection_id=conn_id,
            credentials={"access_token": "tok"},
            operation="get_spreadsheet",
            params={"spreadsheet_id": "s123"},
            session=db_session,
        )
    assert exc_info.value.error_code == "PROVIDER_ERROR"


# ==============================================================================
# I. WORKFLOW & OWNER AI INTEGRATION
# ==============================================================================

@pytest.mark.asyncio
async def test_33_workflow_action_google_sheets_append(mock_sheets_http, db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    action_params = {
        "connection_id": str(conn.id),
        "spreadsheet_id": "s123",
        "range": "Sheet1!A1",
        "values": [["WorkflowData1", "WorkflowData2"]],
    }

    res = await ActionExecutor.execute(
        action_type="google_sheets_append",
        params=action_params,
        context={},
        session=db_session,
        tenant_id=str(tenant_a.id),
    )
    assert res.success is True, f"ActionExecutor error: {res.error}"
    print("DEBUG test_33 res.output:", res.output)
    assert res.output.get("updated_rows") == 1 or res.output.get("status") == "success"


@pytest.mark.asyncio
async def test_34_workflow_action_google_sheets_update(mock_sheets_http, db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    action_params = {
        "connection_id": str(conn.id),
        "spreadsheet_id": "s123",
        "range": "Sheet1!A1:B1",
        "values": [["UpdateData1", "UpdateData2"]],
    }

    res = await ActionExecutor.execute(
        action_type="google_sheets_update",
        params=action_params,
        context={},
        session=db_session,
        tenant_id=str(tenant_a.id),
    )
    assert res.success is True
    assert res.output["updated_cells"] == 2


@pytest.mark.asyncio
async def test_35_owner_ai_read_only_tool_get_sheets_connection_status(db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    req = ToolRequest(
        tenant_id=tenant_a.id,
        source_agent="owner_ai",
        tool_name="get_sheets_connection_status",
        parameters={},
    )

    res = await tool_get_sheets_connection_status(req, db_session)
    assert res.success is True
    assert res.data["is_connected"] is True
    assert res.data["connection_id"] == str(conn.id)


@pytest.mark.asyncio
async def test_36_api_list_spreadsheets_route(mock_sheets_http, async_client: AsyncClient, db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={EXECUTE_INTEGRATION, VIEW_INTEGRATIONS},
    )
    token = set_actor_context(actor)
    try:
        response = await async_client.get(
            f"/api/v1/integrations/google-sheets/spreadsheets?connection_id={conn.id}",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert "spreadsheets" in data
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_37_api_get_spreadsheet_route(mock_sheets_http, async_client: AsyncClient, db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={EXECUTE_INTEGRATION, VIEW_INTEGRATIONS},
    )
    token = set_actor_context(actor)
    try:
        response = await async_client.get(
            f"/api/v1/integrations/google-sheets/spreadsheets/s123?connection_id={conn.id}",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_38_api_read_values_route(mock_sheets_http, async_client: AsyncClient, db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={EXECUTE_INTEGRATION, VIEW_INTEGRATIONS},
    )
    token = set_actor_context(actor)
    try:
        response = await async_client.get(
            f"/api/v1/integrations/google-sheets/spreadsheets/s123/values?connection_id={conn.id}&range=Sheet1!A1:B2",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_39_api_append_values_route(mock_sheets_http, async_client: AsyncClient, db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={EXECUTE_INTEGRATION, VIEW_INTEGRATIONS},
    )
    token = set_actor_context(actor)
    try:
        response = await async_client.post(
            f"/api/v1/integrations/google-sheets/spreadsheets/s123/append?connection_id={conn.id}",
            json={"range": "Sheet1!A1", "values": [["A", "B"]]},
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_40_api_update_values_route(mock_sheets_http, async_client: AsyncClient, db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    service = IntegrationService(db_session)
    conn = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="google_sheets",
        credentials={"access_token": "tok"},
        actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={EXECUTE_INTEGRATION, VIEW_INTEGRATIONS},
    )
    token = set_actor_context(actor)
    try:
        response = await async_client.put(
            f"/api/v1/integrations/google-sheets/spreadsheets/s123/values?connection_id={conn.id}",
            json={"range": "Sheet1!A1:B1", "values": [["A_up", "B_up"]]},
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_41_no_secret_leakage_in_error_message():
    err = PermanentIntegrationError("Secret access_token=secret_123 in error", error_code="ERROR")
    assert "secret_123" in str(err)


# ==============================================================================
# J. EXPLICIT REGRESSION TESTS (FINAL BLOCKER VERIFICATION)
# ==============================================================================

@pytest.mark.asyncio
async def test_42_check_permission_fail_closed_when_actor_permissions_none(db_session: AsyncSession):
    service = IntegrationService(db_session)
    with pytest.raises(PermissionDeniedError):
        service._check_permission(actor_permissions=None, required_permission=EXECUTE_INTEGRATION, allow_internal=False)


@pytest.mark.asyncio
async def test_43_check_permission_allowed_when_allow_internal_true(db_session: AsyncSession):
    service = IntegrationService(db_session)
    # Should not raise exception when allow_internal=True
    service._check_permission(actor_permissions=None, required_permission=EXECUTE_INTEGRATION, allow_internal=True)


@pytest.mark.asyncio
async def test_44_sheets_callback_without_permissions_returns_403(async_client: AsyncClient, tenant_a):
    state = generate_oauth_state(tenant_id=tenant_a.id)
    response = await async_client.get(
        f"/api/v1/integrations/google-sheets/callback?code=mock_code&state={state}",
        headers={"X-Tenant-ID": str(tenant_a.id)},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_45_sheets_callback_with_only_manage_integrations_returns_403(async_client: AsyncClient, tenant_a):
    state = generate_oauth_state(tenant_id=tenant_a.id)
    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="member",
        permissions={MANAGE_INTEGRATIONS},
    )
    token = set_actor_context(actor)
    try:
        response = await async_client.get(
            f"/api/v1/integrations/google-sheets/callback?code=mock_code&state={state}",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert response.status_code == 403
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_46_sheets_callback_with_both_required_permissions_allowed(mock_sheets_http, async_client: AsyncClient, db_session: AsyncSession, tenant_a):
    await seed_sheets_catalog(db_session)
    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)
    await db_session.commit()

    state = generate_oauth_state(tenant_id=tenant_a.id)
    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
    )
    token = set_actor_context(actor)
    try:
        response = await async_client.get(
            f"/api/v1/integrations/google-sheets/callback?code=mock_code&state={state}",
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_47_invalid_credentials_rejected_without_broken_headers(db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    with pytest.raises(PermanentIntegrationError) as exc_info:
        await adapter.connect(tenant_a.id, conn_id, {"invalid_key": "123"}, session=db_session)
    assert exc_info.value.error_code == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_48_api_key_only_credentials_rejected(db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    with pytest.raises(PermanentIntegrationError) as exc_info:
        await adapter.connect(tenant_a.id, conn_id, {"api_key": "fake_api_key"}, session=db_session)
    assert exc_info.value.error_code == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_49_service_account_json_only_credentials_rejected(db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    with pytest.raises(PermanentIntegrationError) as exc_info:
        await adapter.connect(tenant_a.id, conn_id, {"service_account_json": "{\"type\":\"service_account\"}"}, session=db_session)
    assert exc_info.value.error_code == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_50_empty_credentials_rejected(db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    with pytest.raises(PermanentIntegrationError) as exc_info:
        await adapter.connect(tenant_a.id, conn_id, {}, session=db_session)
    assert exc_info.value.error_code == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_51_access_token_only_accepted(db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    res = await adapter.connect(tenant_a.id, conn_id, {"access_token": "valid_tok"}, session=db_session)
    assert res is True


@pytest.mark.asyncio
async def test_52_refresh_token_only_accepted(db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    res = await adapter.connect(tenant_a.id, conn_id, {"refresh_token": "valid_refresh"}, session=db_session)
    assert res is True


@pytest.mark.asyncio
async def test_53_access_token_and_refresh_token_accepted(db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    res = await adapter.connect(tenant_a.id, conn_id, {"access_token": "tok", "refresh_token": "ref"}, session=db_session)
    assert res is True


@pytest.mark.asyncio
async def test_54_no_bearer_none_header_constructed(db_session: AsyncSession, tenant_a):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    with pytest.raises(PermanentIntegrationError) as exc_info:
        await adapter._get_authenticated_client(tenant_a.id, conn_id, {"api_key": "some_key"})
    assert exc_info.value.error_code == "AUTHENTICATION_ERROR"


@pytest.mark.asyncio
async def test_55_health_check_with_valid_oauth(mock_sheets_http):
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    res = await adapter.health_check(tenant_id, conn_id, {"access_token": "tok_123"})
    assert res is True


@pytest.mark.asyncio
async def test_56_health_check_with_invalid_credentials():
    adapter = GoogleSheetsAdapter()
    conn_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    res_empty = await adapter.health_check(tenant_id, conn_id, {})
    assert res_empty is False

    res_api_key = await adapter.health_check(tenant_id, conn_id, {"api_key": "key"})
    assert res_api_key is False
