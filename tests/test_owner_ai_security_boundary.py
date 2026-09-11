import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context
from app.core.auth import resolve_actor_permissions
from app.core.exceptions import AppException
from app.agents.base.registry import agent_registry
from app.agents.base.schemas import AgentRequest, AgentRequestStatus
from app.core.workflows.actions import ActionExecutor
from app.billing.subscription import SubscriptionService
from app.billing.plans import PlanService


@pytest.mark.asyncio
async def test_security_boundary_tenant_member_denied(async_client: AsyncClient, tenant_a):
    """Tenant member attempting to call Owner AI -> DENIED (403 PERMISSION_DENIED)."""
    headers = {
        "X-Tenant-ID": str(tenant_a.id),
        "X-Actor-Role": "member",
        "X-Authenticated-Actor-ID": str(uuid.uuid4()),
        "X-Authenticated-Tenant-ID": str(tenant_a.id),
    }

    res = await async_client.post(
        "/api/v1/owner-ai/run",
        json={"objective": "Unauthorized attempt by member"},
        headers=headers,
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_security_boundary_tenant_admin_denied(async_client: AsyncClient, tenant_a):
    """Tenant admin attempting to call Owner AI -> DENIED (403 PERMISSION_DENIED)."""
    headers = {
        "X-Tenant-ID": str(tenant_a.id),
        "X-Actor-Role": "admin",
        "X-Authenticated-Actor-ID": str(uuid.uuid4()),
        "X-Authenticated-Tenant-ID": str(tenant_a.id),
    }

    res = await async_client.post(
        "/api/v1/owner-ai/run",
        json={"objective": "Unauthorized attempt by admin"},
        headers=headers,
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_security_boundary_tenant_owner_with_business_plan_denied(async_client: AsyncClient, db_session: AsyncSession, tenant_a):
    """Tenant Owner on Business Plan with 'owner_ai' entitlement attempting to access Owner AI -> DENIED (403 PERMISSION_DENIED).

    CRITICAL ARCHITECTURAL REQUIREMENT:
    Tenant ownership and Business subscription entitlement MUST NOT transform a tenant owner into a Human Platform Owner.
    """
    # 1. Ensure tenant_a is on Business plan with owner_ai feature entitlement
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    biz_plan = await plan_srv.get_plan_by_code("business")

    sub_srv = SubscriptionService(db_session)
    sub = await sub_srv.get_subscription_or_none(tenant_a.id)
    if not sub:
        await sub_srv.create_trial_subscription(tenant_a.id)
        sub = await sub_srv.get_subscription_or_none(tenant_a.id)

    sub.plan_id = biz_plan.id
    sub.status = "ACTIVE"
    await db_session.commit()

    # 2. Set Tenant Owner context (role="owner", is_platform_owner=False)
    tenant_owner_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.read", "business.write"},
        is_platform_owner=False,  # NOT a Human Platform Owner
    )
    token = set_actor_context(tenant_owner_actor)

    try:
        res = await async_client.post(
            "/api/v1/owner-ai/run",
            json={"objective": "Tenant Owner trying to access platform Owner AI"},
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "PERMISSION_DENIED"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_security_boundary_human_platform_owner_allowed(async_client: AsyncClient, db_session: AsyncSession, tenant_a):
    """Human Platform Owner (is_platform_owner=True) accessing Owner AI -> ALLOWED (200 OK)."""
    platform_owner_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.read", "business.write"},
        is_platform_owner=True,  # Trusted Human Platform Owner
    )
    token = set_actor_context(platform_owner_actor)

    try:
        res = await async_client.post(
            "/api/v1/owner-ai/run",
            json={"objective": "Platform Owner strategic analysis"},
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert res.status_code == 200
        assert "status" in res.json()
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_security_boundary_tenant_ai_delegation_denied(db_session: AsyncSession, tenant_a):
    """Tenant AI attempting to delegate a task to Owner AI -> DENIED (BLOCKED)."""
    req = AgentRequest(
        tenant_id=tenant_a.id,
        source="agent_delegation",
        source_agent="ai_sales",
        target_agent="owner_ai",
        task_type="unauthorized_delegation",
        objective="Analyze tenant financial secrets via owner_ai",
    )

    res = await agent_registry.delegate_task(req, db_session)
    assert res.status == AgentRequestStatus.BLOCKED
    assert "strictly forbidden" in res.error.lower()


@pytest.mark.asyncio
async def test_security_boundary_workflow_execution_denied(db_session: AsyncSession, tenant_a):
    """Workflow engine executing action call_agent targeting owner_ai -> DENIED."""
    wf_res = await ActionExecutor.execute(
        action_type="call_agent",
        params={"agent_name": "owner_ai", "objective": "Run owner_ai from workflow"},
        context={},
        session=db_session,
        tenant_id=str(tenant_a.id),
    )
    assert wf_res.success is False
    assert "strictly forbidden" in wf_res.error.lower()


@pytest.mark.asyncio
async def test_owner_ai_registry_denies_missing_actor(db_session: AsyncSession, tenant_a):
    """REGRESSION TEST: Verify AgentRegistry fail-closed rejection when actor is None for target_agent='owner_ai'."""
    # Ensure no active actor context set (actor = None)
    req = AgentRequest(
        tenant_id=tenant_a.id,
        source="api",
        source_agent=None,
        target_agent="owner_ai",
        task_type="bypass_attempt",
        objective="Attempt owner_ai execution with missing actor context",
    )

    res = await agent_registry.delegate_task(req, db_session)
    assert res.status == AgentRequestStatus.BLOCKED
    assert "human platform owner context" in res.error.lower()


@pytest.mark.asyncio
async def test_security_boundary_cross_tenant_access_denied(async_client: AsyncClient, db_session: AsyncSession, tenant_a, tenant_b):
    """Tenant attempting to access cross-tenant data via Owner capability -> DENIED (403 FORBIDDEN_CROSS_TENANT_ACCESS)."""
    actor_a = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.read", "business.write"},
        is_platform_owner=True,
    )
    token = set_actor_context(actor_a)

    try:
        with pytest.raises(AppException) as exc_info:
            from app.core.context import set_tenant_context, reset_tenant_context
            tenant_b_tok = set_tenant_context(tenant_b.id)
            try:
                resolve_actor_permissions()
            finally:
                reset_tenant_context(tenant_b_tok)

        assert exc_info.value.code == "FORBIDDEN_CROSS_TENANT_ACCESS"
        assert exc_info.value.status_code == 403
    finally:
        reset_actor_context(token)
