import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.ai_usage import AIUsageRecord
from app.database.models.conversation import Conversation
from app.analytics.schemas import AIAnalyticsSchema
from app.analytics.metrics import safe_decimal, determine_trend_direction


class AIAnalyticsService:
    """Service for computing AI Gateway and Agent performance analytics."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def get_ai_analytics(
        self,
        tenant_id: Optional[uuid.UUID] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> AIAnalyticsSchema:
        now = datetime.now(timezone.utc)
        if not period_end:
            period_end = now
        if not period_start:
            period_start = period_end - timedelta(days=30)

        period_duration = period_end - period_start
        prior_period_start = period_start - period_duration

        ai_filter = [AIUsageRecord.tenant_id == str(tenant_id)] if tenant_id else []

        # 1. Total Requests, Tokens, Cost, Latency
        stmt_summary = select(
            func.count(AIUsageRecord.id),
            func.coalesce(func.sum(AIUsageRecord.input_tokens), 0),
            func.coalesce(func.sum(AIUsageRecord.output_tokens), 0),
            func.coalesce(func.sum(AIUsageRecord.total_tokens), 0),
            func.coalesce(func.sum(AIUsageRecord.estimated_cost), Decimal("0.00")),
            func.coalesce(func.avg(AIUsageRecord.latency_ms), 0.0),
        ).where(
            and_(
                AIUsageRecord.created_at >= period_start,
                AIUsageRecord.created_at <= period_end,
                *ai_filter,
            )
        )
        res = (await self.session.execute(stmt_summary)).one()
        total_requests, in_tok, out_tok, tot_tok, total_cost, avg_lat = (
            res[0], res[1], res[2], res[3], safe_decimal(res[4]), float(res[5])
        )

        # 2. Prior period cost/tokens for trend
        stmt_prior = select(
            func.coalesce(func.sum(AIUsageRecord.total_tokens), 0),
            func.coalesce(func.sum(AIUsageRecord.estimated_cost), Decimal("0.00")),
        ).where(
            and_(
                AIUsageRecord.created_at >= prior_period_start,
                AIUsageRecord.created_at < period_start,
                *ai_filter,
            )
        )
        prior_res = (await self.session.execute(stmt_prior)).one()
        prior_tok, prior_cost = prior_res[0], safe_decimal(prior_res[1])

        usage_trend = determine_trend_direction(Decimal(tot_tok), Decimal(prior_tok))
        cost_trend = determine_trend_direction(total_cost, prior_cost)

        # 3. Success vs Failure rate
        stmt_success = select(
            AIUsageRecord.success,
            func.count(AIUsageRecord.id)
        ).where(
            and_(
                AIUsageRecord.created_at >= period_start,
                AIUsageRecord.created_at <= period_end,
                *ai_filter,
            )
        ).group_by(AIUsageRecord.success)

        succ_rows = (await self.session.execute(stmt_success)).all()
        succ_cnt = 0
        fail_cnt = 0
        for succ, cnt in succ_rows:
            if succ:
                succ_cnt += cnt
            else:
                fail_cnt += cnt

        total_succ_fail = succ_cnt + fail_cnt
        success_rate = round((succ_cnt / total_succ_fail * 100.0), 2) if total_succ_fail > 0 else 100.0
        failure_rate = round((fail_cnt / total_succ_fail * 100.0), 2) if total_succ_fail > 0 else 0.0

        # 4. Breakdown by Agent
        stmt_agent = select(
            AIUsageRecord.task_type,
            func.count(AIUsageRecord.id)
        ).where(
            and_(
                AIUsageRecord.created_at >= period_start,
                AIUsageRecord.created_at <= period_end,
                *ai_filter,
            )
        ).group_by(AIUsageRecord.task_type)
        agent_rows = (await self.session.execute(stmt_agent)).all()
        requests_by_agent = {task or "UNKNOWN": cnt for task, cnt in agent_rows}

        # 5. Breakdown by Model
        stmt_model = select(
            AIUsageRecord.model,
            func.count(AIUsageRecord.id)
        ).where(
            and_(
                AIUsageRecord.created_at >= period_start,
                AIUsageRecord.created_at <= period_end,
                *ai_filter,
            )
        ).group_by(AIUsageRecord.model)
        model_rows = (await self.session.execute(stmt_model)).all()
        requests_by_model = {model or "gemini-3.1-flash-lite": cnt for model, cnt in model_rows}

        # 6. Breakdown by Tenant (Platform query)
        requests_by_tenant = None
        if tenant_id is None:
            stmt_tenant = select(
                AIUsageRecord.tenant_id,
                func.count(AIUsageRecord.id)
            ).where(
                and_(
                    AIUsageRecord.created_at >= period_start,
                    AIUsageRecord.created_at <= period_end,
                )
            ).group_by(AIUsageRecord.tenant_id)
            tenant_rows = (await self.session.execute(stmt_tenant)).all()
            requests_by_tenant = {str(t_id or "system"): cnt for t_id, cnt in tenant_rows}

        # 7. AI Credits & Entitlement (1 credit per 1000 tokens)
        credits_used = (tot_tok + 999) // 1000 if tot_tok > 0 else 0

        # 8. AI Business Value Attribution (Labeled cleanly)
        stmt_convs = select(
            func.count(Conversation.id),
            func.coalesce(func.sum(case((Conversation.human_handoff.is_(True), 1), else_=0)), 0)
        )
        if tenant_id:
            stmt_convs = stmt_convs.where(Conversation.tenant_id == tenant_id)

        conv_res = (await self.session.execute(stmt_convs)).one()
        tot_convs, handoffs = conv_res[0], conv_res[1] or 0

        res_rate = round(((tot_convs - handoffs) / tot_convs * 100.0), 2) if tot_convs > 0 else 100.0
        handoff_rate = round((handoffs / tot_convs * 100.0), 2) if tot_convs > 0 else 0.0

        ai_business_value: Dict[str, Any] = {
            "ai_resolution_rate": res_rate,
            "human_handoff_rate": handoff_rate,
            "ai_assisted_conversations": tot_convs,
            "attribution_label": "assisted",  # assisted, attributed, correlated
            "explanation": "AI assisted in customer interaction routing and task automation."
        }

        return AIAnalyticsSchema(
            total_requests=total_requests,
            input_tokens=in_tok,
            output_tokens=out_tok,
            total_tokens=tot_tok,
            ai_credits_used=credits_used,
            ai_credits_remaining=max(0, 100000 - credits_used),
            ai_cost=total_cost,
            success_rate=success_rate,
            failure_rate=failure_rate,
            average_latency_ms=round(avg_lat, 2),
            requests_by_tenant=requests_by_tenant,
            requests_by_agent=requests_by_agent,
            requests_by_model=requests_by_model,
            cost_trend=cost_trend,
            usage_trend=usage_trend,
            usage_vs_entitlement_pct=min(100.0, round((credits_used / 100000.0 * 100.0), 2)),
            ai_business_value=ai_business_value,
            generated_at=now,
        )
