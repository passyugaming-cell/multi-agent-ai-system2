from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --- USER SCHEMAS ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    is_active: bool = True


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    email: EmailStr
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- BUSINESS PROFILE SCHEMAS ---
class BusinessProfileCreate(BaseModel):
    business_name: str
    business_type: str | None = None
    description: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    address: str | None = None
    city: str | None = None
    province: str | None = None
    country: str | None = None
    operating_hours: dict[str, Any] | list[Any] | None = None
    payment_methods: dict[str, Any] | list[Any] | None = None
    bank_accounts: dict[str, Any] | list[Any] | None = None
    shipping_information: dict[str, Any] | list[Any] | None = None
    courier_methods: dict[str, Any] | list[Any] | None = None
    return_policy: str | None = None
    exchange_policy: str | None = None
    refund_policy: str | None = None
    contact_admin_info: dict[str, Any] | list[Any] | None = None


class BusinessProfileUpdate(BaseModel):
    business_name: str | None = None
    business_type: str | None = None
    description: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    address: str | None = None
    city: str | None = None
    province: str | None = None
    country: str | None = None
    operating_hours: dict[str, Any] | list[Any] | None = None
    payment_methods: dict[str, Any] | list[Any] | None = None
    bank_accounts: dict[str, Any] | list[Any] | None = None
    shipping_information: dict[str, Any] | list[Any] | None = None
    courier_methods: dict[str, Any] | list[Any] | None = None
    return_policy: str | None = None
    exchange_policy: str | None = None
    refund_policy: str | None = None
    contact_admin_info: dict[str, Any] | list[Any] | None = None


class BusinessProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    business_name: str
    business_type: str | None
    description: str | None
    phone: str | None
    email: str | None
    website: str | None
    address: str | None
    city: str | None
    province: str | None
    country: str | None
    operating_hours: dict[str, Any] | list[Any] | None
    payment_methods: dict[str, Any] | list[Any] | None
    bank_accounts: dict[str, Any] | list[Any] | None
    shipping_information: dict[str, Any] | list[Any] | None
    courier_methods: dict[str, Any] | list[Any] | None
    return_policy: str | None
    exchange_policy: str | None
    refund_policy: str | None
    contact_admin_info: dict[str, Any] | list[Any] | None
    created_at: datetime
    updated_at: datetime


# --- PRODUCT & VARIANT SCHEMAS ---
class ProductVariantCreate(BaseModel):
    name: str
    sku: str | None = None
    price_override: Decimal | None = Field(None, ge=0)
    stock: int = Field(0, ge=0)
    is_active: bool = True
    metadata: dict[str, Any] | None = None


class ProductVariantUpdate(BaseModel):
    name: str | None = None
    sku: str | None = None
    price_override: Decimal | None = Field(None, ge=0)
    stock: int | None = Field(None, ge=0)
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


class ProductVariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    product_id: UUID
    name: str
    sku: str | None
    price_override: Decimal | None
    stock: int
    is_active: bool
    metadata: dict[str, Any] | None = Field(None, alias="metadata_")
    created_at: datetime
    updated_at: datetime


class ProductCreate(BaseModel):
    name: str
    type: str = "PRODUCT"  # PRODUCT or SERVICE
    description: str | None = None
    sku: str | None = None
    category: str | None = None
    price: Decimal = Field(..., ge=0)
    currency: str = "IDR"
    stock: int = Field(0, ge=0)
    stock_status: str | None = "IN_STOCK"
    unit: str | None = "pcs"
    is_active: bool = True
    metadata: dict[str, Any] | None = None
    variants: list[ProductVariantCreate] | None = None


class ProductUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    description: str | None = None
    sku: str | None = None
    category: str | None = None
    price: Decimal | None = Field(None, ge=0)
    currency: str | None = None
    stock: int | None = Field(None, ge=0)
    stock_status: str | None = None
    unit: str | None = None
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    type: str
    description: str | None
    sku: str | None
    category: str | None
    price: Decimal
    currency: str
    stock: int
    stock_status: str | None
    unit: str | None
    is_active: bool
    metadata: dict[str, Any] | None = Field(None, alias="metadata_")
    variants: list[ProductVariantResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# --- KNOWLEDGE SCHEMAS ---
class KnowledgeItemCreate(BaseModel):
    category_key: str = "OTHER"
    title: str
    content: str
    status: str = "DRAFT"  # DRAFT, VALIDATING, APPROVED, ACTIVE, OUTDATED, ARCHIVED
    source: str | None = None
    owner: str | None = None
    effective_at: datetime | None = None
    expiry_at: datetime | None = None
    confidence: float | None = None
    metadata: dict[str, Any] | None = None


class KnowledgeItemUpdate(BaseModel):
    category_key: str | None = None
    title: str | None = None
    content: str | None = None
    status: str | None = None
    source: str | None = None
    owner: str | None = None
    effective_at: datetime | None = None
    expiry_at: datetime | None = None
    confidence: float | None = None
    metadata: dict[str, Any] | None = None


class KnowledgeItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    category_key: str
    title: str
    content: str
    status: str
    source: str | None
    owner: str | None
    version: int
    effective_at: datetime | None
    expiry_at: datetime | None
    approval_id: UUID | None
    confidence: float | None
    metadata: dict[str, Any] | None = Field(None, alias="metadata_")
    created_at: datetime
    updated_at: datetime


class KnowledgeItemApproveRequest(BaseModel):
    approved_by: str | None = "owner"
    reason: str | None = "Manual business approval"


# --- CUSTOMER SCHEMAS ---
class CustomerCreate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    external_id: str | None = None
    metadata: dict[str, Any] | None = None


class CustomerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    external_id: str | None = None
    metadata: dict[str, Any] | None = None


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str | None
    phone: str | None
    email: str | None
    external_id: str | None
    metadata: dict[str, Any] | None = Field(None, alias="metadata_")
    created_at: datetime
    updated_at: datetime


# --- CONVERSATION & MESSAGE SCHEMAS ---
class ConversationCreate(BaseModel):
    customer_id: UUID
    channel: str = "whatsapp"
    external_conversation_id: str | None = None
    status: str = "OPEN"
    assigned_user_id: UUID | None = None
    human_handoff: bool = False
    ai_enabled: bool = True
    summary: str | None = None


class ConversationUpdate(BaseModel):
    status: str | None = None
    assigned_user_id: UUID | None = None
    human_handoff: bool | None = None
    ai_enabled: bool | None = None
    summary: str | None = None


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    customer_id: UUID
    channel: str
    external_conversation_id: str | None
    status: str
    assigned_user_id: UUID | None
    human_handoff: bool
    ai_enabled: bool
    summary: str | None
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    conversation_id: UUID
    direction: str  # INBOUND / OUTBOUND
    message_type: str = "TEXT"
    text: str | None = None
    external_message_id: str | None = None
    metadata: dict[str, Any] | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    direction: str
    message_type: str
    text: str | None
    external_message_id: str | None
    metadata: dict[str, Any] | None = Field(None, alias="metadata_")
    created_at: datetime
    updated_at: datetime


# --- ORDER SCHEMAS ---
class OrderItemCreate(BaseModel):
    product_id: UUID | None = None
    quantity: int = Field(..., gt=0)


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    order_id: UUID
    product_id: UUID | None
    product_name_snapshot: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal
    created_at: datetime
    updated_at: datetime


class OrderCreate(BaseModel):
    customer_id: UUID
    currency: str = "IDR"
    metadata: dict[str, Any] | None = None
    items: list[OrderItemCreate]


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    customer_id: UUID
    status: str
    subtotal: Decimal
    total: Decimal
    currency: str
    metadata: dict[str, Any] | None = Field(None, alias="metadata_")
    items: list[OrderItemResponse]
    created_at: datetime
    updated_at: datetime
