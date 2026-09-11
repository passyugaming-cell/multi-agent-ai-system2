import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context
from app.core.auth import resolve_actor_permissions
from app.core.exceptions import AppException
from app.agents.base.registry import agent_registry
from app.agents.base.schemas import AgentRequest, AgentRequestStatus, ToolRequest
from app.core.workflows.actions import ActionExecutor
from app.analytics.services import AnalyticsService
from app.billing.subscription import SubscriptionService
from app.billing.plans import PlanService


@pytest.mark.asyncio
async def test_security_boundary_1_tenant_user_direct_owner_ai_api_denied(async_client: AsyncClient, tenant_a):
    """TEST 1: Tenant user directly trying to invoke Owner AI endpoints -> DENIED (HTTP 403)."""
    # 1. Tenant user with role 'admin' or 'member' (non-owner)
    non_owner_headers = {
        "X-Tenant-ID": str(tenant_a.id),
        "X-Actor-Role": "admin",
        "X-Authenticated-Actor-ID": str(uuid.uuid4()),
        "X-Authenticated-Tenant-ID": str(tenant_a.id),
    }

    # 1a. POST /api/v1/owner-ai/run
    res_run = await async_client.post(
        "/api/v1/owner-ai/run",
        json={"objective": "Unauthorized strategy check"},
        headers=non_owner_headers,
    )
    assert res_run.status_code == 403
    assert res_run.json()["error"]["code"] in ("PERMISSION_DENIED", "FORBIDDEN")

    # 1b. GET /api/v1/owner-ai/brief/daily
    res_brief = await async_client.get(
        "/api/v1/owner-ai/brief/daily",
        headers=non_owner_headers,
    )
    assert res_brief.status_code == 403

    # 1c. GET /api/v1/owner-ai/review/weekly
    res_review = await async_client.get(
        "/api/v1/owner-ai/review/weekly",
        headers=non_owner_headers,
    )
    assert res_review.status_code == 403


@pytest.mark.asyncio
async def test_security_boundary_2_tenant_ai_delegation_to_owner_ai_denied(db_session: AsyncSession, tenant_a):
    """TEST 2: Tenant AI attempting to delegate a task to Owner AI -> DENIED (BLOCKED)."""
    # A specialist Tenant AI agent (e.g. ai_sales) tries to delegate to owner_ai
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
async def test_security_boundary_3_tenant_user_owner_agent_and_workflow_denied(async_client: AsyncClient, db_session: AsyncSession, tenant_a):
    """TEST 3: Tenant user invoking Owner-only agent via endpoint or workflow -> DENIED."""
    # 3a. Direct API call to /api/v1/agents/owner_ai/run as non-owner actor
    non_owner_headers = {
        "X-Tenant-ID": str(tenant_a.id),
        "X-Actor-Role": "member",
        "X-Authenticated-Actor-ID": str(uuid.uuid4()),
        "X-Authenticated-Tenant-ID": str(tenant_a.id),
    }

    res_agent = await async_client.post(
        "/api/v1/agents/owner_ai/run",
        json={
            "tenant_id": str(tenant_a.id),
            "target_agent": "owner_ai",
            "task_type": "strategic_analysis",
            "objective": "Unauthorized run of owner_ai",
        },
        headers=non_owner_headers,
    )
    assert res_agent.status_code == 403

    # 3b. Workflow engine executing action call_agent targeting owner_ai
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
async def test_security_boundary_4_cross_tenant_access_denied(async_client: AsyncClient, db_session: AsyncSession, tenant_a, tenant_b):
    """TEST 4: Tenant attempting to access cross-tenant data via Owner capability -> DENIED."""
    # Actor Context is bound to Tenant A
    actor_a = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.read", "business.write"},
    )
    token = set_actor_context(actor_a)

    try:
        # 4a. Cross-tenant permission check when requesting Tenant B header under Tenant A actor context raises FORBIDDEN_CROSS_TENANT_ACCESS
        with pytest.raises(AppException) as exc_info:
            # resolve_actor_permissions checks get_tenant_context() against actor.tenant_id
            from app.core.context import set_tenant_context, reset_tenant_context
            tenant_b_tok = set_tenant_context(tenant_b.id)
            try:
                resolve_actor_permissions()
            finally:
                reset_tenant_context(tenant_b_tok)

        assert exc_info.value.code == "FORBIDDEN_CROSS_TENANT_ACCESS"
        assert exc_info.value.status_code == 403

        # 4b. Agent request targeting Tenant B with Tenant A actor context is blocked or fails cross-tenant validation
        agent_req_b = AgentRequest(
            tenant_id=tenant_b.id,
            source="owner_api",
            source_agent="owner_ai",
            target_agent="owner_ai",
            task_type="cross_tenant_attempt",
            objective="Access Tenant B facts",
        )
        # Agent delegation / context assembly validates actor tenant binding
        from app.core.context_assembly import ContextAssemblyService, ContextAssemblyRequest
        assembly_srv = ContextAssemblyService(db_session)
        with pytest.raises(AppException) as assembly_exc:
            await assembly_srv.assemble_context(
                ContextAssemblyRequest(
                    tenant_id=tenant_b.id,
                    agent_name="owner_ai",
                    task_type="cross_tenant_attempt",
                )
            )
        assert assembly_exc.value.code == "FORBIDDEN_CROSS_TENANT_ACCESS"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_security_boundary_6_tenant_owner_without_entitlement_denied(async_client: AsyncClient, db_session: AsyncSession, tenant_a):
    """Proves that a Tenant Owner on a plan without 'owner_ai' entitlement (e.g., Starter/Pro) is DENIED (403 FEATURE_NOT_INCLUDED)."""
    # 1. Ensure tenant_a is on Starter plan (no owner_ai feature)
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    starter_plan = await plan_srv.get_plan_by_code("starter")

    sub_srv = SubscriptionService(db_session)
    sub = await sub_srv.get_subscription_or_none(tenant_a.id)
    if not sub:
        await sub_srv.create_trial_subscription(tenant_a.id)
        sub = await sub_srv.get_subscription_or_none(tenant_a.id)

    sub.plan_id = starter_plan.id
    await db_session.commit()

    # 2. Set Tenant Owner actor context for Tenant A
    owner_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.read", "business.write"},
    )
    token = set_actor_context(owner_actor)

    try:
        res = await async_client.post(
            "/api/v1/owner-ai/run",
            json={"objective": "Try running owner_ai on Starter plan"},
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FEATURE_NOT_INCLUDED"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_security_boundary_5_owner_internal_flow_allowed(async_client: AsyncClient, db_session: AsyncSession, tenant_a):
    """TEST 5: Internal Owner flow / Human Owner actor on a Business plan accessing Owner AI -> ALLOWED."""
    # 1. Set tenant_a to Business plan which contains the 'owner_ai' feature entitlement
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()
    biz_plan = await plan_srv.get_plan_by_code("business")

    sub_srv = SubscriptionService(db_session)
    sub = await sub_srv.get_subscription_or_none(tenant_a.id)
    if not sub:
        await sub_srv.create_trial_subscription(tenant_a.id)
        sub = await sub_srv.get_subscription_or_none(tenant_a.id)

    sub.plan_id = biz_plan.id
    await db_session.commit()

    # Set legitimate Owner actor context
    owner_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.read", "business.write"},
    )
    token = set_actor_context(owner_actor)

    try:
        # 5a. Direct execution of owner_ai via registry with source="owner_api" and owner actor context
        owner_agent = agent_registry.get_agent("owner_ai")
        req = AgentRequest(
            tenant_id=tenant_a.id,
            source="owner_api",
            source_agent="owner_ai",
            target_agent="owner_ai",
            task_type="owner_health_check",
            objective="Evaluate business status",
        )

        res = await owner_agent.run(req, db_session)
        assert res.status != AgentRequestStatus.BLOCKED
        assert res.agent == "owner_ai"
    finally:
        reset_actor_context(token)
