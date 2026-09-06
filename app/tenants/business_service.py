import uuid
from typing import Sequence, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.publisher import get_event_bus
from app.core.exceptions import AppException
from app.database.models import BusinessProfile, Product, ProductVariant, KnowledgeItem
from app.repositories.domain import (
    BusinessProfileRepository,
    ProductRepository,
    ProductVariantRepository,
    KnowledgeItemRepository,
)
from app.schemas.domain import (
    BusinessProfileCreate,
    BusinessProfileUpdate,
    ProductCreate,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantUpdate,
    KnowledgeItemCreate,
    KnowledgeItemUpdate,
)

# Valid Knowledge Lifecycle State Transitions
VALID_KNOWLEDGE_TRANSITIONS = {
    "DRAFT": {"VALIDATING", "APPROVED", "ARCHIVED"},
    "VALIDATING": {"APPROVED", "DRAFT", "ARCHIVED"},
    "APPROVED": {"ACTIVE", "OUTDATED", "ARCHIVED"},
    "ACTIVE": {"OUTDATED", "ARCHIVED"},
    "OUTDATED": {"ACTIVE", "ARCHIVED"},
    "ARCHIVED": {"DRAFT"},
}


class BusinessDataService:
    """Service layer for business profile, catalog products & variants, and knowledge setup."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.bp_repo = BusinessProfileRepository(db)
        self.prod_repo = ProductRepository(db)
        self.variant_repo = ProductVariantRepository(db)
        self.know_repo = KnowledgeItemRepository(db)

    def _check_permission(
        self,
        actor_permissions: set[str] | list[str] | None,
        required_permission: str,
        allow_internal: bool = False,
    ) -> None:
        """Enforces fail-closed permission authorization if actor_permissions header is supplied."""
        if allow_internal:
            return
        if actor_permissions is not None:
            perms_set = set(actor_permissions)
            if required_permission not in perms_set and "*" not in perms_set:
                raise AppException(
                    code="PERMISSION_DENIED",
                    message=f"Permission denied: missing {required_permission}",
                    status_code=403,
                )

    async def _publish_event(self, event_type: str, tenant_id: uuid.UUID, payload: dict[str, Any]) -> None:
        """Safely publishes an event to EventBus."""
        try:
            event_bus = get_event_bus()
            await event_bus.publish(
                event_type,
                {
                    "tenant_id": str(tenant_id),
                    "event_type": event_type,
                    "payload": payload,
                },
            )
        except Exception:
            pass

    # --- BUSINESS PROFILE ---
    async def get_business_profile(
        self, tenant_id: uuid.UUID, actor_permissions: set[str] | list[str] | None = None
    ) -> BusinessProfile:
        self._check_permission(actor_permissions, "business.read")
        bp = await self.bp_repo.get_by_tenant(tenant_id)
        if not bp:
            raise AppException(
                code="BUSINESS_PROFILE_NOT_FOUND",
                message="Business profile not found for tenant.",
                status_code=404,
            )
        return bp

    async def create_or_update_business_profile(
        self,
        tenant_id: uuid.UUID,
        payload: BusinessProfileCreate | BusinessProfileUpdate,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> BusinessProfile:
        self._check_permission(actor_permissions, "business.write")
        existing = await self.bp_repo.get_by_tenant(tenant_id)
        data = payload.model_dump(exclude_unset=True)

        if existing:
            updated = await self.bp_repo.update(tenant_id, existing.id, **data)
            await self.db.commit()
            await self._publish_event("business.updated", tenant_id, {"id": str(updated.id)})
            return updated
        else:
            created = await self.bp_repo.create(tenant_id, **data)
            await self.db.commit()
            await self._publish_event("business.updated", tenant_id, {"id": str(created.id)})
            return created

    # --- PRODUCTS & VARIANTS ---
    async def list_products(
        self,
        tenant_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> Sequence[Product]:
        self._check_permission(actor_permissions, "product.read")
        return await self.prod_repo.list_all(tenant_id, skip=skip, limit=limit)

    async def get_product(
        self,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> Product:
        self._check_permission(actor_permissions, "product.read")
        product = await self.prod_repo.get_by_id(tenant_id, product_id)
        if not product:
            raise AppException(
                code="PRODUCT_NOT_FOUND",
                message="Product not found.",
                status_code=404,
            )
        return product

    async def create_product(
        self,
        tenant_id: uuid.UUID,
        payload: ProductCreate,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> Product:
        self._check_permission(actor_permissions, "product.write")
        data = payload.model_dump()
        variants_data = data.pop("variants", None)
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")

        product = await self.prod_repo.create(tenant_id=tenant_id, **data)

        if variants_data:
            for v_item in variants_data:
                if "metadata" in v_item:
                    v_item["metadata_"] = v_item.pop("metadata")
                variant = ProductVariant(tenant_id=tenant_id, product_id=product.id, **v_item)
                self.db.add(variant)

        await self.db.commit()
        product = await self.prod_repo.get_by_id(tenant_id, product.id)
        await self._publish_event("product.created", tenant_id, {"id": str(product.id), "name": product.name})
        return product

    async def update_product(
        self,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        payload: ProductUpdate,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> Product:
        self._check_permission(actor_permissions, "product.write")
        product = await self.get_product(tenant_id, product_id, actor_permissions=actor_permissions)
        data = payload.model_dump(exclude_unset=True)
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")

        updated = await self.prod_repo.update(tenant_id, product.id, **data)
        await self.db.commit()
        updated = await self.prod_repo.get_by_id(tenant_id, product.id)
        await self._publish_event("product.updated", tenant_id, {"id": str(updated.id)})
        return updated

    async def delete_product(
        self,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> bool:
        self._check_permission(actor_permissions, "product.write")
        product = await self.get_product(tenant_id, product_id, actor_permissions=actor_permissions)
        await self.prod_repo.delete(tenant_id, product.id)
        await self.db.commit()
        await self._publish_event("product.deleted", tenant_id, {"id": str(product_id)})
        return True

    # --- PRODUCT VARIANTS ---
    async def create_product_variant(
        self,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        payload: ProductVariantCreate,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> ProductVariant:
        self._check_permission(actor_permissions, "product.write")
        product = await self.get_product(tenant_id, product_id, actor_permissions=actor_permissions)
        data = payload.model_dump()
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")

        variant = await self.variant_repo.create(
            tenant_id=tenant_id, product_id=product.id, **data
        )
        await self.db.commit()
        await self._publish_event(
            "product_variant.created", tenant_id, {"id": str(variant.id), "product_id": str(product.id)}
        )
        return variant

    async def update_product_variant(
        self,
        tenant_id: uuid.UUID,
        variant_id: uuid.UUID,
        payload: ProductVariantUpdate,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> ProductVariant:
        self._check_permission(actor_permissions, "product.write")
        variant = await self.variant_repo.get_by_id(tenant_id, variant_id)
        if not variant:
            raise AppException(
                code="VARIANT_NOT_FOUND",
                message="Product variant not found.",
                status_code=404,
            )
        data = payload.model_dump(exclude_unset=True)
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")

        updated = await self.variant_repo.update(tenant_id, variant.id, **data)
        await self.db.commit()
        await self._publish_event("product_variant.updated", tenant_id, {"id": str(updated.id)})
        return updated

    async def delete_product_variant(
        self,
        tenant_id: uuid.UUID,
        variant_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> bool:
        self._check_permission(actor_permissions, "product.write")
        variant = await self.variant_repo.get_by_id(tenant_id, variant_id)
        if not variant:
            raise AppException(
                code="VARIANT_NOT_FOUND",
                message="Product variant not found.",
                status_code=404,
            )
        await self.variant_repo.delete(tenant_id, variant.id)
        await self.db.commit()
        await self._publish_event("product_variant.deleted", tenant_id, {"id": str(variant_id)})
        return True

    # --- KNOWLEDGE SYSTEM ---
    async def list_knowledge_items(
        self,
        tenant_id: uuid.UUID,
        category_key: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> Sequence[KnowledgeItem]:
        self._check_permission(actor_permissions, "knowledge.read")
        return await self.know_repo.list_by_tenant(
            tenant_id, category_key=category_key, status=status, skip=skip, limit=limit
        )

    async def get_knowledge_item(
        self,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> KnowledgeItem:
        self._check_permission(actor_permissions, "knowledge.read")
        item = await self.know_repo.get_by_id(tenant_id, item_id)
        if not item:
            raise AppException(
                code="KNOWLEDGE_ITEM_NOT_FOUND",
                message="Knowledge item not found.",
                status_code=404,
            )
        return item

    async def create_knowledge_item(
        self,
        tenant_id: uuid.UUID,
        payload: KnowledgeItemCreate,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> KnowledgeItem:
        self._check_permission(actor_permissions, "knowledge.write")
        data = payload.model_dump()
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")

        item = await self.know_repo.create(tenant_id=tenant_id, **data)
        await self.db.commit()
        await self._publish_event("knowledge.created", tenant_id, {"id": str(item.id), "title": item.title})
        return item

    async def update_knowledge_item(
        self,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        payload: KnowledgeItemUpdate,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> KnowledgeItem:
        self._check_permission(actor_permissions, "knowledge.write")
        item = await self.get_knowledge_item(tenant_id, item_id, actor_permissions=actor_permissions)
        data = payload.model_dump(exclude_unset=True)
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")

        new_status = data.get("status")
        if new_status and new_status != item.status:
            allowed = VALID_KNOWLEDGE_TRANSITIONS.get(item.status, set())
            if new_status not in allowed:
                raise AppException(
                    code="INVALID_STATUS_TRANSITION",
                    message=f"Cannot transition knowledge status from '{item.status}' to '{new_status}'.",
                    status_code=400,
                )

        updated = await self.know_repo.update(tenant_id, item.id, **data)
        await self.db.commit()
        await self._publish_event("knowledge.updated", tenant_id, {"id": str(updated.id)})
        return updated

    async def approve_knowledge_item(
        self,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        approved_by: str | None = "owner",
        reason: str | None = "Manual business approval",
        actor_permissions: set[str] | list[str] | None = None,
    ) -> KnowledgeItem:
        self._check_permission(actor_permissions, "knowledge.approve")
        item = await self.get_knowledge_item(tenant_id, item_id, actor_permissions=actor_permissions)

        if item.status not in ("DRAFT", "VALIDATING"):
            raise AppException(
                code="INVALID_STATUS_TRANSITION",
                message=f"Cannot approve knowledge item in status '{item.status}'. Must be DRAFT or VALIDATING.",
                status_code=400,
            )

        updated = await self.know_repo.update(
            tenant_id,
            item.id,
            status="APPROVED",
            owner=approved_by,
        )
        await self.db.commit()
        await self._publish_event(
            "knowledge.approved", tenant_id, {"id": str(updated.id), "approved_by": approved_by}
        )
        return updated

    async def archive_knowledge_item(
        self,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> KnowledgeItem:
        self._check_permission(actor_permissions, "knowledge.write")
        item = await self.get_knowledge_item(tenant_id, item_id, actor_permissions=actor_permissions)

        updated = await self.know_repo.update(tenant_id, item.id, status="ARCHIVED")
        await self.db.commit()
        await self._publish_event("knowledge.archived", tenant_id, {"id": str(updated.id)})
        return updated
