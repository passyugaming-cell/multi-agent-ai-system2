import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.schemas import EventSchema
from app.agents.owner_ai.events import OwnerAIEventConsumer
from app.tenants.repository import TenantRepository
from app.tenants.schemas import TenantCreate


@pytest.mark.asyncio
async def test_owner_ai_event_consumer_filtering(db_session: AsyncSession):
    repo = TenantRepository(db_session)
    tenant = await repo.create(TenantCreate(name="Event Tenant", slug="evt-tenant"))
    await db_session.commit()

    # 1. Routine/irrelevant event is filtered out
    routine_evt = EventSchema(
        event_id="evt_routine_1",
        tenant_id=str(tenant.id),
        event_type="product.viewed",
        payload={"product_id": "prod_1"},
        source="catalog",
    )
    res_routine = await OwnerAIEventConsumer.process_event(routine_evt, db_session)
    assert res_routine is None

    # 2. Meaningful event (client.at_risk) triggers task creation
    meaningful_evt = EventSchema(
        event_id="evt_meaningful_1",
        tenant_id=str(tenant.id),
        event_type="client.at_risk",
        payload={"risk_score": 45, "reason": "Decreased engagement"},
        source="client_manager",
    )
    res_meaningful = await OwnerAIEventConsumer.process_event(meaningful_evt, db_session)
    assert res_meaningful is not None
    assert res_meaningful["processed"] is True
    assert "task_id" in res_meaningful


@pytest.mark.asyncio
async def test_owner_ai_api_endpoints(async_client: AsyncClient, tenant_a):
    # 1. POST /api/v1/owner-ai/run
    res_run = await async_client.post(
        "/api/v1/owner-ai/run",
        json={"objective": "Investigate monthly performance drop"},
        headers={"X-Tenant-ID": str(tenant_a.id)},
    )
    assert res_run.status_code == 200
    assert "status" in res_run.json()

    # 2. GET /api/v1/owner-ai/brief/daily
    res_brief = await async_client.get(
        "/api/v1/owner-ai/brief/daily",
        headers={"X-Tenant-ID": str(tenant_a.id)},
    )
    assert res_brief.status_code == 200
    assert "key_facts" in res_brief.json()

    # 3. GET /api/v1/owner-ai/review/weekly
    res_review = await async_client.get(
        "/api/v1/owner-ai/review/weekly",
        headers={"X-Tenant-ID": str(tenant_a.id)},
    )
    assert res_review.status_code == 200
    assert "weekly_performance" in res_review.json()

    # 4. GET /api/v1/owner-ai/recommendations
    res_recs = await async_client.get(
        "/api/v1/owner-ai/recommendations",
        headers={"X-Tenant-ID": str(tenant_a.id)},
    )
    assert res_recs.status_code == 200
    assert isinstance(res_recs.json(), list)

    # 5. GET /api/v1/owner-ai/memory
    res_mem = await async_client.get(
        "/api/v1/owner-ai/memory?objective=sales",
        headers={"X-Tenant-ID": str(tenant_a.id)},
    )
    assert res_mem.status_code == 200
    assert "business_memories" in res_mem.json()
