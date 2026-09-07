import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import BaseAgent
from app.agents.base.schemas import AgentRequest, AgentResult, AgentRequestStatus
from app.agents.analyst.prompts import ANALYST_AGENT_SYSTEM_INSTRUCTION
from app.agents.analyst.schemas import AnalystOutputSchema, AnalyticsMetric, DataCategoryLabel
from app.agents.analyst.tools import (
    get_revenue_analytics_tool,
    get_order_analytics_tool,
    get_ai_usage_analytics_tool,
)

logger = logging.getLogger(__name__)


class AnalystAgent(BaseAgent):
    """AI Analyst Agent specializing in read-only business intelligence, trend analysis, and forecasting."""

    def __init__(self, ai_gateway=None, enabled: bool = True):
        super().__init__(
            name="ai_analyst",
            system_instruction=ANALYST_AGENT_SYSTEM_INSTRUCTION,
            ai_gateway=ai_gateway,
            enabled=enabled,
        )

    async def process_task(
        self,
        request: AgentRequest,
        db_session: AsyncSession,
    ) -> AgentResult:
        # 1. Fetch read-only analytics data
        rev_res = await self._execute_tool(
            "get_revenue_analytics",
            lambda tr: get_revenue_analytics_tool(tr, db_session),
            request,
            {},
        )
        order_res = await self._execute_tool(
            "get_order_analytics",
            lambda tr: get_order_analytics_tool(tr, db_session),
            request,
            {},
        )
        ai_res_tool = await self._execute_tool(
            "get_ai_usage_analytics",
            lambda tr: get_ai_usage_analytics_tool(tr, db_session),
            request,
            {},
        )

        analytics_data = {
            "revenue": rev_res.data if rev_res.success else {},
            "orders": order_res.data if order_res.success else {},
            "ai_usage": ai_res_tool.data if ai_res_tool.success else {},
        }

        # 2. Assemble safe minimum-necessary AI context & format prompt
        assembled_ctx, formatted_prompt = await self._assemble_agent_context(
            request, db_session, query_text=request.objective
        )

        user_message = (
            f"{formatted_prompt.full_prompt}\n\n"
            f"[TRUSTED HISTORICAL ANALYTICS DATA]\n{analytics_data}\n[/TRUSTED HISTORICAL ANALYTICS DATA]"
        )

        # 3. Call AIGateway
        ai_res, analyst_output = await self._call_ai_gateway(
            request,
            user_message,
            response_schema=AnalystOutputSchema,
            db_session=db_session,
        )

        if not analyst_output:
            rev_val = analytics_data.get("revenue", {}).get("total_revenue", 0.0)
            analyst_output = AnalystOutputSchema(
                finding=f"Historical total revenue: Rp{rev_val:,.2f}",
                metrics=[
                    AnalyticsMetric(
                        metric_name="total_revenue",
                        value=rev_val,
                        category_label=DataCategoryLabel.ACTUAL,
                    )
                ],
                evidence=[{"analytics": analytics_data}],
                recommendation="Continue tracking sales trend over next quarter.",
                confidence=0.90,
            )

        evidence_list = analyst_output.evidence or []
        evidence_list.append({"analytics_data": analytics_data})

        return AgentResult(
            request_id=request.request_id,
            agent=self.name,
            status=AgentRequestStatus.COMPLETED,
            finding=analyst_output.finding,
            evidence=evidence_list,
            recommendation=analyst_output.recommendation,
            confidence=analyst_output.confidence,
            actions=[],  # Read-only agent takes no direct database mutation actions
            needs_approval=False,
            correlation_id=request.correlation_id,
        )
