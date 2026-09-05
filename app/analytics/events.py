import uuid
import logging
from typing import Dict, Any, Set
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.schemas import EventSchema
from app.analytics.services import AnalyticsService

logger = logging.getLogger(__name__)

ANALYTICS_EVENT_TYPES: Set[str] = {
    "invoice.paid",
    "payment.failed",
    "payment.successful",
    "order.created",
    "order.completed",
    "subscription.created",
    "subscription.updated",
    "subscription.cancelled",
    "workflow.failed",
    "usage.threshold_exceeded",
}


class AnalyticsEventConsumer:
    """Event Bus Consumer for near-real-time analytics calculations and anomaly checks."""

    _processed_event_ids: Set[str] = set()

    @classmethod
    def is_relevant_event(cls, event: EventSchema) -> bool:
        return event.event_type in ANALYTICS_EVENT_TYPES

    @classmethod
    async def process_event(cls, event: EventSchema, db_session: AsyncSession) -> Dict[str, Any] | None:
        """Tenant-scoped, idempotent event processor."""
        if not cls.is_relevant_event(event):
            return None

        # Idempotency check
        if event.event_id in cls._processed_event_ids:
            logger.info("Analytics consumer skipping duplicate event %s", event.event_id)
            return {"processed": False, "reason": "duplicate", "event_id": event.event_id}

        cls._processed_event_ids.add(event.event_id)
        if len(cls._processed_event_ids) > 10000:
            cls._processed_event_ids.clear()

        tenant_id = uuid.UUID(event.tenant_id)
        analytics_svc = AnalyticsService(db_session)

        # Trigger KPI refresh / anomaly check
        anomalies = await analytics_svc.anomalies.detect_anomalies(tenant_id=tenant_id, period_days=1)

        return {
            "processed": True,
            "event_id": event.event_id,
            "event_type": event.event_type,
            "tenant_id": str(tenant_id),
            "anomalies_detected": len(anomalies),
        }
