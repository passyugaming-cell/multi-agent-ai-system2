import uuid
from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context
from app.core.context_assembly import (
    ContextAssemblyService,
    ContextAssemblyRequest,
)
from app.core.exceptions import AppException
from app.database.models import Tenant, Product, BusinessProfile, KnowledgeItem, Conversation, Message, Customer
from app.database.models.workflow import Task
from app.memory.service import MemoryService
from app.memory.schemas import MemoryCreateSchema, MemoryScope, MemoryType, MemoryImportance
from app.tenants.business_service import BusinessDataService
from app.schemas.domain import KnowledgeItemCreate


@pytest_asyncio.fixture
async def setup_closure_tenants(test_engine):
    """Creates isolated test tenants for closure verification."""
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        t1 = Tenant(
            name="Closure Tenant Alpha",
            slug=f"closure-alpha-{uuid.uuid4().hex[:6]}",
            is_active=True,
            lifecycle_state="ACTIVE",
        )
        t2 = Tenant(
            name="Closure Tenant Beta",
            slug=f"closure-beta-{uuid.uuid4().hex[:6]}",
            is_active=True,
            lifecycle_state="ACTIVE",
        )
        session.add_all([t1, t2])
        await session.commit()

        yield t1.id, t2.id


@pytest.mark.asyncio
async def test_owner_ai_platform_owner_boundary_closure(test_engine, setup_closure_tenants):
    """Verifies strict security boundary: Human Platform Owner can access Owner AI context, but tenant actors CANNOT."""
    t1_id, t2_id = setup_closure_tenants
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        service = ContextAssemblyService(session)
        req_owner = ContextAssemblyRequest(tenant_id=t1_id, agent_name="owner_ai")

        # 1. Human Platform Owner (is_platform_owner=True) -> ALLOWED
        platform_actor = AuthenticatedActor(
            user_id=uuid.uuid4(),
            tenant_id=t1_id,
            role="owner",
            permissions={"*"},
            is_platform_owner=True,
        )
        token = set_actor_context(platform_actor)
        try:
            ctx = await service.assemble_context(req_owner)
            assert ctx.tenant_id == t1_id
            assert ctx.agent_name == "owner_ai"
        finally:
            reset_actor_context(token)

        # 2. Tenant Owner (role="owner", is_platform_owner=False) -> REJECTED (403 PERMISSION_DENIED)
        tenant_owner_actor = AuthenticatedActor(
            user_id=uuid.uuid4(),
            tenant_id=t1_id,
            role="owner",
            permissions={"business.read", "business.write", "*"},
            is_platform_owner=False,
        )
        token = set_actor_context(tenant_owner_actor)
        try:
            with pytest.raises(AppException) as exc_info:
                await service.assemble_context(req_owner)
            assert exc_info.value.code == "PERMISSION_DENIED"
            assert "Only Human Platform Owner" in exc_info.value.message
        finally:
            reset_actor_context(token)

        # 3. Tenant Admin -> REJECTED
        tenant_admin_actor = AuthenticatedActor(
            user_id=uuid.uuid4(),
            tenant_id=t1_id,
            role="admin",
            permissions={"business.read"},
            is_platform_owner=False,
        )
        token = set_actor_context(tenant_admin_actor)
        try:
            with pytest.raises(AppException) as exc_info:
                await service.assemble_context(req_owner)
            assert exc_info.value.code == "PERMISSION_DENIED"
        finally:
            reset_actor_context(token)

        # 4. Tenant User -> REJECTED
        tenant_user_actor = AuthenticatedActor(
            user_id=uuid.uuid4(),
            tenant_id=t1_id,
            role="user",
            permissions=set(),
            is_platform_owner=False,
        )
        token = set_actor_context(tenant_user_actor)
        try:
            with pytest.raises(AppException) as exc_info:
                await service.assemble_context(req_owner)
            assert exc_info.value.code == "PERMISSION_DENIED"
        finally:
            reset_actor_context(token)

        # 5. Missing Actor -> REJECTED
        with pytest.raises(AppException) as exc_info:
            await service.assemble_context(req_owner)
        assert exc_info.value.code == "PERMISSION_DENIED"

        # 6. Privilege escalation via requested_categories -> REJECTED / FILTERED
        # Tenant sales agent requesting Owner AI categories (analytics, tasks) without permissions
        req_sales_escalation = ContextAssemblyRequest(
            tenant_id=t1_id,
            agent_name="ai_sales",
            include_categories=["analytics", "tasks", "products"],
        )
        restricted_sales_actor = AuthenticatedActor(
            user_id=uuid.uuid4(),
            tenant_id=t1_id,
            role="user",
            permissions={"products.read"},
            is_platform_owner=False,
        )
        token = set_actor_context(restricted_sales_actor)
        try:
            ctx_sales = await service.assemble_context(req_sales_escalation)
            # "analytics" and "tasks" must be filtered out because agent policy & actor perms prohibit them
            assert "analytics" not in ctx_sales.assembled_categories
            assert "tasks" not in ctx_sales.assembled_categories
            assert ctx_sales.assembled_categories == ["products"]
        finally:
            reset_actor_context(token)


@pytest.mark.asyncio
async def test_relevance_and_empty_result_semantics_closure(test_engine, setup_closure_tenants):
    """Verifies that non-matching product/knowledge search queries return EMPTY results instead of arbitrary records."""
    t1_id, t2_id = setup_closure_tenants
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        # Create products for Tenant 1
        p1 = Product(tenant_id=t1_id, name="Leather Jacket", sku="JKT-LEATHER", price=Decimal("750000.00"), stock=5, is_active=True)
        p2 = Product(tenant_id=t1_id, name="Denim Pants", sku="PNT-DENIM", price=Decimal("350000.00"), stock=12, is_active=True)
        session.add_all([p1, p2])

        # Create product for Tenant 2 (Tenant isolation test)
        p_t2 = Product(tenant_id=t2_id, name="Tenant 2 Secret Product", sku="T2-SECRET", price=Decimal("999999.00"), stock=1, is_active=True)
        session.add(p_t2)

        # Create approved knowledge item
        biz_service = BusinessDataService(session)
        k1 = await biz_service.create_knowledge_item(
            tenant_id=t1_id,
            payload=KnowledgeItemCreate(
                title="Shipping Policy",
                category_key="shipping",
                content="We ship via JNE and J&T express nationwide.",
            ),
            allow_internal=True,
        )
        await biz_service.approve_knowledge_item(tenant_id=t1_id, item_id=k1.id, allow_internal=True)
        await session.commit()

        actor_t1 = AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=t1_id, role="owner", permissions={"business.read"})
        token = set_actor_context(actor_t1)
        try:
            service = ContextAssemblyService(session)

            # 1. Matching Product Query -> Returns relevant product only
            req_match = ContextAssemblyRequest(tenant_id=t1_id, agent_name="ai_sales", query_text="Leather Jacket")
            ctx_match = await service.assemble_context(req_match)
            prods = ctx_match.facts.get("product_catalog", [])
            assert len(prods) == 1
            assert prods[0]["sku"] == "JKT-LEATHER"

            # 2. Non-matching Product Query -> Returns EMPTY result [] (NOT arbitrary first 10 products!)
            req_no_match = ContextAssemblyRequest(tenant_id=t1_id, agent_name="ai_sales", query_text="NonExistentLaptop999")
            ctx_no_match = await service.assemble_context(req_no_match)
            prods_empty = ctx_no_match.facts.get("product_catalog", [])
            assert prods_empty == []  # Empty result semantics!

            # 3. Non-matching Knowledge Query -> Returns EMPTY result []
            req_know_no_match = ContextAssemblyRequest(tenant_id=t1_id, agent_name="ai_sales", query_text="UnrelatedQuantumPhysics")
            ctx_know_empty = await service.assemble_context(req_know_no_match)
            assert ctx_know_empty.knowledge == []

            # 4. Cross-Tenant Product Isolation -> Tenant 1 NEVER receives Tenant 2 product
            req_all = ContextAssemblyRequest(tenant_id=t1_id, agent_name="ai_sales")
            ctx_all = await service.assemble_context(req_all)
            all_prods = ctx_all.facts.get("product_catalog", [])
            assert not any(p["sku"] == "T2-SECRET" for p in all_prods)
        finally:
            reset_actor_context(token)


@pytest.mark.asyncio
async def test_deterministic_context_budget_limit_closure(test_engine, setup_closure_tenants):
    """Verifies max context byte budget limit and retention of authoritative DB facts when trimming context."""
    t1_id, _ = setup_closure_tenants
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        # Create authoritative DB product truth
        p = Product(tenant_id=t1_id, name="Authoritative Product", sku="AUTH-PROD-01", price=Decimal("500000.00"), stock=100, is_active=True)
        session.add(p)

        # Create business profile
        bp_service = BusinessDataService(session)
        await bp_service.create_or_update_business_profile(
            tenant_id=t1_id,
            payload=type("BP", (), {
                "model_dump": lambda self, exclude_unset=True: {
                    "business_name": "Authoritative Business Corp",
                    "description": "Enterprise solutions provider",
                }
            })(),
            allow_internal=True,
        )

        # Populate large memory entries to exceed context budget
        mem_service = MemoryService(session)
        for i in range(15):
            await mem_service.save_memory_or_propose(
                scope=MemoryScope.BUSINESS,
                tenant_id=t1_id,
                create_data=MemoryCreateSchema(
                    key=f"large_mem_{i}",
                    memory_type=MemoryType.FACT,
                    content={"data": "x" * 1500},
                    source="unit_test",
                ),
                source_agent="owner_ai",
            )
        await session.commit()

        actor_t1 = AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=t1_id, role="owner", permissions={"business.read"})
        token = set_actor_context(actor_t1)
        try:
            service = ContextAssemblyService(session)
            req = ContextAssemblyRequest(tenant_id=t1_id, agent_name="ai_sales")
            ctx = await service.assemble_context(req)

            # Authoritative System DB Facts MUST survive trimming
            assert ctx.facts.get("product_catalog") is not None
            assert len(ctx.facts["product_catalog"]) > 0
            assert ctx.facts["product_catalog"][0]["sku"] == "AUTH-PROD-01"
            assert ctx.business_profile["business_name"] == "Authoritative Business Corp"

            # Low-priority memory must be trimmed safely down within budget
            assert len(ctx.business_memory) <= 10
        finally:
            reset_actor_context(token)


@pytest.mark.asyncio
async def test_conversation_summary_and_task_context_closure(test_engine, setup_closure_tenants):
    """Verifies assembly of conversation summary and task/workflow context."""
    t1_id, _ = setup_closure_tenants
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        cust = Customer(tenant_id=t1_id, name="John Doe", phone="+6281111222")
        session.add(cust)
        await session.flush()

        conv = Conversation(
            tenant_id=t1_id,
            customer_id=cust.id,
            status="OPEN",
            summary="Customer inquired about bulk order discounts and fast delivery options.",
        )
        session.add(conv)
        await session.flush()

        msg = Message(tenant_id=t1_id, conversation_id=conv.id, direction="INBOUND", text="Is there express shipping?")
        session.add(msg)

        # Create active task
        task = Task(
            tenant_id=t1_id,
            title="Follow up bulk quote",
            description="Prepare quote for 100 units",
            task_type="sales_quote",
            status="IN_PROGRESS",
            priority="HIGH",
            assigned_agent="ai_sales",
        )
        session.add(task)
        await session.commit()

        platform_actor = AuthenticatedActor(
            user_id=uuid.uuid4(),
            tenant_id=t1_id,
            role="owner",
            permissions={"*"},
            is_platform_owner=True,
        )
        token = set_actor_context(platform_actor)
        try:
            service = ContextAssemblyService(session)
            # Test Conversation Summary with sales agent (has conversation category)
            req_sales = ContextAssemblyRequest(
                tenant_id=t1_id,
                agent_name="ai_sales",
                customer_id=cust.id,
                conversation_id=conv.id,
            )
            ctx_sales = await service.assemble_context(req_sales)
            assert ctx_sales.conversation_summary == "Customer inquired about bulk order discounts and fast delivery options."

            # Test Task Context with owner_ai agent (has tasks category)
            req_owner = ContextAssemblyRequest(
                tenant_id=t1_id,
                agent_name="owner_ai",
                customer_id=cust.id,
                conversation_id=conv.id,
            )
            ctx = await service.assemble_context(req_owner)

            # Task Context Assembly
            assert ctx.task_context is not None
            assert ctx.task_context["active_tasks_count"] >= 1
            assert ctx.task_context["tasks"][0]["title"] == "Follow up bulk quote"
            ctx.conversation_summary = ctx_sales.conversation_summary

            # 3. Prompt Formatting verification
            formatted = ContextAssemblyService.format_prompt(
                assembled=ctx,
                user_message="Status update request",
            )
            assert "[CONVERSATION SUMMARY]" in formatted.full_prompt
            assert "bulk order discounts" in formatted.full_prompt
            assert "[TASK / WORKFLOW STATE]" in formatted.full_prompt
            assert "Follow up bulk quote" in formatted.full_prompt
        finally:
            reset_actor_context(token)


@pytest.mark.asyncio
async def test_memory_governance_metadata_preservation_closure(test_engine, setup_closure_tenants):
    """Verifies safe exposure of memory governance metadata (confidence, source, status, version)."""
    t1_id, _ = setup_closure_tenants
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        mem_service = MemoryService(session)
        await mem_service.save_memory_or_propose(
            scope=MemoryScope.BUSINESS,
            tenant_id=t1_id,
            create_data=MemoryCreateSchema(
                key="governance_policy_01",
                memory_type=MemoryType.POLICY,
                content={"text": "Standard return window is 14 days"},
                source="operator_manual",
                confidence=0.95,
                importance=MemoryImportance.HIGH,
            ),
            source_agent="owner_ai",
        )
        await session.commit()

        actor_t1 = AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=t1_id, role="owner", permissions={"business.read"})
        token = set_actor_context(actor_t1)
        try:
            service = ContextAssemblyService(session)
            req = ContextAssemblyRequest(tenant_id=t1_id, agent_name="ai_sales", query_text="return window policy")
            ctx = await service.assemble_context(req)

            mem_item = next(m for m in ctx.business_memory if m["key"] == "governance_policy_01")
            assert mem_item["confidence"] == 0.95
            assert mem_item["source"] == "operator_manual"
            assert mem_item["status"] == "ACTIVE"
            assert mem_item["importance"] == "HIGH"
        finally:
            reset_actor_context(token)
