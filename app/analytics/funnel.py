import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.sales import SalesAnalyticsService
from app.analytics.schemas import SalesFunnelStageSchema


class FunnelAnalyticsService:
    """Service for deterministic multi-stage funnel analytics."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def get_sales_funnel(
        self,
        tenant_id: Optional[uuid.UUID] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> List[SalesFunnelStageSchema]:
        sales_svc = SalesAnalyticsService(self.session)
        res = await sales_svc.get_sales_analytics(
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
        )
        return res.funnel_stages
