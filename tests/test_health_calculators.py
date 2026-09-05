import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.owner_ai.health import BusinessHealthCalculator, ClientHealthCalculator
from app.tenants.repository import TenantRepository
from app.tenants.schemas import TenantCreate
from app.database.models.order import Order
from app.database.models.customer import Customer


@pytest.mark.asyncio
async def test_health_calculators_deterministic(db_session: AsyncSession):
    repo = TenantRepository(db_session)
    tenant = await repo.create(TenantCreate(name="Health Tenant", slug="health-tenant"))
    await db_session.commit()

    # Create test customer and orders
    cust = Customer(tenant_id=tenant.id, name="Test Customer", email="test@example.com")
    db_session.add(cust)
    await db_session.commit()
    await db_session.refresh(cust)

    order1 = Order(tenant_id=tenant.id, customer_id=cust.id, status="COMPLETED", subtotal=100, total=100)
    order2 = Order(tenant_id=tenant.id, customer_id=cust.id, status="COMPLETED", subtotal=200, total=200)
    db_session.add_all([order1, order2])
    await db_session.commit()

    # Calculate business health
    biz_result = await BusinessHealthCalculator.calculate(db_session, tenant.id)
    assert 0.0 <= biz_result.score <= 100.0
    assert "revenue_sales" in biz_result.category_scores
    assert biz_result.historical_comparison["curr_30d_orders"] == 2
    assert biz_result.historical_comparison["curr_30d_revenue"] == 300.0

    # Calculate client health
    cli_result = await ClientHealthCalculator.calculate(db_session, tenant.id)
    assert 0.0 <= cli_result.score <= 100.0
    assert cli_result.category in ("HEALTHY", "NEEDS_ATTENTION", "AT_RISK", "CRITICAL")
    assert cli_result.score == 100.0  # Zero failures
