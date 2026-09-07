import logging
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import BaseAgent
from app.agents.base.schemas import AgentRequest, AgentResult, AgentRequestStatus
from app.agents.sales.prompts import SALES_AGENT_SYSTEM_INSTRUCTION
from app.agents.sales.schemas import SalesOutputSchema
from app.agents.sales.tools import (
    get_products_tool,
    get_customer_conversation_tool,
    create_followup_task_tool,
    recommend_discount_tool,
)
from app.database.models.workflow import Approval

logger = logging.getLogger(__name__)


class SalesAgent(BaseAgent):
    """AI Sales Agent specializing in lead qualification, product recommendations, and follow-ups."""

    def __init__(self, ai_gateway=None, enabled: bool = True):
        super().__init__(
            name="ai_sales",
            system_instruction=SALES_AGENT_SYSTEM_INSTRUCTION,
            ai_gateway=ai_gateway,
            enabled=enabled,
        )

    async def process_task(
        self,
        request: AgentRequest,
        db_session: AsyncSession,
    ) -> AgentResult:
        # 1. Fetch DB product truth
        product_query = request.context.get("product_name") or request.objective
        products_tool_res = await self._execute_tool(
            "get_products",
            lambda tr: get_products_tool(tr, db_session),
            request,
            {"product_name": product_query},
        )

        db_products = products_tool_res.data if products_tool_res.success else []

        # 2. Fetch conversation if customer_id is provided
        customer_id = request.context.get("customer_id")
        conv_messages = []
        if customer_id:
            conv_tool_res = await self._execute_tool(
                "get_customer_conversation",
                lambda tr: get_customer_conversation_tool(tr, db_session),
                request,
                {"customer_id": customer_id},
            )
            if conv_tool_res.success:
                conv_messages = conv_tool_res.data

        # 3. Assemble safe minimum-necessary AI context & format prompt
        assembled_ctx, formatted_prompt = await self._assemble_agent_context(
            request, db_session, query_text=product_query
        )

        user_message = formatted_prompt.full_prompt

        # 4. Call AIGateway with structured output schema
        ai_res, sales_output = await self._call_ai_gateway(
            request,
            user_message,
            response_schema=SalesOutputSchema,
            db_session=db_session,
        )

        if not sales_output:
            # Fallback if structured output empty
            sales_output = SalesOutputSchema(
                finding="Analyzed inquiry based on product database.",
                evidence=[{"products": db_products}],
                recommendation="Provide catalog information to customer.",
                confidence=0.85,
            )

        # 5. Handle follow-up task creation if indicated
        actions_taken = []
        if sales_output.followup_task_needed:
            task_res = await self._execute_tool(
                "create_followup_task",
                lambda tr: create_followup_task_tool(tr, db_session),
                request,
                {
                    "title": sales_output.task_title or f"Follow-up: {request.objective[:30]}",
                    "description": sales_output.task_description or sales_output.recommendation,
                },
            )
            if task_res.success:
                actions_taken.append({"type": "create_task", "result": task_res.data})

        # 6. Handle discount & risk classification / Approval
        already_approved = bool(request.context.get("_already_approved"))
        needs_approval = sales_output.requires_approval and not already_approved
        approval_id = None
        status = AgentRequestStatus.COMPLETED

        if sales_output.proposed_discount_percent and sales_output.proposed_discount_percent > 0:
            disc_res = await self._execute_tool(
                "recommend_discount",
                lambda tr: recommend_discount_tool(tr, db_session),
                request,
                {
                    "discount_percent": sales_output.proposed_discount_percent,
                    "reason": sales_output.recommendation,
                },
            )
            if disc_res.success:
                actions_taken.append({"type": "recommend_discount", "result": disc_res.data})
                if disc_res.data.get("requires_approval") and not already_approved:
                    needs_approval = True

        if needs_approval:
            status = AgentRequestStatus.WAITING_APPROVAL
            if request.source != "workflow":
                approval_rec = Approval(
                    tenant_id=request.tenant_id,
                    requested_by="agent:ai_sales",
                    action_type="approve_discount",
                    target=str(request.context.get("customer_id") or "customer"),
                    reason=f"Proposed discount ({sales_output.proposed_discount_percent}%) requires approval.",
                    risk_level="HIGH",
                    status="PENDING",
                    evidence={"finding": sales_output.finding, "recommendation": sales_output.recommendation},
                )
                db_session.add(approval_rec)
                await db_session.flush()
                approval_id = str(approval_rec.id)

        evidence_list = sales_output.evidence or []
        evidence_list.append({"db_products": db_products})

        return AgentResult(
            request_id=request.request_id,
            agent=self.name,
            status=status,
            finding=sales_output.finding,
            evidence=evidence_list,
            recommendation=sales_output.recommendation,
            confidence=sales_output.confidence,
            actions=actions_taken,
            needs_approval=needs_approval,
            approval_id=approval_id,
            correlation_id=request.correlation_id,
        )
