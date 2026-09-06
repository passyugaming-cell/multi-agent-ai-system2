import re
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import Product
from app.repositories.domain import ProductRepository


class DeterministicRouter:
    """Evaluates rules against database truth for deterministic operations."""

    PRICE_KEYWORDS = ["harga", "price", "berapa", "cost", "harganya"]
    STOCK_KEYWORDS = ["stok", "stock", "ada", "ready", "sisa", "tersedia"]
    HANDOFF_KEYWORDS = [
        "human", "agent", "admin", "cs", "customer service",
        "operator", "bantuan manusia", "hubungi cs", "bicara dengan cs",
        "human agent", "live agent", "bicarakan dengan cs"
    ]

    @staticmethod
    def is_price_query(text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in DeterministicRouter.PRICE_KEYWORDS)

    @staticmethod
    def is_stock_query(text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in DeterministicRouter.STOCK_KEYWORDS)

    @staticmethod
    def is_human_handoff_query(text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in DeterministicRouter.HANDOFF_KEYWORDS)

    @staticmethod
    async def match_product(
        tenant_id: uuid.UUID,
        query_text: str,
        session: AsyncSession,
    ) -> Optional[Product]:
        """Attempts to deterministically match a product in the database by SKU or name keywords."""
        product_repo = ProductRepository(session)
        products = await product_repo.list_all(tenant_id=tenant_id, limit=200)

        cleaned_text = query_text.lower()

        # 1. Match SKU if provided
        for product in products:
            if product.sku and product.sku.lower() in cleaned_text:
                return product

        # 2. Match exact or substring product name
        for product in products:
            if product.name and product.name.lower() in cleaned_text:
                return product

        # 3. Match individual words in product name
        for product in products:
            words = [w for w in product.name.lower().split() if len(w) > 2]
            if words and all(word in cleaned_text for word in words):
                return product

        return None
