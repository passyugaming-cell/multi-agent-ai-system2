import logging
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_gateway import AIGateway, AIRequest
from app.core.ai_gateway.prompts import (
    CUSTOMER_SERVICE_SYSTEM_PROMPT,
    INTENT_CLASSIFICATION_SYSTEM_PROMPT,
)
from app.core.router.intent import StructuredIntent
from app.core.router.deterministic import DeterministicRouter
from app.database.models import Conversation, Message, Product
from app.repositories.domain import (
    BusinessProfileRepository,
    ProductRepository,
    KnowledgeItemRepository,
)

logger = logging.getLogger("core.router")


class RouterResult:
    def __init__(
        self,
        response_text: str,
        was_ai_called: bool,
        handsoff_to_human: bool = False,
        matched_product: Optional[Product] = None,
    ):
        self.response_text = response_text
        self.was_ai_called = was_ai_called
        self.handsoff_to_human = handsoff_to_human
        self.matched_product = matched_product


class MessageRouter:
    """Deterministic-first router for tenant incoming messages."""

    def __init__(self, ai_gateway: Optional[AIGateway] = None):
        self.ai_gateway = ai_gateway or AIGateway()

    async def route_message(
        self,
        tenant_id: uuid.UUID,
        conversation: Conversation,
        message: Message,
        session: AsyncSession,
    ) -> RouterResult:
        # 1. Check Human Handoff / AI Enabled status
        if conversation.human_handoff or not conversation.ai_enabled:
            logger.info(
                f"Conversation {conversation.id} has human_handoff={conversation.human_handoff} / ai_enabled={conversation.ai_enabled}. AI disabled."
            )
            return RouterResult(
                response_text="[SYSTEM] Message logged for human agent.",
                was_ai_called=False,
                handsoff_to_human=True,
            )

        text = message.text or ""

        # Check explicit human handoff request from customer
        if DeterministicRouter.is_human_handoff_query(text):
            conversation.human_handoff = True
            conversation.status = "WAITING_HUMAN"
            return RouterResult(
                response_text="Pesan Anda telah diteruskan ke tim support kami. Mohon tunggu sejenak.",
                was_ai_called=False,
                handsoff_to_human=True,
            )

        # 2. Attempt Deterministic Matching (Price / Stock lookup)
        is_price = DeterministicRouter.is_price_query(text)
        is_stock = DeterministicRouter.is_stock_query(text)

        if is_price or is_stock:
            matched_product = await DeterministicRouter.match_product(
                tenant_id=tenant_id, query_text=text, session=session
            )
            if matched_product:
                if is_price and not is_stock:
                    return RouterResult(
                        response_text=f"Harga {matched_product.name} adalah Rp {matched_product.price:,.0f}.",
                        was_ai_called=False,
                        matched_product=matched_product,
                    )
                elif is_stock and not is_price:
                    return RouterResult(
                        response_text=f"Stok {matched_product.name} saat ini tersedia {matched_product.stock} unit.",
                        was_ai_called=False,
                        matched_product=matched_product,
                    )
                else:
                    return RouterResult(
                        response_text=f"Harga {matched_product.name} adalah Rp {matched_product.price:,.0f} dan stok tersedia {matched_product.stock} unit.",
                        was_ai_called=False,
                        matched_product=matched_product,
                    )

        # 3. Ambiguous Query -> Gemini Intent Classification
        try:
            intent_request = AIRequest(
                tenant_id=tenant_id,
                task_type="intent_classification",
                system_instruction=INTENT_CLASSIFICATION_SYSTEM_PROMPT,
                user_message=text,
                response_schema=StructuredIntent,
            )
            ai_intent_response = await self.ai_gateway.generate(
                request=intent_request, db_session=session
            )
            structured_intent: StructuredIntent = ai_intent_response.structured_output

            if structured_intent and structured_intent.action in [
                "GET_PRODUCT_PRICE",
                "GET_PRODUCT_STOCK",
            ]:
                query_name = (
                    structured_intent.product_name_query or structured_intent.product_sku or text
                )
                matched_product = await DeterministicRouter.match_product(
                    tenant_id=tenant_id, query_text=query_name, session=session
                )

                if matched_product:
                    if structured_intent.action == "GET_PRODUCT_PRICE":
                        reply = f"Harga {matched_product.name} adalah Rp {matched_product.price:,.0f}."
                    else:
                        reply = f"Stok {matched_product.name} tersedia {matched_product.stock} unit."

                    return RouterResult(
                        response_text=reply,
                        was_ai_called=True,
                        matched_product=matched_product,
                    )
        except Exception as exc:
            logger.warning(f"AI Intent classification failed or unavailable: {exc}")

        # 4. Fallback: Call Gemini for conversational assistance with assembled safe context
        try:
            from app.core.context_assembly import ContextAssemblyService, ContextAssemblyRequest

            assembly_service = ContextAssemblyService(session)
            assembled_ctx = await assembly_service.assemble_context(
                ContextAssemblyRequest(
                    tenant_id=tenant_id,
                    agent_name="customer_service",
                    task_type="customer_service_response",
                    query_text=text,
                    conversation_id=conversation.id,
                    customer_id=conversation.customer_id,
                )
            )

            formatted_prompt = ContextAssemblyService.format_prompt(
                assembled=assembled_ctx,
                user_message=text,
                system_instruction=CUSTOMER_SERVICE_SYSTEM_PROMPT,
            )

            gen_request = AIRequest(
                tenant_id=tenant_id,
                task_type="customer_service_response",
                system_instruction=CUSTOMER_SERVICE_SYSTEM_PROMPT,
                user_message=formatted_prompt.full_prompt,
                context={
                    "product_catalog": assembled_ctx.facts.get("product_catalog", []),
                    "business_profile": assembled_ctx.business_profile or {},
                    "approved_knowledge": assembled_ctx.knowledge,
                    "business_memory": assembled_ctx.business_memory,
                    "client_memory": assembled_ctx.client_memory,
                },
            )
            ai_response = await self.ai_gateway.generate(
                request=gen_request, db_session=session
            )
            return RouterResult(
                response_text=ai_response.text,
                was_ai_called=True,
            )
        except Exception as exc:
            logger.error(f"AI Response generation failed: {exc}")
            return RouterResult(
                response_text="Maaf, sistem kami sedang mengalami gangguan. Pesan Anda telah diteruskan ke tim support kami.",
                was_ai_called=False,
                handsoff_to_human=False,
            )
