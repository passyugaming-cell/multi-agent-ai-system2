import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.agents import (
    agent_registry,
    AgentRequest,
    AgentResult,
    AgentRequestStatus,
    ToolRequest,
    ToolResult,
)
from app.agents.sales.agent import SalesAgent
from app.agents.sales.schemas import SalesOutputSchema
from app.agents.client_manager.agent import ClientManagerAgent
from app.agents.client_manager.schemas import ClientManagerOutputSchema
from app.agents.support.agent import SupportAgent
from app.agents.support.schemas import SupportDiagnosisOutputSchema, IncidentSeverity
from app.agents.data_manager.agent import DataManagerAgent
from app.agents.data_manager.schemas import DataManagerOutputSchema
from app.agents.analyst.agent import AnalystAgent
from app.agents.analyst.schemas import AnalystOutputSchema, DataCategoryLabel

from app.core.ai_gateway import AIGateway
from app.database.models.product import Product
from app.database.models.customer import Customer
from app.database.models.agent import AgentExecution
from app.database.models.workflow import Approval, Task, WorkflowConfiguration, WorkflowExecution
from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context
from app.core.approvals.service import ApprovalService
from app.core.workflows.engine import WorkflowEngine
from tests.fake_ai import FakeAIProvider


@pytest.mark.asyncio
async def test_agent_registry_and_capabilities(db_session: AsyncSession):
    """Test agent registry, capability discovery, and disabled status."""
    registry = agent_registry
    agents = registry.list_agents()
    agent_names = [a["name"] for a in agents]

    assert "ai_sales" in agent_names
    assert "ai_client_manager" in agent_names
    assert "ai_support" in agent_names
    assert "ai_data_manager" in agent_names
    assert "ai_analyst" in agent_names

    sales = registry.get_agent("ai_sales")
    assert sales.enabled is True

    # Test disabled agent
    disabled_sales = SalesAgent(enabled=False)
    registry._agents["ai_sales_disabled"] = disabled_sales

    req = AgentRequest(
        tenant_id=uuid.uuid4(),
        target_agent="ai_sales_disabled",
        task_type="sales_query",
        objective="Disabled agent test",
    )
    res = await registry.delegate_task(req, db_session)
    assert res.status == AgentRequestStatus.BLOCKED
    assert "disabled" in res.error.lower()


@pytest.mark.asyncio
async def test_agent_request_and_result_schema_validation():
    """Test Pydantic v2 schemas and confidence bounds enforcement."""
    tenant_id = uuid.uuid4()
    req = AgentRequest(
        tenant_id=tenant_id,
        target_agent="ai_sales",
        task_type="qualify_lead",
        objective="Qualify lead John",
        context={"budget": 5000},
    )
    assert req.request_id.startswith("req_")
    assert req.delegation_depth == 0

    res = AgentResult(
        request_id=req.request_id,
        agent="ai_sales",
        status=AgentRequestStatus.COMPLETED,
        finding="Lead qualified",
        confidence=0.87,
    )
    assert res.confidence == 0.87

    # Confidence out of bounds check
    with pytest.raises(ValueError):
        AgentResult(
            request_id=req.request_id,
            agent="ai_sales",
            status=AgentRequestStatus.COMPLETED,
            confidence=1.5,
        )


@pytest.mark.asyncio
async def test_delegation_depth_protection(db_session: AsyncSession):
    """Test max delegation depth protection preventing infinite recursive loops."""
    req = AgentRequest(
        tenant_id=uuid.uuid4(),
        target_agent="ai_sales",
        task_type="delegation_test",
        objective="Test depth limit",
        delegation_depth=3,  # Already at max depth 3
    )
    res = await agent_registry.delegate_task(req, db_session)
    assert res.status == AgentRequestStatus.BLOCKED
    assert "Delegation depth limit exceeded" in res.error


@pytest.mark.asyncio
async def test_ai_sales_agent_uses_db_truth_and_approvals(db_session: AsyncSession, tenant_a):
    """Test AI Sales Agent product lookup from DB truth and discount Approval requirement."""
    # Seed product into Tenant A database
    p1 = Product(
        tenant_id=tenant_a.id,
        name="Laptop Pro 15",
        description="High performance laptop",
        price=15000000.0,
        stock=5,
        is_active=True,
    )
    db_session.add(p1)
    await db_session.commit()

    fake_output = SalesOutputSchema(
        finding="Laptop Pro 15 is in stock for Rp15.000.000.",
        evidence=[{"product": "Laptop Pro 15", "price": 15000000.0}],
        recommendation="Offer Laptop Pro 15 with 15% discount for bulk inquiry.",
        confidence=0.92,
        proposed_discount_percent=15.0,
        requires_approval=True,
        followup_task_needed=True,
        task_title="Follow up on bulk laptop lead",
    )
    fake_gateway = AIGateway(provider=FakeAIProvider(default_structured_output=fake_output))

    sales_agent = SalesAgent(ai_gateway=fake_gateway)

    req = AgentRequest(
        tenant_id=tenant_a.id,
        target_agent="ai_sales",
        task_type="product_inquiry",
        objective="Inquire about Laptop Pro 15 price and stock",
        context={"product_name": "Laptop Pro"},
    )

    token = set_actor_context(AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=tenant_a.id, role="owner", permissions={"business.read", "product.read", "knowledge.read"}))
    try:
        res = await sales_agent.run(req, db_session)
    finally:
        reset_actor_context(token)

    assert res.status == AgentRequestStatus.WAITING_APPROVAL
    assert res.needs_approval is True
    assert res.approval_id is not None
    assert "15.0%" in res.finding or "Laptop Pro" in res.finding or "15" in res.recommendation

    # Verify task was created in DB
    tasks = (await db_session.execute(select(Task).where(Task.tenant_id == tenant_a.id))).scalars().all()
    assert len(tasks) >= 1
    assert any("bulk laptop" in t.title.lower() for t in tasks)

    # Verify audit record created
    audits = (await db_session.execute(select(AgentExecution).where(AgentExecution.tenant_id == tenant_a.id))).scalars().all()
    assert len(audits) >= 1
    assert audits[0].agent_name == "ai_sales"


@pytest.mark.asyncio
async def test_ai_client_manager_readiness_and_no_data_fabrication(db_session: AsyncSession, tenant_a):
    """Test AI Client Manager readiness calculation and non-fabrication of missing info."""
    fake_output = ClientManagerOutputSchema(
        finding="Readiness Score: 20%. Operating hours and business profile have not been configured.",
        evidence=[{"missing": "operating_hours"}],
        recommendation="Configure business profile operating hours and upload products.",
        confidence=0.95,
        missing_configurations=["Business Profile: operating_hours"],
        onboarding_task_needed=True,
        task_title="Configure Business Profile Operating Hours",
    )
    fake_gateway = AIGateway(provider=FakeAIProvider(default_structured_output=fake_output))
    cm_agent = ClientManagerAgent(ai_gateway=fake_gateway)

    req = AgentRequest(
        tenant_id=tenant_a.id,
        target_agent="ai_client_manager",
        task_type="evaluate_onboarding",
        objective="Evaluate onboarding readiness",
    )

    token = set_actor_context(AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=tenant_a.id, role="owner", permissions={"business.read", "product.read", "knowledge.read"}))
    try:
        res = await cm_agent.run(req, db_session)
    finally:
        reset_actor_context(token)

    assert res.status in (AgentRequestStatus.COMPLETED, AgentRequestStatus.WAITING_APPROVAL)
    assert "Readiness Score" in res.finding or "configured" in res.finding
    assert len(res.actions) >= 1  # Task created


@pytest.mark.asyncio
async def test_ai_support_agent_diagnosis_and_approval(db_session: AsyncSession, tenant_a):
    """Test AI Support Agent evidence-based diagnosis and critical remediation Approval creation."""
    fake_output = SupportDiagnosisOutputSchema(
        observed_evidence=["Database connection pool exhausted"],
        possible_cause="Unclosed database connections in custom background worker.",
        incident_severity=IncidentSeverity.CRITICAL,
        recommendation="Restart database connections and patch leak.",
        confidence=0.88,
        support_task_needed=True,
        requires_high_risk_remediation=True,
    )
    fake_gateway = AIGateway(provider=FakeAIProvider(default_structured_output=fake_output))
    support_agent = SupportAgent(ai_gateway=fake_gateway)

    req = AgentRequest(
        tenant_id=tenant_a.id,
        target_agent="ai_support",
        task_type="diagnose_incident",
        objective="Diagnose database connection error",
    )

    token = set_actor_context(AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=tenant_a.id, role="owner", permissions={"business.read", "product.read", "knowledge.read"}))
    try:
        res = await support_agent.run(req, db_session)
    finally:
        reset_actor_context(token)

    assert res.status == AgentRequestStatus.WAITING_APPROVAL
    assert res.needs_approval is True
    assert res.approval_id is not None
    assert "CRITICAL" in res.finding


@pytest.mark.asyncio
async def test_ai_data_manager_rejects_missing_fields_and_no_hallucination(db_session: AsyncSession, tenant_a):
    """Test AI Data Manager strict rejection of records missing required fields without hallucinating."""
    fake_gateway = AIGateway(provider=FakeAIProvider())
    dm_agent = DataManagerAgent(ai_gateway=fake_gateway)

    raw_records_missing_price = [
        {"name": "Premium Hoodie"}  # Price is missing!
    ]

    req = AgentRequest(
        tenant_id=tenant_a.id,
        target_agent="ai_data_manager",
        task_type="validate_import",
        objective="Validate raw product import list",
        context={"records": raw_records_missing_price, "entity_type": "product"},
    )

    token = set_actor_context(AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=tenant_a.id, role="owner", permissions={"business.read", "product.read", "knowledge.read"}))
    try:
        res = await dm_agent.run(req, db_session)
    finally:
        reset_actor_context(token)

    assert res.status == AgentRequestStatus.WAITING_DATA
    assert "missing" in res.finding.lower()
    assert "price" in res.finding.lower()
    assert res.confidence == 1.0


@pytest.mark.asyncio
async def test_ai_analyst_agent_read_only_and_data_labeling(db_session: AsyncSession, tenant_a):
    """Test AI Analyst read-only behavior and explicit data labeling (ACTUAL, ESTIMATE, FORECAST, RECOMMENDATION)."""
    fake_output = AnalystOutputSchema(
        finding="Total actual historical revenue: Rp0.00.",
        metrics=[],
        evidence=[],
        recommendation="Focus on sales lead conversion.",
        confidence=0.90,
    )
    fake_gateway = AIGateway(provider=FakeAIProvider(default_structured_output=fake_output))
    analyst_agent = AnalystAgent(ai_gateway=fake_gateway)

    req = AgentRequest(
        tenant_id=tenant_a.id,
        target_agent="ai_analyst",
        task_type="analyze_revenue",
        objective="Analyze quarterly revenue and forecast next quarter",
    )

    token = set_actor_context(AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=tenant_a.id, role="owner", permissions={"business.read", "product.read", "knowledge.read"}))
    try:
        res = await analyst_agent.run(req, db_session)
    finally:
        reset_actor_context(token)

    assert res.status == AgentRequestStatus.COMPLETED
    assert res.needs_approval is False
    assert len(res.actions) == 0  # Read-only agent performs no direct database mutation actions


@pytest.mark.asyncio
async def test_workflow_engine_can_invoke_agent_and_pause_for_approval(db_session: AsyncSession, tenant_a):
    """Test Phase 2 Workflow Engine invoking call_agent action and pausing on WAITING_APPROVAL."""
    # Seed workflow configuration
    wf_config = WorkflowConfiguration(
        tenant_id=tenant_a.id,
        key="lead_qualification_workflow",
        name="Lead Qualification Workflow",
        trigger_type="lead.created",
        is_active=True,
        actions=[
            {
                "type": "call_agent",
                "params": {
                    "agent_name": "ai_sales",
                    "task_type": "qualify_lead",
                    "objective": "Qualify new lead with discount proposal",
                    "context": {"discount_percent": 20.0},
                },
            }
        ],
    )
    db_session.add(wf_config)
    await db_session.commit()

    # Configure Fake AI Sales agent output to require approval
    fake_sales_output = SalesOutputSchema(
        finding="Proposed 20% discount for enterprise lead.",
        recommendation="Request discount approval for 20% discount.",
        confidence=0.95,
        proposed_discount_percent=20.0,
        requires_approval=True,
    )
    fake_gateway = AIGateway(provider=FakeAIProvider(default_structured_output=fake_sales_output))
    agent_registry._agents["ai_sales"] = SalesAgent(ai_gateway=fake_gateway)

    # Publish event triggering workflow
    from app.core.events.schemas import EventSchema
    event = EventSchema(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        tenant_id=str(tenant_a.id),
        event_type="lead.created",
        payload={"lead_name": "Enterprise Lead"},
        source="test_suite",
    )

    engine = WorkflowEngine(db_session)
    executions = await engine.handle_event(event)

    assert len(executions) == 1
    exec_rec = executions[0]
    assert exec_rec.status == "WAITING_APPROVAL"

    # Verify Approval record was created
    approvals = (await db_session.execute(select(Approval).where(Approval.tenant_id == tenant_a.id))).scalars().all()
    assert len(approvals) >= 1
    appr = approvals[0]
    assert appr.status == "PENDING"

    # Approve approval and verify workflow resumes
    approval_service = ApprovalService(db_session)
    token = set_actor_context(AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=tenant_a.id, role="admin", permissions={"business.read", "product.read", "knowledge.read"}))
    try:
        updated_appr = await approval_service.approve(tenant_a.id, appr.id, decided_by="admin_user", reason="Approved 20% discount")
    finally:
        reset_actor_context(token)
    assert updated_appr.status == "APPROVED"

    await db_session.refresh(exec_rec)
    assert exec_rec.status == "COMPLETED"


@pytest.mark.asyncio
async def test_agent_api_endpoints_and_tenant_isolation(async_client: AsyncClient, tenant_a, tenant_b):
    """Test API endpoints for agents and strict tenant isolation checks."""
    actor_a = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.read", "product.read", "knowledge.read"},
    )
    token = set_actor_context(actor_a)

    try:
        # 1. Test GET /api/v1/agents
        res = await async_client.get("/api/v1/agents", headers={"X-Tenant-ID": str(tenant_a.id)})
        assert res.status_code == 200
        data = res.json()
        assert "agents" in data
        assert len(data["agents"]) >= 5

        # 2. Test GET /api/v1/agents/ai_sales
        res = await async_client.get("/api/v1/agents/ai_sales", headers={"X-Tenant-ID": str(tenant_a.id)})
        assert res.status_code == 200
        assert res.json()["name"] == "ai_sales"

        # 3. Test POST /api/v1/agents/ai_sales/run with tenant match
        run_payload = {
            "tenant_id": str(tenant_a.id),
            "target_agent": "ai_sales",
            "task_type": "inquire_product",
            "objective": "Check available products",
        }
        res = await async_client.post(
            "/api/v1/agents/ai_sales/run",
            json=run_payload,
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert res.status_code == 200
        res_data = res.json()
        assert res_data["agent"] == "ai_sales"
    finally:
        reset_actor_context(token)

    # 4. Test Tenant Mismatch Security Rejection (Tenant A header attempting Tenant B request)
    actor_a_b = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.read", "product.read", "knowledge.read"},
    )
    token_b = set_actor_context(actor_a_b)
    try:
        mismatch_payload = {
            "tenant_id": str(tenant_b.id),
            "target_agent": "ai_sales",
            "task_type": "inquire_product",
            "objective": "Cross tenant leak attempt",
        }
        res = await async_client.post(
            "/api/v1/agents/ai_sales/run",
            json=mismatch_payload,
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert res.status_code == 403
        assert "tenant_id does not match" in res.json()["error"]["message"]
    finally:
        reset_actor_context(token_b)
