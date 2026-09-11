import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.schemas import EventSchema
from app.agents.owner_ai.events import OwnerAIEventConsumer
from app.tenants.repository import TenantRepository
from app.tenants.schemas import TenantCreate
from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context
from app.core.auth_service import hash_password, create_access_token
from app.database.models.user import User
from app.billing.subscription import SubscriptionService
from app.billing.plans import PlanService


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
async def test_owner_ai_api_endpoints(async_client: AsyncClient, db_session: AsyncSession, tenant_a, monkeypatch):
    import app.core.auth_service as auth_srv
    async def mock_is_revoked(jti: str) -> bool:
        return False
    monkeypatch.setattr(auth_srv, "is_token_revoked_redis", mock_is_revoked)
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

    # Create real user in database
    user_email = f"owner-{uuid.uuid4().hex[:6]}@example.com"
    user = User(
        tenant_id=tenant_a.id,
        email=user_email,
        password_hash=hash_password("Password123!"),
        role="owner",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    jwt_token = create_access_token({
        "sub": user_email,
        "tenant_ids": [str(tenant_a.id)],
        "active_tenant_id": str(tenant_a.id),
    })

    headers = {
        "X-Tenant-ID": str(tenant_a.id),
        "Authorization": f"Bearer {jwt_token}",
    }

    # 1. POST /api/v1/owner-ai/run
    res_run = await async_client.post(
        "/api/v1/owner-ai/run",
        json={"objective": "Investigate monthly performance drop"},
        headers=headers,
    )
    if res_run.status_code != 200:
        print("RUN FAILED JSON:", res_run.json())
    assert res_run.status_code == 200
    assert "status" in res_run.json()

    # 2. GET /api/v1/owner-ai/brief/daily
    res_brief = await async_client.get(
        "/api/v1/owner-ai/brief/daily",
        headers=headers,
    )
    assert res_brief.status_code == 200
    assert "key_facts" in res_brief.json()

    # 3. GET /api/v1/owner-ai/review/weekly
    res_review = await async_client.get(
        "/api/v1/owner-ai/review/weekly",
        headers=headers,
    )
    assert res_review.status_code == 200
    assert "weekly_performance" in res_review.json()

    # 4. GET /api/v1/owner-ai/recommendations
    res_recs = await async_client.get(
        "/api/v1/owner-ai/recommendations",
        headers=headers,
    )
    assert res_recs.status_code == 200
    assert isinstance(res_recs.json(), list)

    # 5. GET /api/v1/owner-ai/memory
    res_mem = await async_client.get(
        "/api/v1/owner-ai/memory?objective=sales",
        headers=headers,
    )
    assert res_mem.status_code == 200
    assert "business_memories" in res_mem.json()
