import uuid
import logging
from datetime import datetime, timezone
from typing import Sequence, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.publisher import get_event_bus
from app.core.events.schemas import EventSchema
from app.core.exceptions import AppException
from app.database.models import BusinessProfile, Product, ProductVariant, KnowledgeItem
from app.database.models.workflow import Approval
from app.database.models.audit import ProvisioningAudit
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

logger = logging.getLogger(__name__)

# Valid Knowledge Lifecycle State Transitions via normal updates
VALID_KNOWLEDGE_TRANSITIONS = {
    "DRAFT": {"VALIDATING", "ARCHIVED"},
    "VALIDATING": {"DRAFT", "ARCHIVED"},
    "APPROVED": {"ACTIVE", "OUTDATED", "ARCHIVED", "DRAFT"},
    "ACTIVE": {"OUTDATED", "ARCHIVED", "DRAFT"},
    "OUTDATED": {"ACTIVE", "ARCHIVED", "DRAFT"},
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
        """Enforces strict fail-closed permission authorization."""
        if allow_internal:
            return
        if actor_permissions is None:
            raise AppException(
                code="PERMISSION_DENIED",
                message=f"Permission denied: missing {required_permission}",
                status_code=403,
            )
        perms_set = set(actor_permissions)
        if required_permission not in perms_set and "*" not in perms_set:
            raise AppException(
                code="PERMISSION_DENIED",
                message=f"Permission denied: missing {required_permission}",
                status_code=403,
            )

    async def _publish_event(self, event_type: str, tenant_id: uuid.UUID, payload: dict[str, Any]) -> None:
        """Publishes an event to EventBus with structured logging on failure."""
        try:
            event = EventSchema(
                event_id=f"evt_{uuid.uuid4().hex}",
                tenant_id=str(tenant_id),
                event_type=event_type,
                occurred_at=datetime.now(timezone.utc),
                payload=payload,
                source="business_service",
            )
            event_bus = get_event_bus()
            await event_bus.publish(event)
        except Exception as exc:
            logger.error(
                "Failed to publish EventBus event %s for tenant %s: %s",
                event_type,
                tenant_id,
                exc,
                exc_info=True,
            )

    async def _record_audit(
        self, tenant_id: uuid.UUID, action: str, details: dict[str, Any], actor: str | None = None
    ) -> None:
        """Records a provisioning audit record for business data mutations."""
        try:
            audit = ProvisioningAudit(
                tenant_id=tenant_id,
                action=action,
                actor=actor or "system",
                result="SUCCESS",
                metadata_info=details,
            )
            self.db.add(audit)
        except Exception as exc:
            logger.error("Failed to record audit for %s: %s", action, exc)

    def _validate_knowledge_transition(self, current_status: str, target_status: str) -> None:
        """Centralized validation for KnowledgeItem lifecycle state transitions."""
        if current_status == target_status:
            return
        allowed = VALID_KNOWLEDGE_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise AppException(
                code="INVALID_STATUS_TRANSITION",
                message=f"Cannot transition knowledge status from '{current_status}' to '{target_status}'. Allowed transitions: {sorted(list(allowed))}",
                status_code=400,
            )

    # --- BUSINESS PROFILE ---
    async def get_business_profile(
        self,
        tenant_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
        allow_internal: bool = False,
    ) -> BusinessProfile:
        self._check_permission(actor_permissions, "business.read", allow_internal=allow_internal)
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
        allow_internal: bool = False,
    ) -> BusinessProfile:
        self._check_permission(actor_permissions, "business.write", allow_internal=allow_internal)
        existing = await self.bp_repo.get_by_tenant(tenant_id)
        data = payload.model_dump(exclude_unset=True)

        if existing:
            updated = await self.bp_repo.update(tenant_id, existing.id, **data)
            await self._record_audit(tenant_id, "business_profile.updated", {"id": str(updated.id)})
            await self.db.commit()
            await self._publish_event("business.updated", tenant_id, {"id": str(updated.id)})
            return updated
        else:
            created = await self.bp_repo.create(tenant_id, **data)
            await self._record_audit(tenant_id, "business_profile.created", {"id": str(created.id)})
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
        allow_internal: bool = False,
    ) -> Sequence[Product]:
        self._check_permission(actor_permissions, "product.read", allow_internal=allow_internal)
        return await self.prod_repo.list_all(tenant_id, skip=skip, limit=limit)

    async def get_product(
        self,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
        allow_internal: bool = False,
    ) -> Product:
        self._check_permission(actor_permissions, "product.read", allow_internal=allow_internal)
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
        allow_internal: bool = False,
    ) -> Product:
        self._check_permission(actor_permissions, "product.write", allow_internal=allow_internal)
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

        await self._record_audit(tenant_id, "product.created", {"id": str(product.id), "name": product.name})
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
        allow_internal: bool = False,
    ) -> Product:
        self._check_permission(actor_permissions, "product.write", allow_internal=allow_internal)
        product = await self.get_product(tenant_id, product_id, actor_permissions=actor_permissions, allow_internal=allow_internal)
        data = payload.model_dump(exclude_unset=True)
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")

        updated = await self.prod_repo.update(tenant_id, product.id, **data)
        await self._record_audit(tenant_id, "product.updated", {"id": str(updated.id)})
        await self.db.commit()
        updated = await self.prod_repo.get_by_id(tenant_id, product.id)
        await self._publish_event("product.updated", tenant_id, {"id": str(updated.id)})
        return updated

    async def delete_product(
        self,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
        allow_internal: bool = False,
    ) -> bool:
        self._check_permission(actor_permissions, "product.write", allow_internal=allow_internal)
        product = await self.get_product(tenant_id, product_id, actor_permissions=actor_permissions, allow_internal=allow_internal)
        await self.prod_repo.delete(tenant_id, product.id)
        await self._record_audit(tenant_id, "product.deleted", {"id": str(product_id)})
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
        allow_internal: bool = False,
    ) -> ProductVariant:
        self._check_permission(actor_permissions, "product.write", allow_internal=allow_internal)
        product = await self.get_product(tenant_id, product_id, actor_permissions=actor_permissions, allow_internal=allow_internal)
        data = payload.model_dump()
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")

        variant = await self.variant_repo.create(
            tenant_id=tenant_id, product_id=product.id, **data
        )
        await self._record_audit(tenant_id, "product_variant.created", {"id": str(variant.id), "product_id": str(product.id)})
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
        allow_internal: bool = False,
    ) -> ProductVariant:
        self._check_permission(actor_permissions, "product.write", allow_internal=allow_internal)
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
        await self._record_audit(tenant_id, "product_variant.updated", {"id": str(updated.id)})
        await self.db.commit()
        await self._publish_event("product_variant.updated", tenant_id, {"id": str(updated.id)})
        return updated

    async def delete_product_variant(
        self,
        tenant_id: uuid.UUID,
        variant_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
        allow_internal: bool = False,
    ) -> bool:
        self._check_permission(actor_permissions, "product.write", allow_internal=allow_internal)
        variant = await self.variant_repo.get_by_id(tenant_id, variant_id)
        if not variant:
            raise AppException(
                code="VARIANT_NOT_FOUND",
                message="Product variant not found.",
                status_code=404,
            )
        await self.variant_repo.delete(tenant_id, variant.id)
        await self._record_audit(tenant_id, "product_variant.deleted", {"id": str(variant_id)})
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
        allow_internal: bool = False,
    ) -> Sequence[KnowledgeItem]:
        self._check_permission(actor_permissions, "knowledge.read", allow_internal=allow_internal)
        return await self.know_repo.list_by_tenant(
            tenant_id, category_key=category_key, status=status, skip=skip, limit=limit
        )

    async def get_knowledge_item(
        self,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
        allow_internal: bool = False,
    ) -> KnowledgeItem:
        self._check_permission(actor_permissions, "knowledge.read", allow_internal=allow_internal)
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
        allow_internal: bool = False,
    ) -> KnowledgeItem:
        self._check_permission(actor_permissions, "knowledge.write", allow_internal=allow_internal)
        data = payload.model_dump()
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")

        # BLOCKER 2 FIX: Prohibit direct creation of APPROVED or ACTIVE status. Always force DRAFT on creation.
        requested_status = data.get("status")
        if requested_status in ("APPROVED", "ACTIVE"):
            raise AppException(
                code="INVALID_STATUS_ON_CREATION",
                message=f"Cannot create knowledge item directly in status '{requested_status}'. Must be created as DRAFT.",
                status_code=400,
            )
        data["status"] = "DRAFT"
        data["version"] = 1
        data["approval_id"] = None

        item = await self.know_repo.create(tenant_id=tenant_id, **data)
        await self._record_audit(tenant_id, "knowledge.created", {"id": str(item.id), "title": item.title})
        await self.db.commit()
        await self._publish_event("knowledge.created", tenant_id, {"id": str(item.id), "title": item.title})
        return item

    async def update_knowledge_item(
        self,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        payload: KnowledgeItemUpdate,
        actor_permissions: set[str] | list[str] | None = None,
        allow_internal: bool = False,
    ) -> KnowledgeItem:
        self._check_permission(actor_permissions, "knowledge.write", allow_internal=allow_internal)
        item = await self.get_knowledge_item(tenant_id, item_id, actor_permissions=actor_permissions, allow_internal=allow_internal)
        data = payload.model_dump(exclude_unset=True)
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")

        # Disallow setting status to APPROVED directly via update
        if data.get("status") in ("APPROVED", "ACTIVE") and item.status in ("DRAFT", "VALIDATING"):
            raise AppException(
                code="APPROVAL_REQUIRED",
                message="Status 'APPROVED' or 'ACTIVE' can only be granted via the approval endpoint /approve",
                status_code=400,
            )

        # BLOCKER 7 & 8 FIX: Real Versioning and Re-approval Safety
        is_content_changed = any(
            k in data and data[k] != getattr(item, k, None)
            for k in ("title", "content", "category_key")
        )
        if is_content_changed:
            data["version"] = (item.version or 1) + 1
            if item.status in ("APPROVED", "ACTIVE"):
                # Content change MUST reset status to DRAFT and clear approval_id
                data["status"] = "DRAFT"
                data["approval_id"] = None

        # BLOCKER 6 FIX: Centralized status transition validation
        new_status = data.get("status")
        if new_status and new_status != item.status:
            self._validate_knowledge_transition(item.status, new_status)

        updated = await self.know_repo.update(tenant_id, item.id, **data)
        await self._record_audit(
            tenant_id,
            "knowledge.updated",
            {"id": str(updated.id), "version": updated.version, "status": updated.status},
        )
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
        allow_internal: bool = False,
    ) -> KnowledgeItem:
        self._check_permission(actor_permissions, "knowledge.approve", allow_internal=allow_internal)
        item = await self.get_knowledge_item(tenant_id, item_id, actor_permissions=actor_permissions, allow_internal=allow_internal)

        if item.status not in ("DRAFT", "VALIDATING"):
            raise AppException(
                code="INVALID_STATUS_TRANSITION",
                message=f"Cannot approve knowledge item in status '{item.status}'. Must be DRAFT or VALIDATING.",
                status_code=400,
            )

        # BLOCKER 3 FIX: Integration with existing ApprovalSystem
        now = datetime.now(timezone.utc)
        approval = Approval(
            tenant_id=tenant_id,
            requested_by=approved_by or "owner",
            action_type="knowledge.approve",
            target=f"knowledge:{item.id}",
            reason=reason or "Manual business knowledge approval",
            risk_level="HIGH",
            status="APPROVED",
            decided_by=approved_by or "owner",
            decided_at=now,
            meta_data={"title": item.title, "version": item.version},
        )
        self.db.add(approval)
        await self.db.flush()

        updated = await self.know_repo.update(
            tenant_id,
            item.id,
            status="APPROVED",
            owner=approved_by,
            approval_id=approval.id,
        )
        await self._record_audit(
            tenant_id,
            "knowledge.approved",
            {
                "id": str(updated.id),
                "approval_id": str(approval.id),
                "approved_by": approved_by,
                "reason": reason,
            },
            actor=approved_by,
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
        allow_internal: bool = False,
    ) -> KnowledgeItem:
        self._check_permission(actor_permissions, "knowledge.write", allow_internal=allow_internal)
        item = await self.get_knowledge_item(tenant_id, item_id, actor_permissions=actor_permissions, allow_internal=allow_internal)

        # BLOCKER 6 FIX: Validate archive transition centrally
        self._validate_knowledge_transition(item.status, "ARCHIVED")

        updated = await self.know_repo.update(tenant_id, item.id, status="ARCHIVED")
        await self._record_audit(tenant_id, "knowledge.archived", {"id": str(updated.id)})
        await self.db.commit()
        await self._publish_event("knowledge.archived", tenant_id, {"id": str(updated.id)})
        return updated
