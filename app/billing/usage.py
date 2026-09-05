import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.billing import UsageRecord, Subscription
from app.billing.subscription import SubscriptionService
from app.billing.entitlement import EntitlementResolver
from app.billing.exceptions import LimitExceededError
from app.billing.events import publish_billing_event


class UsageMetric:
    AI_CREDITS = "ai_credits"
    AUTOMATION_RUNS = "automation_runs"
    ACTIVE_CUSTOMERS = "active_customers"
    OUTBOUND_MESSAGES = "outbound_messages"
    WHATSAPP_CONNECTIONS = "whatsapp_connections"
    ADMINS = "admins"
    STORAGE_BYTES = "storage_bytes"


TOKENS_PER_AI_CREDIT = 10  # Configurable conversion rule: 10 tokens = 1 credit


def calculate_ai_credits(total_tokens: int | None) -> int:
    """Calculates deterministic AI credits from raw total token count."""
    if not total_tokens or total_tokens <= 0:
        return 1
    credits = total_tokens // TOKENS_PER_AI_CREDIT
    return max(1, credits)


class UsageService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session
        self.sub_service = SubscriptionService(db_session)
        self.entitlement_resolver = EntitlementResolver(db_session)

    async def get_current_period(self, tenant_id: uuid.UUID) -> tuple[datetime, datetime]:
        sub = await self.sub_service.get_subscription(tenant_id)
        return sub.current_period_start, sub.current_period_end

    async def get_current_usage(self, tenant_id: uuid.UUID, metric: str) -> int:
        period_start, period_end = await self.get_current_period(tenant_id)
        stmt = select(func.sum(UsageRecord.quantity)).where(
            and_(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.metric == metric,
                UsageRecord.period_start >= period_start,
                UsageRecord.period_end <= period_end,
            )
        )
        val = (await self.session.execute(stmt)).scalar()
        return val if val is not None else 0

    async def check_and_increment_usage(
        self,
        tenant_id: uuid.UUID,
        metric: str,
        quantity: int,
        source: str = "SYSTEM",
        metadata: dict[str, Any] | None = None,
        policy: str = "BLOCK",  # ALLOW, WARN, BLOCK
    ) -> UsageRecord:
        """Atomic limit enforcement and usage incrementation with threshold event publishing."""
        period_start, period_end = await self.get_current_period(tenant_id)
        limit = await self.entitlement_resolver.get_limit(tenant_id, metric)

        current_usage = await self.get_current_usage(tenant_id, metric)
        projected_usage = current_usage + quantity

        if limit != -1:  # Limited metric
            if projected_usage > limit:
                if policy == "BLOCK":
                    raise LimitExceededError(metric, projected_usage, limit)

        # Record usage
        rec = UsageRecord(
            tenant_id=tenant_id,
            metric=metric,
            period_start=period_start,
            period_end=period_end,
            quantity=quantity,
            source=source,
            metadata_=metadata,
        )
        self.session.add(rec)
        await self.session.commit()

        # Check threshold percentages and trigger events
        if limit > 0:
            prev_ratio = float(current_usage) / float(limit)
            new_ratio = float(projected_usage) / float(limit)

            # Trigger 70% threshold
            if prev_ratio < 0.70 <= new_ratio:
                await publish_billing_event(
                    event_type="usage.warning",
                    tenant_id=tenant_id,
                    payload={
                        "metric": metric,
                        "threshold_percentage": 70,
                        "current_usage": projected_usage,
                        "limit": limit,
                    },
                    source="usage_service",
                )

            # Trigger 85% threshold
            if prev_ratio < 0.85 <= new_ratio:
                await publish_billing_event(
                    event_type="usage.warning",
                    tenant_id=tenant_id,
                    payload={
                        "metric": metric,
                        "threshold_percentage": 85,
                        "current_usage": projected_usage,
                        "limit": limit,
                    },
                    source="usage_service",
                )

            # Trigger 100% threshold
            if prev_ratio < 1.0 <= new_ratio:
                await publish_billing_event(
                    event_type="usage.limit_reached",
                    tenant_id=tenant_id,
                    payload={
                        "metric": metric,
                        "threshold_percentage": 100,
                        "current_usage": projected_usage,
                        "limit": limit,
                    },
                    source="usage_service",
                )

        return rec
