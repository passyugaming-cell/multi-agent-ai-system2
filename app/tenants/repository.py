from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tenant import Tenant
from app.tenants.schemas import TenantCreate, TenantUpdate


class TenantRepository:
    """Repository for managing Tenant database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, tenant_id: UUID) -> Optional[Tenant]:
        """Fetch tenant by UUID primary key."""
        result = await self.session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Tenant]:
        """Fetch tenant by unique slug."""
        result = await self.session.execute(
            select(Tenant).where(Tenant.slug == slug)
        )
        return result.scalar_one_or_none()

    async def create(self, tenant_data: TenantCreate) -> Tenant:
        """Create a new tenant entity."""
        tenant = Tenant(
            name=tenant_data.name,
            slug=tenant_data.slug,
            is_active=tenant_data.is_active,
        )
        self.session.add(tenant)
        await self.session.flush()
        return tenant

    async def update(self, tenant: Tenant, update_data: TenantUpdate) -> Tenant:
        """Update existing tenant entity."""
        data = update_data.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(tenant, field, value)
        await self.session.flush()
        return tenant

    async def exists(self, tenant_id: UUID) -> bool:
        """Check if tenant exists by UUID."""
        tenant = await self.get_by_id(tenant_id)
        return tenant is not None

    async def is_active(self, tenant_id: UUID) -> bool:
        """Check if tenant is active by UUID."""
        tenant = await self.get_by_id(tenant_id)
        return tenant is not None and tenant.is_active
