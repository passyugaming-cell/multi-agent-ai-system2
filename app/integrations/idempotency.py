import uuid
import logging
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.integrations import IntegrationExecution

logger = logging.getLogger(__name__)


class IntegrationIdempotencyChecker:
    """Ensures integration operations and webhooks are executed idempotently."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def get_existing_execution(
        self, tenant_id: uuid.UUID, idempotency_key: str
    ) -> IntegrationExecution | None:
        stmt = select(IntegrationExecution).where(
            and_(
                IntegrationExecution.tenant_id == tenant_id,
                IntegrationExecution.idempotency_key == idempotency_key,
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
