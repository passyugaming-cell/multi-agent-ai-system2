import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.factory import register_all_agents
from app.agents.base.registry import agent_registry
from app.agents.base.schemas import AgentRequest, AgentRequestStatus
from app.tenants.repository import TenantRepository
from app.tenants.schemas import TenantCreate
from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context


@pytest.mark.asyncio
async def test_owner_ai_agent_and_orchestrator(db_session: AsyncSession):
    # Register agents
    register_all_agents(agent_registry)

    repo = TenantRepository(db_session)
    tenant = await repo.create(TenantCreate(name="Orchestrator Tenant", slug="orch-tenant"))
    await db_session.commit()

    owner_agent = agent_registry.get_agent("owner_ai")
    assert owner_agent is not None

    # Test orchestration
    req = AgentRequest(
        tenant_id=tenant.id,
        source="api",
        target_agent="owner_ai",
        task_type="investigate_conversion_drop",
        objective="Kenapa performa bisnis bulan ini menurun dan apa yang harus saya lakukan?",
    )

    token = set_actor_context(AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=tenant.id, role="owner", permissions={"business.read", "product.read", "knowledge.read"}))
    try:
        res = await owner_agent.run(req, db_session)
    finally:
        reset_actor_context(token)

    assert res.status in (AgentRequestStatus.COMPLETED, AgentRequestStatus.PARTIAL)
    assert res.agent == "owner_ai"
    assert res.finding is not None
    assert len(res.evidence) > 0
    assert 0.0 <= res.confidence <= 1.0


@pytest.mark.asyncio
async def test_owner_ai_delegation_depth_limit(db_session: AsyncSession):
    register_all_agents(agent_registry)

    repo = TenantRepository(db_session)
    tenant = await repo.create(TenantCreate(name="Depth Tenant", slug="depth-tenant"))
    await db_session.commit()

    owner_agent = agent_registry.get_agent("owner_ai")

    # Exceed delegation depth (>= 3)
    req = AgentRequest(
        tenant_id=tenant.id,
        source="api",
        target_agent="owner_ai",
        task_type="deep_orchestration",
        objective="Exceed max depth",
        delegation_depth=3,
    )

    token = set_actor_context(AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=tenant.id, role="owner", permissions={"business.read", "product.read", "knowledge.read"}))
    try:
        res = await owner_agent.run(req, db_session)
    finally:
        reset_actor_context(token)
    assert res.status == AgentRequestStatus.BLOCKED
    assert "limit exceeded" in res.error.lower()
