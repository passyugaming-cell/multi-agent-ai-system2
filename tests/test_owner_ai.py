import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.agents.factory import register_all_agents
from app.agents.base.registry import agent_registry
from app.agents.base.schemas import AgentRequest, AgentRequestStatus
from app.agents.owner_ai import (
    OwnerAIAgent,
    OwnerAIOrchestrator,
    BusinessHealthCalculator,
    ClientHealthCalculator,
    ReportGenerator,
    RecommendationService,
    ApprovalRouter,
)
from app.agents.owner_ai.schemas import RecommendationStatus
from app.memory.service import MemoryService
from app.memory.schemas import MemoryCreateSchema, MemoryType, MemoryScope
from app.database.models.order import Order
from app.database.models.customer import Customer
from app.database.models.workflow import Task, Approval
from app.database.models.owner_ai import OwnerAIExecution, Recommendation
from app.tenants.repository import TenantRepository
from app.tenants.schemas import TenantCreate
from app.core.exceptions import AppError


@pytest.mark.asyncio
async def test_end_to_end_acceptance_scenario(db_session: AsyncSession):
    """SCENARIO: Human Owner asks: 'Kenapa performa bisnis bulan ini menurun dan apa yang harus saya lakukan?'"""
    register_all_agents(agent_registry)

    repo = TenantRepository(db_session)
    tenant = await repo.create(TenantCreate(name="E2E Owner Tenant", slug="e2e-owner-tenant"))
    await db_session.commit()

    # Seed DB data: Customer & Orders
    cust = Customer(tenant_id=tenant.id, name="E2E Customer", email="e2e@example.com")
    db_session.add(cust)
    await db_session.commit()
    await db_session.refresh(cust)

    order1 = Order(tenant_id=tenant.id, customer_id=cust.id, status="COMPLETED", subtotal=500000, total=500000)
    order2 = Order(tenant_id=tenant.id, customer_id=cust.id, status="CANCELLED", subtotal=150000, total=150000)
    db_session.add_all([order1, order2])
    await db_session.commit()

    # Create an approval-requiring pending action in Phase 2 ApprovalSystem
    appr_service = ApprovalRouter(db_session)
    appr_record = Approval(
        tenant_id=tenant.id,
        requested_by="ai_sales",
        action_type="change_official_price",
        target="Laptop Pro",
        reason="Strategic price reduction recommendation",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr_record)
    await db_session.commit()

    # Human Owner invokes Owner AI
    owner_agent = agent_registry.get_agent("owner_ai")
    req = AgentRequest(
        tenant_id=tenant.id,
        source="api",
        target_agent="owner_ai",
        task_type="strategic_investigation",
        objective="Kenapa performa bisnis bulan ini menurun dan apa yang harus saya lakukan?",
    )

    res = await owner_agent.run(req, db_session)

    # Assertions for E2E Flow
    assert res.status in (AgentRequestStatus.COMPLETED, AgentRequestStatus.PARTIAL)
    assert res.agent == "owner_ai"

    # 1. WHAT HAPPENED & WHY IT MAY HAVE HAPPENED
    assert res.finding is not None
    assert "Business Health Score" in res.evidence[0] or "Health Score" in str(res.evidence)

    # 2. WHAT THE SYSTEM RECOMMENDS
    assert res.recommendation is not None

    # 3. WHAT REQUIRES HUMAN DECISION & Approval Routing
    pending_approvals = await appr_service.get_pending_approvals_with_explanations(tenant.id)
    assert len(pending_approvals) >= 1
    assert any(a["action_type"] == "change_official_price" for a in pending_approvals)
    assert any(a["owner_action_required"] is True for a in pending_approvals)

    # Owner AI MUST NOT automatically approve high-risk action
    with pytest.raises(AppError):
        appr_service.validate_owner_authority(is_high_risk=True, action_type="change_official_price")

    # Tasks created in Task System for specialists
    tasks = (await db_session.execute(select(Task).where(Task.tenant_id == tenant.id))).scalars().all()
    assert len(tasks) >= 1

    # Executions audit record created
    executions = (await db_session.execute(select(OwnerAIExecution).where(OwnerAIExecution.tenant_id == tenant.id))).scalars().all()
    assert len(executions) >= 1
    assert executions[0].objective == req.objective


@pytest.mark.asyncio
async def test_owner_ai_tenant_isolation(db_session: AsyncSession):
    register_all_agents(agent_registry)

    repo = TenantRepository(db_session)
    tenant_a = await repo.create(TenantCreate(name="Iso Tenant A", slug="iso-tenant-a"))
    tenant_b = await repo.create(TenantCreate(name="Iso Tenant B", slug="iso-tenant-b"))
    await db_session.commit()

    mem_service = MemoryService(db_session)

    # Save memory for Tenant A
    await mem_service.save_memory_or_propose(
        scope=MemoryScope.CLIENT,
        tenant_id=tenant_a.id,
        create_data=MemoryCreateSchema(
            memory_type=MemoryType.PREFERENCE,
            key="confidential_strategy",
            content={"strategy": "Project Alpha"},
            source="owner",
        ),
        source_agent="owner_ai",
    )

    # Retrieve context for Tenant B - must not contain Tenant A's memory
    ctx_b = await mem_service.get_relevant_context(tenant_b.id, objective="confidential_strategy")
    keys_b = [m.key for m in ctx_b.client_memories]
    assert "confidential_strategy" not in keys_b


@pytest.mark.asyncio
async def test_owner_ai_cannot_self_approve(db_session: AsyncSession):
    repo = TenantRepository(db_session)
    tenant = await repo.create(TenantCreate(name="Self Approve Tenant", slug="no-self-approve"))
    await db_session.commit()

    router = ApprovalRouter(db_session)

    # High-risk action self-approval check
    with pytest.raises(AppError) as exc:
        router.validate_owner_authority(is_high_risk=True, action_type="issue_refund")
    assert "forbidden" in str(exc.value).lower()
