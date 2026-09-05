import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tenant import Tenant
from app.database.models.billing import Plan, Subscription, Invoice, InvoiceItem, Payment
from app.database.models.order import Order
from app.database.models.customer import Customer
from app.database.models.ai_usage import AIUsageRecord
from app.database.models.workflow import WorkflowExecution, WorkflowConfiguration
from app.database.models.owner_ai import Recommendation
from app.analytics.services import AnalyticsService
from app.analytics.events import AnalyticsEventConsumer
from app.core.events.schemas import EventSchema
from app.agents.owner_ai.tools import (
    tool_get_financial_summary,
    tool_get_client_summary,
    tool_get_sales_summary,
    tool_get_ai_summary,
    tool_get_automation_summary,
    tool_get_subscription_summary,
    tool_get_kpis,
    tool_get_trends,
    tool_get_anomalies,
    tool_get_forecast,
    tool_generate_daily_brief,
    tool_generate_weekly_review,
)
from app.agents.base.schemas import ToolRequest


@pytest.mark.asyncio
async def test_financial_analytics_and_decimal_precision(
    db_session: AsyncSession, tenant_a: Tenant
):
    analytics = AnalyticsService(db_session)
    now = datetime.now(timezone.utc)

    # Seed plan
    plan = Plan(
        name="Pro Plan",
        code=f"pro-{uuid.uuid4().hex[:6]}",
        price_monthly=Decimal("500000.00"),
        price_yearly=Decimal("5000000.00"),
        currency="IDR",
    )
    db_session.add(plan)
    await db_session.commit()

    # Seed subscription
    sub = Subscription(
        tenant_id=tenant_a.id,
        plan_id=plan.id,
        status="ACTIVE",
        billing_cycle="MONTHLY",
        amount=Decimal("500000.00"),
        currency="IDR",
        started_at=now,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    db_session.add(sub)
    await db_session.commit()

    # Seed paid invoice with decimal amount
    inv = Invoice(
        tenant_id=tenant_a.id,
        subscription_id=sub.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
        status="PAID",
        subtotal=Decimal("10000000.00"),
        total=Decimal("10000000.00"),
        currency="IDR",
        issued_at=now,
        paid_at=now,
    )
    db_session.add(inv)
    await db_session.commit()

    inv_item = InvoiceItem(
        invoice_id=inv.id,
        description="Subscription Fee",
        revenue_type="SUBSCRIPTION",
        amount=Decimal("10000000.00"),
        quantity=1,
        unit_price=Decimal("10000000.00"),
    )
    db_session.add(inv_item)
    await db_session.commit()

    fin = await analytics.financial.get_financial_analytics(tenant_a.id)

    assert fin.total_revenue == Decimal("10000000.00")
    assert fin.mrr == Decimal("500000.00")
    assert fin.arr == Decimal("6000000.00")
    assert isinstance(fin.total_revenue, Decimal)


@pytest.mark.asyncio
async def test_tenant_isolation_analytics(
    db_session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
):
    analytics = AnalyticsService(db_session)
    now = datetime.now(timezone.utc)

    # Seed invoice for Tenant A (Rp 10,000,000)
    inv_a = Invoice(
        tenant_id=tenant_a.id,
        invoice_number=f"INV-A-{uuid.uuid4().hex[:6]}",
        status="PAID",
        subtotal=Decimal("10000000.00"),
        total=Decimal("10000000.00"),
        paid_at=now,
    )
    db_session.add(inv_a)

    # Seed invoice for Tenant B (Rp 5,000,000)
    inv_b = Invoice(
        tenant_id=tenant_b.id,
        invoice_number=f"INV-B-{uuid.uuid4().hex[:6]}",
        status="PAID",
        subtotal=Decimal("5000000.00"),
        total=Decimal("5000000.00"),
        paid_at=now,
    )
    db_session.add(inv_b)
    await db_session.commit()

    fin_a = await analytics.financial.get_financial_analytics(tenant_a.id)
    fin_b = await analytics.financial.get_financial_analytics(tenant_b.id)

    assert fin_a.total_revenue == Decimal("10000000.00")
    assert fin_b.total_revenue == Decimal("5000000.00")


@pytest.mark.asyncio
async def test_acceptance_scenario_revenue_change_and_trends(
    db_session: AsyncSession, tenant_a: Tenant
):
    analytics = AnalyticsService(db_session)
    now = datetime.now(timezone.utc)
    curr_start = now - timedelta(days=15)
    prev_start = now - timedelta(days=45)

    # Current period revenue Rp 10.000.000
    inv_curr = Invoice(
        tenant_id=tenant_a.id,
        invoice_number=f"INV-C-{uuid.uuid4().hex[:6]}",
        status="PAID",
        total=Decimal("10000000.00"),
        paid_at=curr_start,
    )
    # Previous period revenue Rp 8.000.000
    inv_prev = Invoice(
        tenant_id=tenant_a.id,
        invoice_number=f"INV-P-{uuid.uuid4().hex[:6]}",
        status="PAID",
        total=Decimal("8000000.00"),
        paid_at=prev_start,
    )
    db_session.add_all([inv_curr, inv_prev])
    await db_session.commit()

    fin = await analytics.financial.get_financial_analytics(tenant_a.id)
    trends = await analytics.trends.detect_trends(tenant_a.id)

    assert fin.total_revenue == Decimal("10000000.00")
    assert fin.revenue_growth_pct == 25.0
    assert any(t.metric_key == "revenue" and t.direction == "INCREASING" for t in trends)


@pytest.mark.asyncio
async def test_anomaly_detection_without_fabricated_cause(
    db_session: AsyncSession, tenant_a: Tenant
):
    analytics = AnalyticsService(db_session)
    now = datetime.now(timezone.utc)
    curr_start = now - timedelta(days=15)
    prev_start = now - timedelta(days=45)

    # Historical baseline Rp 10.000.000
    inv_prev = Invoice(
        tenant_id=tenant_a.id,
        invoice_number=f"INV-P-{uuid.uuid4().hex[:6]}",
        status="PAID",
        total=Decimal("10000000.00"),
        paid_at=prev_start,
    )
    # Current period revenue sudden drop to Rp 5.000.000 (-50%)
    inv_curr = Invoice(
        tenant_id=tenant_a.id,
        invoice_number=f"INV-C-{uuid.uuid4().hex[:6]}",
        status="PAID",
        total=Decimal("5000000.00"),
        paid_at=curr_start,
    )
    db_session.add_all([inv_prev, inv_curr])
    await db_session.commit()

    anomalies = await analytics.anomalies.detect_anomalies(tenant_a.id)

    rev_anomalies = [a for a in anomalies if a.metric == "revenue"]
    assert len(rev_anomalies) == 1
    anom = rev_anomalies[0]
    assert anom.deviation_pct == -50.0
    assert "dislike" not in anom.explanation.lower()  # Must not fabricate subjective cause


@pytest.mark.asyncio
async def test_forecasting_insufficient_data_handling(
    db_session: AsyncSession, tenant_a: Tenant
):
    analytics = AnalyticsService(db_session)
    forecasts = await analytics.forecasting.generate_forecasts(tenant_a.id)

    rev_fc = next(f for f in forecasts if f.metric == "revenue")
    assert rev_fc.data_sufficiency == "INSUFFICIENT_DATA"
    assert rev_fc.predicted_value is None


@pytest.mark.asyncio
async def test_health_calculators_reuse(
    db_session: AsyncSession, tenant_a: Tenant
):
    analytics = AnalyticsService(db_session)
    biz_h = await analytics.get_business_health(tenant_a.id)
    client_h = await analytics.get_client_health(tenant_a.id)

    assert "score" in biz_h
    assert "category_scores" in biz_h
    assert "score" in client_h
    assert "category" in client_h


@pytest.mark.asyncio
async def test_daily_brief_and_weekly_review(
    db_session: AsyncSession, tenant_a: Tenant
):
    analytics = AnalyticsService(db_session)
    brief = await analytics.reports.generate_daily_brief(tenant_a.id)
    review = await analytics.reports.generate_weekly_review(tenant_a.id)

    assert brief.business_health_score >= 0.0
    assert "key_numbers" in brief.model_dump(mode="json")
    assert review.weekly_revenue >= Decimal("0.00")
    assert len(review.trends) >= 0


@pytest.mark.asyncio
async def test_owner_ai_read_only_analytics_tools(
    db_session: AsyncSession, tenant_a: Tenant
):
    req = ToolRequest(
        tenant_id=str(tenant_a.id),
        tool_name="get_financial_summary",
        parameters={},
        correlation_id="test_corr_1",
    )

    res_fin = await tool_get_financial_summary(req, db_session)
    assert res_fin.success is True
    assert "total_revenue" in res_fin.data

    res_kpis = await tool_get_kpis(req, db_session)
    assert res_kpis.success is True
    assert isinstance(res_kpis.data, list)

    res_brief = await tool_generate_daily_brief(req, db_session)
    assert res_brief.success is True
    assert "summary" in res_brief.data


@pytest.mark.asyncio
async def test_event_bus_analytics_consumer(
    db_session: AsyncSession, tenant_a: Tenant
):
    evt = EventSchema(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        tenant_id=str(tenant_a.id),
        event_type="payment.failed",
        payload={"amount": 5000000},
        source="billing_service",
    )

    res = await AnalyticsEventConsumer.process_event(evt, db_session)
    assert res is not None
    assert res["processed"] is True
    assert res["tenant_id"] == str(tenant_a.id)


@pytest.mark.asyncio
async def test_analytics_api_endpoints(
    client: AsyncClient, tenant_a: Tenant, tenant_b: Tenant
):
    headers_a = {"X-Tenant-ID": str(tenant_a.id)}
    headers_b = {"X-Tenant-ID": str(tenant_b.id)}

    # Financial
    r_fin = await client.get("/api/v1/analytics/financial", headers=headers_a)
    assert r_fin.status_code == 200
    assert "total_revenue" in r_fin.json()

    # Clients
    r_cli = await client.get("/api/v1/analytics/clients", headers=headers_a)
    assert r_cli.status_code == 200
    assert "active_clients" in r_cli.json()

    # Sales
    r_sales = await client.get("/api/v1/analytics/sales", headers=headers_a)
    assert r_sales.status_code == 200
    assert "funnel_stages" in r_sales.json()

    # Customers
    r_cust = await client.get("/api/v1/analytics/customers", headers=headers_a)
    assert r_cust.status_code == 200
    assert "total_customers" in r_cust.json()

    # AI
    r_ai = await client.get("/api/v1/analytics/ai", headers=headers_a)
    assert r_ai.status_code == 200
    assert "total_requests" in r_ai.json()

    # Automation
    r_auto = await client.get("/api/v1/analytics/automation", headers=headers_a)
    assert r_auto.status_code == 200
    assert "workflow_executions" in r_auto.json()

    # Subscriptions
    r_sub = await client.get("/api/v1/analytics/subscriptions", headers=headers_a)
    assert r_sub.status_code == 200
    assert "active_subscriptions" in r_sub.json()

    # Funnel
    r_funnel = await client.get("/api/v1/analytics/funnel", headers=headers_a)
    assert r_funnel.status_code == 200
    assert isinstance(r_funnel.json(), list)

    # KPI
    r_kpi = await client.get("/api/v1/analytics/kpi", headers=headers_a)
    assert r_kpi.status_code == 200
    assert isinstance(r_kpi.json(), list)

    # Trends
    r_trends = await client.get("/api/v1/analytics/trends", headers=headers_a)
    assert r_trends.status_code == 200
    assert isinstance(r_trends.json(), list)

    # Anomalies
    r_anom = await client.get("/api/v1/analytics/anomalies", headers=headers_a)
    assert r_anom.status_code == 200
    assert isinstance(r_anom.json(), list)

    # Forecast
    r_fc = await client.get("/api/v1/analytics/forecast", headers=headers_a)
    assert r_fc.status_code == 200
    assert isinstance(r_fc.json(), list)

    # Health
    r_health = await client.get("/api/v1/analytics/health", headers=headers_a)
    assert r_health.status_code == 200
    assert "business_health" in r_health.json()

    # Recommendations
    r_recs = await client.get("/api/v1/analytics/recommendations", headers=headers_a)
    assert r_recs.status_code == 200
    assert "recommendations_created" in r_recs.json()

    # Daily brief
    r_brief = await client.get("/api/v1/analytics/daily-brief", headers=headers_a)
    assert r_brief.status_code == 200
    assert "key_numbers" in r_brief.json()

    # Weekly review
    r_review = await client.get("/api/v1/analytics/weekly-review", headers=headers_a)
    assert r_review.status_code == 200
    assert "weekly_revenue" in r_review.json()

    # Platform (Owner)
    r_platform = await client.get("/api/v1/analytics/owner/platform", headers=headers_a)
    assert r_platform.status_code == 200
    assert "platform_financials" in r_platform.json()
