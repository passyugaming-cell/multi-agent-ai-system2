import uuid
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.core.context import get_tenant_id
from app.core.exceptions import AppError
from app.analytics.services import AnalyticsService
from app.analytics.schemas import (
    FinancialAnalyticsSchema,
    ClientAnalyticsSchema,
    SalesAnalyticsSchema,
    SalesFunnelStageSchema,
    CustomerAnalyticsSchema,
    AIAnalyticsSchema,
    AutomationAnalyticsSchema,
    SubscriptionAnalyticsSchema,
    KPISchema,
    TrendSchema,
    AnomalySchema,
    ForecastSchema,
    DailyBusinessBriefSchema,
    WeeklyStrategicReviewSchema,
)

router = APIRouter(prefix="/analytics", tags=["Analytics & BI"])


def require_tenant_id() -> uuid.UUID:
    tid = get_tenant_id()
    if not tid:
        raise AppError("X-Tenant-ID header is missing or context is invalid.", status_code=400)
    return uuid.UUID(tid) if isinstance(tid, str) else tid


@router.get("/financial", response_model=FinancialAnalyticsSchema)
async def get_financial_analytics(
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.financial.get_financial_analytics(tenant_id)


@router.get("/clients", response_model=ClientAnalyticsSchema)
async def get_client_analytics(
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.clients.get_client_analytics(tenant_id)


@router.get("/sales", response_model=SalesAnalyticsSchema)
async def get_sales_analytics(
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.sales.get_sales_analytics(tenant_id)


@router.get("/customers", response_model=CustomerAnalyticsSchema)
async def get_customer_analytics(
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.customers.get_customer_analytics(tenant_id)


@router.get("/ai", response_model=AIAnalyticsSchema)
async def get_ai_analytics(
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.ai.get_ai_analytics(tenant_id)


@router.get("/automation", response_model=AutomationAnalyticsSchema)
async def get_automation_analytics(
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.automation.get_automation_analytics(tenant_id)


@router.get("/subscriptions", response_model=SubscriptionAnalyticsSchema)
async def get_subscription_analytics(
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.subscriptions.get_subscription_analytics(tenant_id)


@router.get("/funnel", response_model=List[SalesFunnelStageSchema])
async def get_funnel_analytics(
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.funnel.get_sales_funnel(tenant_id)


@router.get("/kpi", response_model=List[KPISchema])
async def get_kpi_analytics(
    period: str = Query("30d", description="Period window e.g. 24h, 7d, 30d"),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.kpi.get_kpis(tenant_id, period)


@router.get("/trends", response_model=List[TrendSchema])
async def get_trends_analytics(
    period_days: int = Query(30, description="Comparison window days"),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.trends.detect_trends(tenant_id, period_days)


@router.get("/anomalies", response_model=List[AnomalySchema])
async def get_anomalies_analytics(
    period_days: int = Query(30, description="Detection window days"),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.anomalies.detect_anomalies(tenant_id, period_days)


@router.get("/forecast", response_model=List[ForecastSchema])
async def get_forecast_analytics(
    period_days: int = Query(30, description="Forecast baseline days"),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.forecasting.generate_forecasts(tenant_id, period_days)


@router.get("/health")
async def get_health_analytics(
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    business_health = await service.get_business_health(tenant_id)
    client_health = await service.get_client_health(tenant_id)
    return {
        "business_health": business_health,
        "client_health": client_health,
    }


@router.get("/recommendations")
async def get_recommendations_analytics(
    period_days: int = Query(30, description="Evaluation window days"),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.recommendations.get_recommendation_analytics(tenant_id, period_days)


@router.get("/daily-brief", response_model=DailyBusinessBriefSchema)
async def get_daily_brief(
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.reports.generate_daily_brief(tenant_id)


@router.get("/weekly-review", response_model=WeeklyStrategicReviewSchema)
async def get_weekly_review(
    db: AsyncSession = Depends(get_db),
):
    tenant_id = require_tenant_id()
    service = AnalyticsService(db)
    return await service.reports.generate_weekly_review(tenant_id)


# Owner / Platform-level aggregated analytics (Cross-tenant)
@router.get("/owner/platform")
async def get_owner_platform_analytics(
    db: AsyncSession = Depends(get_db),
):
    service = AnalyticsService(db)
    fin = await service.financial.get_financial_analytics(tenant_id=None)
    clients = await service.clients.get_client_analytics(tenant_id=None)
    ai_data = await service.ai.get_ai_analytics(tenant_id=None)
    auto_data = await service.automation.get_automation_analytics(tenant_id=None)
    return {
        "platform_financials": fin.model_dump(mode="json"),
        "platform_clients": clients.model_dump(mode="json"),
        "platform_ai_usage": ai_data.model_dump(mode="json"),
        "platform_automation": auto_data.model_dump(mode="json"),
    }
