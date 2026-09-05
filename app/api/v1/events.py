import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_tenant_id
from app.database.session import get_db_session
from app.core.events.schemas import EventSchema
from app.core.events.publisher import get_event_bus
from app.core.workflows.engine import WorkflowEngine
from app.schemas.phase2 import EventPublishRequest, EventResponse

router = APIRouter(prefix="/events", tags=["Events"])


@router.post("", response_model=EventResponse)
async def publish_event(
    body: EventPublishRequest,
    db: AsyncSession = Depends(get_db_session),
) -> EventResponse:
    tenant_id = get_tenant_id()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context missing")

    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    event = EventSchema(
        event_id=event_id,
        tenant_id=str(tenant_id),
        event_type=body.event_type,
        payload=body.payload,
        source=body.source,
        correlation_id=body.correlation_id,
        causation_id=body.causation_id,
        idempotency_key=body.idempotency_key,
    )

    # Publish to bus
    bus = get_event_bus()
    await bus.publish(event)

    # Execute workflow engine inline for request lifecycle
    engine = WorkflowEngine(db)
    await engine.handle_event(event)

    return EventResponse(
        event_id=event.event_id,
        tenant_id=event.tenant_id,
        event_type=event.event_type,
        occurred_at=event.occurred_at.isoformat(),
        source=event.source,
        status="published",
    )
