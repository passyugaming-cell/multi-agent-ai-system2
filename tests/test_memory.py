import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.service import MemoryService
from app.memory.schemas import (
    MemoryType,
    MemoryScope,
    MemoryCreateSchema,
    MemoryImportance,
)
from app.database.models.tenant import Tenant
from app.tenants.repository import TenantRepository
from app.tenants.schemas import TenantCreate


@pytest.mark.asyncio
async def test_memory_creation_and_tenant_isolation(db_session: AsyncSession):
    repo = TenantRepository(db_session)
    tenant_a = await repo.create(TenantCreate(name="Mem Tenant A", slug="mem-tenant-a"))
    tenant_b = await repo.create(TenantCreate(name="Mem Tenant B", slug="mem-tenant-b"))
    await db_session.commit()

    service = MemoryService(db_session)

    # 1. Add Client Memory for Tenant A
    create_a = MemoryCreateSchema(
        memory_type=MemoryType.PREFERENCE,
        key="preferred_language",
        content={"language": "Indonesian"},
        source="client_manager",
    )
    item_a, prop_a = await service.save_memory_or_propose(
        scope=MemoryScope.CLIENT,
        tenant_id=tenant_a.id,
        create_data=create_a,
        source_agent="ai_client_manager",
    )
    assert item_a is not None
    assert prop_a is None
    assert item_a.key == "preferred_language"

    # 2. Add Client Memory for Tenant B
    create_b = MemoryCreateSchema(
        memory_type=MemoryType.PREFERENCE,
        key="preferred_language",
        content={"language": "English"},
        source="client_manager",
    )
    item_b, prop_b = await service.save_memory_or_propose(
        scope=MemoryScope.CLIENT,
        tenant_id=tenant_b.id,
        create_data=create_b,
        source_agent="ai_client_manager",
    )
    assert item_b is not None

    # 3. Retrieve context for Tenant A and verify Tenant B's data is isolated
    context_a = await service.get_relevant_context(
        tenant_id=tenant_a.id,
        objective="check preferred_language for client",
    )
    keys_a = [m.content.get("language") for m in context_a.client_memories]
    assert "Indonesian" in keys_a
    assert "English" not in keys_a


@pytest.mark.asyncio
async def test_ai_fact_coercion_and_proposal(db_session: AsyncSession):
    repo = TenantRepository(db_session)
    tenant = await repo.create(TenantCreate(name="Trust Tenant", slug="trust-tenant"))
    await db_session.commit()

    service = MemoryService(db_session)

    # AI source attempting to create FACT is coerced to INSIGHT
    create_fact = MemoryCreateSchema(
        memory_type=MemoryType.FACT,
        key="customer_preference",
        content={"preference": "Product A"},
        source="ai_sales",
        confidence=0.99,
    )
    item, prop = await service.save_memory_or_propose(
        scope=MemoryScope.CLIENT,
        tenant_id=tenant.id,
        create_data=create_fact,
        source_agent="ai_sales",
    )
    assert item is not None
    assert item.memory_type == MemoryType.INSIGHT
    assert item.confidence <= 0.85

    # AI source attempting to change POLICY triggers a proposal
    create_policy = MemoryCreateSchema(
        memory_type=MemoryType.POLICY,
        key="discount_policy",
        content={"max_discount": 50},
        source="ai_sales",
    )
    item_p, prop_p = await service.save_memory_or_propose(
        scope=MemoryScope.BUSINESS,
        tenant_id=tenant.id,
        create_data=create_policy,
        source_agent="ai_sales",
    )
    assert item_p is None
    assert prop_p is not None
    assert prop_p.proposed_key == "discount_policy"
    assert prop_p.status == "PENDING"
