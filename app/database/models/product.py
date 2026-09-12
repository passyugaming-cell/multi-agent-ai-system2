import uuid
from decimal import Decimal
from typing import Any
from sqlalchemy import String, Text, Boolean, Numeric, Integer, ForeignKey, Index, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel


class Product(BaseModel):
    """Product entity representing catalog items or services owned by a tenant."""

    __tablename__ = "products"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="PRODUCT", nullable=False)  # PRODUCT or SERVICE
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="IDR", nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stock_status: Mapped[str | None] = mapped_column(String(50), default="IN_STOCK", nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), default="pcs", nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_products_tenant_id"),
        CheckConstraint("price >= 0", name="check_product_price_non_negative"),
        CheckConstraint("stock >= 0", name="check_product_stock_non_negative"),
        Index("idx_products_tenant_sku", "tenant_id", "sku"),
        Index("idx_products_tenant_name", "tenant_id", "name"),
    )


class ProductVariant(BaseModel):
    """ProductVariant entity representing SKUs/variants of a product."""

    __tablename__ = "product_variants"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price_override: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    product = relationship("Product", back_populates="variants")

    __table_args__ = (
        CheckConstraint("stock >= 0", name="check_product_variant_stock_non_negative"),
        Index("idx_product_variants_tenant_sku", "tenant_id", "sku"),
    )
