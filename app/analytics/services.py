import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.financial import FinancialAnalyticsService
from app.analytics.clients import ClientAnalyticsService
from app.analytics.sales import SalesAnalyticsService
from app.analytics.customers import CustomerAnalyticsService
from app.analytics.ai import AIAnalyticsService
from app.analytics.automation import AutomationAnalyticsService
from app.analytics.subscriptions import SubscriptionAnalyticsService
from app.analytics.funnel import FunnelAnalyticsService
from app.analytics.kpi import KPIService
from app.analytics.trends import TrendDetectionService
from app.analytics.anomalies import AnomalyDetectionService
from app.analytics.forecasting import ForecastingService
from app.analytics.recommendations import RecommendationAnalyticsService
from app.analytics.reports import ExecutiveReportService
from app.agents.owner_ai.health import BusinessHealthCalculator, ClientHealthCalculator


class AnalyticsService:
    """Unified façade service providing full Phase 5 Analytics & Business Intelligence."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session
        self.financial = FinancialAnalyticsService(db_session)
        self.clients = ClientAnalyticsService(db_session)
        self.sales = SalesAnalyticsService(db_session)
        self.customers = CustomerAnalyticsService(db_session)
        self.ai = AIAnalyticsService(db_session)
        self.automation = AutomationAnalyticsService(db_session)
        self.subscriptions = SubscriptionAnalyticsService(db_session)
        self.funnel = FunnelAnalyticsService(db_session)
        self.kpi = KPIService(db_session)
        self.trends = TrendDetectionService(db_session)
        self.anomalies = AnomalyDetectionService(db_session)
        self.forecasting = ForecastingService(db_session)
        self.recommendations = RecommendationAnalyticsService(db_session)
        self.reports = ExecutiveReportService(db_session)

    async def get_business_health(self, tenant_id: uuid.UUID) -> Dict[str, Any]:
        """Expose existing BusinessHealthCalculator output."""
        res = await BusinessHealthCalculator.calculate(self.session, tenant_id)
        return res.model_dump(mode="json")

    async def get_client_health(self, tenant_id: uuid.UUID) -> Dict[str, Any]:
        """Expose existing ClientHealthCalculator output."""
        res = await ClientHealthCalculator.calculate(self.session, tenant_id)
        return res.model_dump(mode="json")
