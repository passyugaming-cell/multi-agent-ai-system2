import uuid
import pytest
from app.integrations.credentials import redact_secrets
from app.agents.owner_ai.tools import tool_execute_integration_operation
from app.agents.base.schemas import ToolRequest


def test_redact_secrets_short_opaque_secrets():
    credentials = {
        "api_key": "abc",
        "secret": "123",
        "password": "x",
        "token": "a",
        "nested": {
            "refresh_token": "rt_short",
        },
    }

    redacted = redact_secrets(credentials)

    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["secret"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["token"] == "[REDACTED]"
    assert redacted["nested"]["refresh_token"] == "[REDACTED]"


def test_redact_secrets_dict_keys():
    credentials = {
        "access_token": "ya29.a0AfH6SMB...",
        "refresh_token": "1//0e...",
        "api_key": "AIzaSyD...",
        "server_key": "SB-Mid-server-123456",
        "client_secret": "GOCSPX-abc123xyz",
        "app_secret": "meta_app_secret_999",
        "authorization": "Bearer eyJhbGciOi...",
        "verify_token": "my_webhook_verify_token",
        "nested": {
            "private_key": "-----BEGIN PRIVATE KEY-----...",
            "public_info": "safe_data_value",
        },
    }

    redacted = redact_secrets(credentials)

    assert redacted["access_token"] == "[REDACTED]"
    assert redacted["refresh_token"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["server_key"] == "[REDACTED]"
    assert redacted["client_secret"] == "[REDACTED]"
    assert redacted["app_secret"] == "[REDACTED]"
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["verify_token"] == "[REDACTED]"
    assert redacted["nested"]["private_key"] == "[REDACTED]"
    assert redacted["nested"]["public_info"] == "safe_data_value"


def test_redact_secrets_in_lists():
    item_list = [
        {"name": "conn_1", "access_token": "secret_val_1"},
        {"name": "conn_2", "server_key": "secret_val_2"},
        ["nested_list_item", {"bearer_token": "secret_val_3"}],
    ]

    redacted = redact_secrets(item_list)

    assert redacted[0]["access_token"] == "[REDACTED]"
    assert redacted[0]["name"] == "conn_1"
    assert redacted[1]["server_key"] == "[REDACTED]"
    assert redacted[2][1]["bearer_token"] == "[REDACTED]"


def test_redact_secrets_long_string_detection():
    long_secret = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    normal_string = "Hello world from AI OS!"

    assert redact_secrets(long_secret) == "[REDACTED_SECRET]"
    assert redact_secrets(normal_string) == "Hello world from AI OS!"


@pytest.mark.asyncio
async def test_owner_ai_tool_redacts_credentials(db_session, tenant_a, monkeypatch):
    from app.database.models.integrations import Integration
    from app.integrations.service import IntegrationService
    from app.billing.plans import PlanService
    from app.billing.subscription import SubscriptionService

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
        credentials={"access_token": "secret_token_123"},
        allow_internal=True,
    )

    # Mock execute_operation to return sensitive keys in result
    async def mock_execute(*args, **kwargs):
        class MockResult:
            status = "COMPLETED"
            result = {
                "access_token": "raw_sensitive_access_token_123",
                "calendars": [{"id": "primary", "refresh_token": "raw_sensitive_refresh_token"}],
            }
            safe_error_message = None
        return MockResult()

    monkeypatch.setattr(IntegrationService, "execute_operation", mock_execute)

    req = ToolRequest(
        tenant_id=tenant_a.id,
        tool_name="execute_integration_operation",
        parameters={
            "connection_id": str(conn.id),
            "operation": "list_calendars",
            "params": {},
        },
    )

    res = await tool_execute_integration_operation(req, db_session)
    assert res.success is True
    assert res.data["access_token"] == "[REDACTED]"
    assert res.data["calendars"][0]["refresh_token"] == "[REDACTED]"
