import uuid
from typing import Generic, Type, TypeVar, Sequence, Any
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)


class BaseRepository(Generic[ModelType]):
    """Tenant-scoped base repository providing safe entity queries."""

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> ModelType | None:
        stmt = select(self.model).where(
            self.model.tenant_id == tenant_id,
            self.model.id == entity_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> Sequence[ModelType]:
        stmt = (
            select(self.model)
            .where(self.model.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create(self, tenant_id: uuid.UUID, **kwargs: Any) -> ModelType:
        kwargs["tenant_id"] = tenant_id
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(
        self, tenant_id: uuid.UUID, entity_id: uuid.UUID, **kwargs: Any
    ) -> ModelType | None:
        instance = await self.get_by_id(tenant_id, entity_id)
        if not instance:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(instance, key):
                setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> bool:
        stmt = delete(self.model).where(
            self.model.tenant_id == tenant_id,
            self.model.id == entity_id,
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0
