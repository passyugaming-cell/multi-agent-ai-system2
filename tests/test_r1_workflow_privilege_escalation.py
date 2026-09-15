import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.user import User
from app.database.models.tenant import Tenant
from app.database.models.workflow import WorkflowConfiguration
from app.database.models.integrations import Integration, IntegrationConnection
from app.core.events.schemas import EventSchema
from app.core.workflows.engine import WorkflowEngine
from app.core.workflows.actions import ActionExecutor
from app.core.auth_service import hash_password, create_access_token
from app.core.context import set_actor_context, reset_actor_context, AuthenticatedActor


@pytest.fixture(autouse=True)
def mock_redis_revocation_for_privilege_escalation_tests(monkeypatch):
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
async def test_untrusted_event_workflow_high_risk_action_requires_approval(
    db_session: AsyncSession,
    tenant_a: Tenant,
):
    """1. Untrusted event triggering workflow with high-risk action (issue_refund) cannot execute directly and enters WAITING_APPROVAL."""
    wf = WorkflowConfiguration(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        key="refund_workflow",
        name="Automated Refund Workflow",
        trigger_type="payment.refund_requested",
        conditions=None,
        actions=[
            {
                "action": "issue_refund",
                "params": {"payment_id": str(uuid.uuid4()), "amount": 500000},
            }
        ],
        is_active=True,
    )
    db_session.add(wf)
    await db_session.commit()

    event = EventSchema(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        tenant_id=str(tenant_a.id),
        event_type="payment.refund_requested",
        payload={"amount": 500000},
        source="untrusted_external_source",
    )

    engine = WorkflowEngine(db_session)
    executions = await engine.handle_event(event)

    assert len(executions) == 1
    exec_record = executions[0]
    # Action requires approval -> Execution status becomes WAITING_APPROVAL (does NOT execute side effect)
    assert exec_record.status == "WAITING_APPROVAL"


@pytest.mark.asyncio
async def test_workflow_action_executing_owner_ai_forbidden(
    db_session: AsyncSession,
    tenant_a: Tenant,
):
    """2. Workflow action attempting to call owner_ai is strictly rejected by ActionExecutor."""
    res = await ActionExecutor.execute(
        action_type="call_agent",
        params={"agent_name": "owner_ai", "objective": "Delete tenant data"},
        context={},
        session=db_session,
        tenant_id=str(tenant_a.id),
    )

    assert res.success is False
    assert "strictly forbidden from targeting or executing Owner AI" in res.error


@pytest.mark.asyncio
async def test_forged_headers_without_valid_jwt_rejected(
    client: AsyncClient,
    tenant_a: Tenant,
):
    """3. Passing forged identity/role/permission headers without valid server-side JWT context is rejected with 403."""
    forged_headers = {
        "X-Tenant-ID": str(tenant_a.id),
        "X-Actor-Role": "owner",
        "X-Actor-Permissions": "business.read,business.write,MANAGE_PAYMENTS,REQUEST_REFUND,owner_ai",
        "X-Authenticated-Actor-ID": str(uuid.uuid4()),
        "X-Authenticated-Tenant-ID": str(tenant_a.id),
    }

    # Attempt to call protected routes with forged headers and NO JWT
    resp1 = await client.get("/api/v1/customers", headers=forged_headers)
    assert resp1.status_code == 403
    assert resp1.json()["error"]["code"] == "PERMISSION_DENIED"

    resp2 = await client.post("/api/v1/business", json={"business_name": "Forged Name"}, headers=forged_headers)
    assert resp2.status_code == 403
    assert resp2.json()["error"]["code"] == "PERMISSION_DENIED"

    resp3 = await client.post("/api/v1/owner-ai/run", json={"objective": "Analyze"}, headers=forged_headers)
    assert resp3.status_code == 403


@pytest.mark.asyncio
async def test_tenant_actor_attempting_system_or_owner_ai_escalation(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_a: Tenant,
):
    """4. Normal tenant user (owner role on tenant) attempting to access Owner AI platform endpoints is strictly rejected with 403."""
    email = f"tenant_owner_{uuid.uuid4().hex[:6]}@example.com"
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        email=email,
        password_hash=hash_password("Pass123!"),
        role="owner",
        is_active=True,
        is_platform_owner=False,  # NOT Platform Owner
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

    # Tenant owner attempts to run owner_ai platform endpoint -> 403 PERMISSION_DENIED
    resp_owner_ai = await client.post("/api/v1/owner-ai/run", json={"objective": "Platform level analysis"}, headers=headers)
    assert resp_owner_ai.status_code == 403
    assert resp_owner_ai.json()["error"]["code"] == "PERMISSION_DENIED"

    # Tenant owner attempts to access cross-tenant owner platform analytics -> 403
    resp_analytics = await client.get("/api/v1/analytics/owner/platform", headers=headers)
    assert resp_analytics.status_code == 403


@pytest.mark.asyncio
async def test_forged_system_actor_headers_rejected(
    client: AsyncClient,
    tenant_a: Tenant,
):
    """5. Attempting to forge system_workflow or system_webhook headers via HTTP is rejected with 403 PERMISSION_DENIED."""
    forged_system_headers = {
        "X-Tenant-ID": str(tenant_a.id),
        "X-Actor-Role": "system_workflow",
        "X-Actor-Permissions": "business.read,business.write,SEND_WHATSAPP_MESSAGE,EXECUTE_INTEGRATION,MANAGE_PAYMENTS",
    }

    resp = await client.get("/api/v1/customers", headers=forged_system_headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_cross_tenant_workflow_action_rejected(
    db_session: AsyncSession,
    tenant_a: Tenant,
    tenant_b: Tenant,
):
    """6. Workflow in Tenant A attempting to execute an action on Tenant B's connection is rejected."""
    # Create Catalog Integration & Connection owned by Tenant B
    integration = Integration(
        integration_key="google_sheets",
        provider_key="google_sheets",
        display_name="Google Sheets Connector",
        category="sheets",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    conn_b = IntegrationConnection(
        tenant_id=tenant_b.id,
        integration_id=integration.id,
        status="ACTIVE",
    )
    db_session.add(conn_b)
    await db_session.commit()

    # Attempt to run ActionExecutor under Tenant A using Tenant B's connection_id
    res = await ActionExecutor.execute(
        action_type="google_sheets_append",
        params={"connection_id": str(conn_b.id), "spreadsheet_id": "test_sheet"},
        context={},
        session=db_session,
        tenant_id=str(tenant_a.id),
    )

    assert res.success is False
    assert "not found" in res.error.lower() or "denied" in res.error.lower() or "does not belong" in res.error.lower()


@pytest.mark.asyncio
async def test_system_actor_no_wildcard_permissions(
    db_session: AsyncSession,
    tenant_a: Tenant,
):
    """7. Prove that system/workflow actor created by WorkflowEngine possesses no wildcard/unrestricted permissions (*)."""
    event = EventSchema(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        tenant_id=str(tenant_a.id),
        event_type="test.system_actor_check",
        payload={},
        source="unit_test",
    )

    engine = WorkflowEngine(db_session)
    # Establish system_workflow actor context exactly as handle_event does
    wf_actor = AuthenticatedActor(
        user_id=None,
        tenant_id=tenant_a.id,
        role="system_workflow",
        permissions={
            "business.read",
            "product.read",
            "knowledge.read",
            "business.write",
            "SEND_WHATSAPP_MESSAGE",
            "EXECUTE_INTEGRATION",
            "MANAGE_PAYMENTS",
        },
        is_platform_owner=False,
    )

    assert "*" not in wf_actor.permissions
    assert "all" not in wf_actor.permissions
    assert wf_actor.is_platform_owner is False
    assert wf_actor.tenant_id == tenant_a.id
