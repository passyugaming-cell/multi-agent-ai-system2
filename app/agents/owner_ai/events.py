import uuid
import logging
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.schemas import EventSchema
from app.core.tasks.service import TaskService
from app.agents.owner_ai.orchestrator import OwnerAIOrchestrator

logger = logging.getLogger(__name__)

# Events that are meaningful enough to warrant Owner AI attention
RELEVANT_EVENT_TYPES = {
    "client.health_changed",
    "client.at_risk",
    "order.trend_changed",
    "payment.failed",
    "whatsapp.disconnected",
    "workflow.failed",
    "task.blocked",
    "approval.requested",
    "system.incident",
}


class OwnerAIEventConsumer:
    """Event Bus Consumer for Owner AI using deterministic filtering before raising tasks/orchestration."""

    @staticmethod
    def is_meaningful_event(event: EventSchema) -> bool:
        """Deterministic filter to prevent processing routine events with AI."""
        if event.event_type not in RELEVANT_EVENT_TYPES:
            return False

        payload = event.payload or {}

        # Deterministic severity/importance check
        if event.event_type == "payment.failed":
            # Only trigger for high amount or repeated failure
            amount = payload.get("amount", 0)
            return amount > 1000000 or payload.get("repeated", False)

        if event.event_type == "client.at_risk":
            return True

        if event.event_type in ("system.incident", "workflow.failed", "task.blocked"):
            return payload.get("severity") in ("HIGH", "CRITICAL") or payload.get("priority") in ("HIGH", "CRITICAL")

        return True

    @classmethod
    async def process_event(cls, event: EventSchema, db_session: AsyncSession) -> Dict[str, Any] | None:
        """Process meaningful events for tenant."""
        if not cls.is_meaningful_event(event):
            logger.debug("Event %s (%s) filtered out by deterministic filter.", event.event_id, event.event_type)
            return None

        tenant_id = uuid.UUID(event.tenant_id)
        task_service = TaskService(db_session)

        # Create Task in TaskSystem
        task = await task_service.create_task(
            tenant_id=tenant_id,
            title=f"Investigate Event: {event.event_type}",
            description=f"Event ID {event.event_id} from {event.source}: {event.payload}",
            task_type=f"event_investigation_{event.event_type}",
            priority="HIGH",
            assigned_agent="owner_ai",
            source="event_bus",
        )

        return {
            "processed": True,
            "task_id": str(task.id),
            "event_id": event.event_id,
            "event_type": event.event_type,
        }
