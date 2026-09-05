from pydantic import BaseModel
from typing import Literal, Optional


class StructuredIntent(BaseModel):
    """Schema for AI intent classification and tool execution parameters."""

    intent: Literal["check_price", "check_stock", "create_order", "general_inquiry", "unknown"]
    confidence: float
    action: Optional[Literal["GET_PRODUCT_PRICE", "GET_PRODUCT_STOCK", "NONE"]] = "NONE"
    product_name_query: Optional[str] = None
    product_sku: Optional[str] = None
    product_id: Optional[str] = None
