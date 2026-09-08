import uuid
from decimal import Decimal
from typing import Sequence
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    User,
    BusinessProfile,
    Product,
    ProductVariant,
    KnowledgeItem,
    Customer,
    Conversation,
    Message,
    Order,
    OrderItem,
    AIUsageRecord,
)
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_by_email(self, tenant_id: uuid.UUID, email: str) -> User | None:
        stmt = select(User).where(User.tenant_id == tenant_id, User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class BusinessProfileRepository(BaseRepository[BusinessProfile]):
    def __init__(self, session: AsyncSession):
        super().__init__(BusinessProfile, session)

    async def get_by_tenant(self, tenant_id: uuid.UUID) -> BusinessProfile | None:
        stmt = select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ProductRepository(BaseRepository[Product]):
    def __init__(self, session: AsyncSession):
        super().__init__(Product, session)

    async def get_by_id(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Product | None:
        stmt = select(Product).options(selectinload(Product.variants)).where(Product.tenant_id == tenant_id, Product.id == entity_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> Sequence[Product]:
        stmt = (
            select(Product)
            .options(selectinload(Product.variants))
            .where(Product.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_sku(self, tenant_id: uuid.UUID, sku: str) -> Product | None:
        stmt = (
            select(Product)
            .options(selectinload(Product.variants))
            .where(Product.tenant_id == tenant_id, Product.sku == sku)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search_by_name(self, tenant_id: uuid.UUID, query: str) -> Sequence[Product]:
        stmt = (
            select(Product)
            .options(selectinload(Product.variants))
            .where(
                Product.tenant_id == tenant_id,
                Product.name.ilike(f"%{query}%"),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()


class ProductVariantRepository(BaseRepository[ProductVariant]):
    def __init__(self, session: AsyncSession):
        super().__init__(ProductVariant, session)

    async def list_by_product(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> Sequence[ProductVariant]:
        stmt = select(ProductVariant).where(
            ProductVariant.tenant_id == tenant_id,
            ProductVariant.product_id == product_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_sku(self, tenant_id: uuid.UUID, sku: str) -> ProductVariant | None:
        stmt = select(ProductVariant).where(
            ProductVariant.tenant_id == tenant_id,
            ProductVariant.sku == sku,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class KnowledgeItemRepository(BaseRepository[KnowledgeItem]):
    def __init__(self, session: AsyncSession):
        super().__init__(KnowledgeItem, session)

    async def list_by_tenant(
        self,
        tenant_id: uuid.UUID,
        category_key: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[KnowledgeItem]:
        stmt = select(KnowledgeItem).where(KnowledgeItem.tenant_id == tenant_id)
        if category_key:
            stmt = stmt.where(KnowledgeItem.category_key == category_key)
        if status:
            stmt = stmt.where(KnowledgeItem.status == status)
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_active_and_approved(
        self, tenant_id: uuid.UUID, category_key: str | None = None
    ) -> Sequence[KnowledgeItem]:
        stmt = select(KnowledgeItem).where(
            KnowledgeItem.tenant_id == tenant_id,
            KnowledgeItem.status.in_(["APPROVED", "ACTIVE"]),
        )
        if category_key:
            stmt = stmt.where(KnowledgeItem.category_key == category_key)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def search_active_knowledge(
        self, tenant_id: uuid.UUID, query: str
    ) -> Sequence[KnowledgeItem]:
        stmt = select(KnowledgeItem).where(
            KnowledgeItem.tenant_id == tenant_id,
            KnowledgeItem.status.in_(["APPROVED", "ACTIVE"]),
            or_(
                KnowledgeItem.title.ilike(f"%{query}%"),
                KnowledgeItem.content.ilike(f"%{query}%"),
                KnowledgeItem.category_key.ilike(f"%{query}%"),
            ),
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()


class CustomerRepository(BaseRepository[Customer]):
    def __init__(self, session: AsyncSession):
        super().__init__(Customer, session)

    async def get_by_phone(self, tenant_id: uuid.UUID, phone: str) -> Customer | None:
        stmt = select(Customer).where(Customer.tenant_id == tenant_id, Customer.phone == phone)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_external_id(self, tenant_id: uuid.UUID, external_id: str) -> Customer | None:
        stmt = select(Customer).where(
            Customer.tenant_id == tenant_id, Customer.external_id == external_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ConversationRepository(BaseRepository[Conversation]):
    def __init__(self, session: AsyncSession):
        super().__init__(Conversation, session)

    async def get_by_external_id(
        self, tenant_id: uuid.UUID, external_conversation_id: str
    ) -> Conversation | None:
        stmt = select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.external_conversation_id == external_conversation_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_customer(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Conversation | None:
        stmt = (
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.customer_id == customer_id,
                Conversation.status.in_(["OPEN", "PENDING", "WAITING_HUMAN", "HUMAN_HANDLING"]),
            )
            .order_by(Conversation.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()


class MessageRepository(BaseRepository[Message]):
    def __init__(self, session: AsyncSession):
        super().__init__(Message, session)

    async def get_by_external_id(
        self, tenant_id: uuid.UUID, external_message_id: str
    ) -> Message | None:
        stmt = select(Message).where(
            Message.tenant_id == tenant_id,
            Message.external_message_id == external_message_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_conversation(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID, limit: int = 50
    ) -> Sequence[Message]:
        stmt = (
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()


class OrderRepository(BaseRepository[Order]):
    def __init__(self, session: AsyncSession):
        super().__init__(Order, session)

    async def get_by_id(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Order | None:
        stmt = (
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.tenant_id == tenant_id, Order.id == entity_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> Sequence[Order]:
        stmt = (
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_id_with_items(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Order | None:
        return await self.get_by_id(tenant_id, order_id)

    async def create_order_with_items(
        self,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID,
        currency: str,
        items_data: list[dict],
        metadata: dict | None = None,
    ) -> Order:
        subtotal = Decimal("0.00")
        order_items = []

        for item in items_data:
            product: Product = item["product"]
            qty: int = item["quantity"]
            unit_price = product.price
            item_subtotal = unit_price * qty
            subtotal += item_subtotal

            order_items.append(
                OrderItem(
                    tenant_id=tenant_id,
                    product_id=product.id,
                    product_name_snapshot=product.name,
                    unit_price=unit_price,
                    quantity=qty,
                    subtotal=item_subtotal,
                )
            )

        total = subtotal

        order = Order(
            tenant_id=tenant_id,
            customer_id=customer_id,
            status="PENDING",
            subtotal=subtotal,
            total=total,
            currency=currency,
            metadata_=metadata,
            items=order_items,
        )
        self.session.add(order)
        await self.session.flush()
        await self.session.refresh(order)
        return order


class AIUsageRepository(BaseRepository[AIUsageRecord]):
    def __init__(self, session: AsyncSession):
        super().__init__(AIUsageRecord, session)

    async def get_by_request_id(
        self, tenant_id: uuid.UUID, request_id: str
    ) -> AIUsageRecord | None:
        stmt = select(AIUsageRecord).where(
            AIUsageRecord.tenant_id == tenant_id,
            AIUsageRecord.request_id == request_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
