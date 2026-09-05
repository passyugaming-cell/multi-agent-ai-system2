from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AppException,
    TenantInactiveException,
    TenantNotFoundException,
)
from app.database.models.tenant import Tenant
from app.tenants.repository import TenantRepository
from app.tenants.schemas import TenantCreate, TenantUpdate


class TenantService:
    """Service layer handling tenant business logic and lifecycle rules."""

    def __init__(self, session: AsyncSession) -> None:
        self.repository = TenantRepository(session)

    async def get_tenant_by_id(self, tenant_id: UUID) -> Tenant:
        """Retrieve tenant by ID or raise TenantNotFoundException."""
        tenant = await self.repository.get_by_id(tenant_id)
        if not tenant:
            raise TenantNotFoundException()
        return tenant

    async def get_tenant_by_slug(self, slug: str) -> Tenant:
        """Retrieve tenant by slug or raise TenantNotFoundException."""
        tenant = await self.repository.get_by_slug(slug)
        if not tenant:
            raise TenantNotFoundException()
        return tenant

    async def create_tenant(self, tenant_data: TenantCreate) -> Tenant:
        """Create tenant enforcing slug uniqueness."""
        existing = await self.repository.get_by_slug(tenant_data.slug)
        if existing:
            raise AppException(
                code="SLUG_ALREADY_EXISTS",
                message=f"Tenant with slug '{tenant_data.slug}' already exists",
                status_code=400,
            )
        return await self.repository.create(tenant_data)

    async def update_tenant(self, tenant_id: UUID, update_data: TenantUpdate) -> Tenant:
        """Update tenant attributes with slug uniqueness verification."""
        tenant = await self.get_tenant_by_id(tenant_id)
        if update_data.slug and update_data.slug != tenant.slug:
            existing = await self.repository.get_by_slug(update_data.slug)
            if existing:
                raise AppException(
                    code="SLUG_ALREADY_EXISTS",
                    message=f"Tenant with slug '{update_data.slug}' already exists",
                    status_code=400,
                )
        return await self.repository.update(tenant, update_data)

    async def validate_tenant(self, tenant_id: UUID) -> Tenant:
        """Validate tenant exists and is active."""
        tenant = await self.repository.get_by_id(tenant_id)
        if not tenant:
            raise TenantNotFoundException()
        if not tenant.is_active:
            raise TenantInactiveException()
        return tenant
