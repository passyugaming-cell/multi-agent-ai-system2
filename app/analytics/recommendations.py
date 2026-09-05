import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.owner_ai import Recommendation


class RecommendationAnalyticsService:
    """Service for analyzing recommendation system performance and outcomes."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def get_recommendation_analytics(
        self,
        tenant_id: Optional[uuid.UUID] = None,
        period_days: int = 30,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=period_days)

        rec_filter = [Recommendation.tenant_id == tenant_id] if tenant_id else []

        # 1. Total created
        stmt_total = select(func.count(Recommendation.id)).where(
            and_(
                Recommendation.created_at >= period_start,
                *rec_filter,
            )
        )
        total_created = (await self.session.execute(stmt_total)).scalar() or 0

        # 2. Breakdown by status
        stmt_status = select(
            Recommendation.status,
            func.count(Recommendation.id)
        ).where(
            and_(
                Recommendation.created_at >= period_start,
                *rec_filter,
            )
        ).group_by(Recommendation.status)

        status_rows = (await self.session.execute(stmt_status)).all()
        by_status = {st: cnt for st, cnt in status_rows}

        accepted = by_status.get("ACCEPTED", 0) + by_status.get("EXECUTED", 0) + by_status.get("APPROVED", 0)
        rejected = by_status.get("REJECTED", 0)
        modified = by_status.get("MODIFIED", 0)
        expired = by_status.get("EXPIRED", 0)
        proposed = by_status.get("PROPOSED", 0)

        acceptance_rate = round((accepted / total_created * 100.0), 2) if total_created > 0 else 0.0

        return {
            "period_days": period_days,
            "recommendations_created": total_created,
            "accepted": accepted,
            "rejected": rejected,
            "modified": modified,
            "expired": expired,
            "proposed": proposed,
            "acceptance_rate_pct": acceptance_rate,
            "actions_completed": accepted,
            "measurable_outcomes_recorded": accepted > 0,
            "effectiveness_score": round(acceptance_rate, 1),
            "generated_at": now.isoformat(),
        }
