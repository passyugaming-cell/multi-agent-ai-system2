import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.schemas import ToolRequest, ToolResult, AgentRequest
from app.agents.base.registry import agent_registry
from app.agents.owner_ai.health import BusinessHealthCalculator, ClientHealthCalculator
from app.agents.owner_ai.reports import ReportGenerator
from app.agents.owner_ai.recommendations import RecommendationService
from app.memory.service import MemoryService
from app.core.tasks.service import TaskService
from app.core.approvals.service import ApprovalService
from app.core.exceptions import AppError
from app.billing.subscription import SubscriptionService
from app.billing.usage import UsageService, UsageMetric
from app.billing.invoices import InvoiceService
from app.billing.payments import PaymentService
from app.analytics.services import AnalyticsService


async def tool_get_billing_summary(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        sub_service = SubscriptionService(db_session)
        usage_service = UsageService(db_session)
        invoice_service = InvoiceService(db_session)
        payment_service = PaymentService(db_session)

        sub = await sub_service.get_subscription_or_none(tenant_id)
        plan_code = sub.plan.code if sub and sub.plan else "unknown"
        status = sub.status if sub else "NONE"

        ai_credits_used = await usage_service.get_current_usage(tenant_id, UsageMetric.AI_CREDITS) if sub else 0
        ai_credits_limit = await usage_service.entitlement_resolver.get_limit(tenant_id, UsageMetric.AI_CREDITS) if sub else 0

        invoices = await invoice_service.list_invoices(tenant_id) if sub else []
        payments = await payment_service.list_payments(tenant_id) if sub else []

        data = {
            "subscription_status": status,
            "plan_code": plan_code,
            "billing_cycle": sub.billing_cycle if sub else None,
            "ai_credits_used": ai_credits_used,
            "ai_credits_limit": ai_credits_limit,
            "total_invoices": len(invoices),
            "total_payments": len(payments),
            "latest_invoice_status": invoices[0].status if invoices else None,
            "latest_payment_status": payments[0].status if payments else None,
        }

        return ToolResult(
            success=True,
            tool_name="get_billing_summary",
            data=data,
            evidence=[f"Billing summary read-only facts retrieved for plan {plan_code} ({status})."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_billing_summary",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_financial_summary(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        analytics = AnalyticsService(db_session)
        res = await analytics.financial.get_financial_analytics(tenant_id)
        return ToolResult(
            success=True,
            tool_name="get_financial_summary",
            data=res.model_dump(mode="json"),
            evidence=[f"Retrieved deterministic financial summary for revenue {res.total_revenue} IDR and MRR {res.mrr} IDR."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_financial_summary",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_client_summary(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        analytics = AnalyticsService(db_session)
        res = await analytics.clients.get_client_analytics(tenant_id)
        return ToolResult(
            success=True,
            tool_name="get_client_summary",
            data=res.model_dump(mode="json"),
            evidence=[f"Retrieved client summary for {res.active_clients} active clients."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_client_summary",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_sales_summary(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        analytics = AnalyticsService(db_session)
        res = await analytics.sales.get_sales_analytics(tenant_id)
        return ToolResult(
            success=True,
            tool_name="get_sales_summary",
            data=res.model_dump(mode="json"),
            evidence=[f"Retrieved sales analytics for {res.total_leads} leads with overall conversion {res.overall_conversion_rate}%."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_sales_summary",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_ai_summary(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        analytics = AnalyticsService(db_session)
        res = await analytics.ai.get_ai_analytics(tenant_id)
        return ToolResult(
            success=True,
            tool_name="get_ai_summary",
            data=res.model_dump(mode="json"),
            evidence=[f"Retrieved AI analytics for {res.total_requests} requests costing ${res.ai_cost}."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_ai_summary",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_automation_summary(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        analytics = AnalyticsService(db_session)
        res = await analytics.automation.get_automation_analytics(tenant_id)
        return ToolResult(
            success=True,
            tool_name="get_automation_summary",
            data=res.model_dump(mode="json"),
            evidence=[f"Retrieved automation analytics for {res.workflow_executions} executions with success rate {res.success_rate}%."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_automation_summary",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_subscription_summary(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        analytics = AnalyticsService(db_session)
        res = await analytics.subscriptions.get_subscription_analytics(tenant_id)
        return ToolResult(
            success=True,
            tool_name="get_subscription_summary",
            data=res.model_dump(mode="json"),
            evidence=[f"Retrieved subscription analytics for {res.active_subscriptions} active subscriptions."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_subscription_summary",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_kpis(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        analytics = AnalyticsService(db_session)
        period = request.parameters.get("period", "30d")
        res = await analytics.kpi.get_kpis(tenant_id, period)
        return ToolResult(
            success=True,
            tool_name="get_kpis",
            data=[kpi.model_dump(mode="json") for kpi in res],
            evidence=[f"Retrieved {len(res)} core KPIs."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_kpis",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_trends(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        analytics = AnalyticsService(db_session)
        period_days = int(request.parameters.get("period_days", 30))
        res = await analytics.trends.detect_trends(tenant_id, period_days)
        return ToolResult(
            success=True,
            tool_name="get_trends",
            data=[t.model_dump(mode="json") for t in res],
            evidence=[f"Retrieved trend analysis for {len(res)} metrics."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_trends",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_anomalies(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        analytics = AnalyticsService(db_session)
        period_days = int(request.parameters.get("period_days", 30))
        res = await analytics.anomalies.detect_anomalies(tenant_id, period_days)
        return ToolResult(
            success=True,
            tool_name="get_anomalies",
            data=[a.model_dump(mode="json") for a in res],
            evidence=[f"Retrieved {len(res)} anomaly signals."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_anomalies",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_forecast(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        analytics = AnalyticsService(db_session)
        period_days = int(request.parameters.get("period_days", 30))
        res = await analytics.forecasting.generate_forecasts(tenant_id, period_days)
        return ToolResult(
            success=True,
            tool_name="get_forecast",
            data=[f.model_dump(mode="json") for f in res],
            evidence=[f"Generated forecast projections for {len(res)} key metrics."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_forecast",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_evaluate_business_health(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        res = await BusinessHealthCalculator.calculate(db_session, request.tenant_id)
        return ToolResult(
            success=True,
            tool_name="evaluate_business_health",
            data=res.model_dump(mode="json"),
            evidence=[f"Business Health Score calculated as {res.score} based on DB metrics."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="evaluate_business_health",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_evaluate_client_health(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        res = await ClientHealthCalculator.calculate(db_session, request.tenant_id)
        return ToolResult(
            success=True,
            tool_name="evaluate_client_health",
            data=res.model_dump(mode="json"),
            evidence=[f"Client Health Score calculated as {res.score} ({res.category})."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="evaluate_client_health",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_memory_context(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        objective = request.parameters.get("objective", "")
        mem_service = MemoryService(db_session)
        ctx = await mem_service.get_relevant_context(request.tenant_id, objective)
        return ToolResult(
            success=True,
            tool_name="get_memory_context",
            data=ctx.model_dump(mode="json"),
            evidence=[f"Retrieved {len(ctx.business_memories)} business and {len(ctx.client_memories)} client memories."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_memory_context",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_delegate_task_to_agent(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        target_agent = request.parameters.get("target_agent")
        task_type = request.parameters.get("task_type", "general_task")
        objective = request.parameters.get("objective", "")
        context = request.parameters.get("context", {})
        delegation_depth = request.parameters.get("delegation_depth", 0)

        agent_req = AgentRequest(
            tenant_id=request.tenant_id,
            source="owner_ai",
            source_agent="owner_ai",
            target_agent=target_agent,
            task_type=task_type,
            objective=objective,
            context=context,
            correlation_id=request.correlation_id,
            delegation_depth=delegation_depth,
        )

        agent_res = await agent_registry.delegate_task(agent_req, db_session)
        return ToolResult(
            success=agent_res.status.value not in ("FAILED", "BLOCKED"),
            tool_name="delegate_task_to_agent",
            data=agent_res.model_dump(mode="json"),
            evidence=agent_res.evidence,
            error=agent_res.error,
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="delegate_task_to_agent",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_create_orchestration_task(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        task_service = TaskService(db_session)
        task = await task_service.create_task(
            tenant_id=request.tenant_id,
            title=request.parameters.get("title", "Owner AI Task"),
            description=request.parameters.get("description"),
            task_type=request.parameters.get("task_type", "orchestration"),
            priority=request.parameters.get("priority", "NORMAL"),
            assigned_agent=request.parameters.get("assigned_agent"),
            source="owner_ai",
        )
        return ToolResult(
            success=True,
            tool_name="create_orchestration_task",
            data={"task_id": str(task.id), "status": task.status, "title": task.title},
            evidence=[f"Created task '{task.title}' assigned to {task.assigned_agent}."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="create_orchestration_task",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_generate_daily_brief(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        analytics = AnalyticsService(db_session)
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        brief = await analytics.reports.generate_daily_brief(tenant_id)
        return ToolResult(
            success=True,
            tool_name="generate_daily_brief",
            data=brief.model_dump(mode="json"),
            evidence=["Daily Business Brief generated successfully based on deterministic analytics."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="generate_daily_brief",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_generate_weekly_review(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        analytics = AnalyticsService(db_session)
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        review = await analytics.reports.generate_weekly_review(tenant_id)
        return ToolResult(
            success=True,
            tool_name="generate_weekly_review",
            data=review.model_dump(mode="json"),
            evidence=["Weekly Strategic Review generated successfully based on deterministic analytics."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="generate_weekly_review",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_execute_integration_operation(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        from app.integrations import IntegrationService
        service = IntegrationService(db_session)
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        conn_id_str = request.parameters.get("connection_id")
        operation = request.parameters.get("operation")
        params = request.parameters.get("params", {})

        if not conn_id_str or not operation:
            return ToolResult(
                success=False,
                tool_name="execute_integration_operation",
                error="connection_id and operation are required parameters",
                correlation_id=request.correlation_id,
            )

        conn_id = uuid.UUID(str(conn_id_str))
        res = await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=conn_id,
            operation=operation,
            params=params,
            idempotency_key=request.parameters.get("idempotency_key"),
            allow_internal=True,
        )

        return ToolResult(
            success=res.status == "COMPLETED",
            tool_name="execute_integration_operation",
            data=res.result or {},
            error=res.safe_error_message,
            evidence=[f"Executed integration operation '{operation}' with status {res.status}"],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="execute_integration_operation",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_onboarding_status(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    """Read-only tool for Owner AI to inspect tenant onboarding checklist, readiness score, and blocking items."""
    try:
        from app.tenants.onboarding_service import OnboardingService
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        service = OnboardingService(db_session)
        summary = await service.get_onboarding_summary(tenant_id)

        data = {
            "lifecycle_state": summary.lifecycle_state,
            "readiness_score": summary.readiness_score,
            "readiness_status": summary.readiness_status,
            "blocking_items": summary.blocking_items,
            "warnings": summary.warnings,
            "checklist_summary": summary.checklist_summary.model_dump(mode="json"),
        }

        return ToolResult(
            success=True,
            tool_name="get_onboarding_status",
            data=data,
            evidence=[f"Retrieved read-only onboarding summary with readiness score {summary.readiness_score}%."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_onboarding_status",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_whatsapp_connection_status(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    """Read-only tool for Owner AI to inspect WhatsApp Cloud API connection status without direct mutation capability."""
    try:
        from app.integrations import IntegrationService
        service = IntegrationService(db_session)
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id

        conn = await service.get_connection_by_provider(tenant_id, "whatsapp_cloud_api", allow_internal=True) or await service.get_connection_by_provider(tenant_id, "whatsapp", allow_internal=True)

        if not conn:
            data = {
                "is_connected": False,
                "status": "DISCONNECTED",
                "phone_number_id": None,
            }
        else:
            data = {
                "is_connected": conn.status in ("ACTIVE", "CONNECTED"),
                "status": conn.status,
                "connection_id": str(conn.id),
                "external_account_id": conn.external_account_id,
                "last_connected_at": conn.last_connected_at.isoformat() if conn.last_connected_at else None,
                "last_error_at": conn.last_error_at.isoformat() if conn.last_error_at else None,
            }

        return ToolResult(
            success=True,
            tool_name="get_whatsapp_connection_status",
            data=data,
            evidence=["Retrieved read-only WhatsApp Cloud API connection status."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_whatsapp_connection_status",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_sheets_connection_status(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    """Read-only tool for Owner AI to inspect Google Sheets connection status without direct mutation capability."""
    try:
        from app.integrations import IntegrationService
        service = IntegrationService(db_session)
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id

        conn = await service.get_connection_by_provider(tenant_id, "google_sheets", allow_internal=True)

        if not conn:
            data = {
                "is_connected": False,
                "status": "DISCONNECTED",
                "connection_id": None,
            }
        else:
            data = {
                "is_connected": conn.status in ("ACTIVE", "CONNECTED"),
                "status": conn.status,
                "connection_id": str(conn.id),
                "external_account_id": conn.external_account_id,
                "last_connected_at": conn.last_connected_at.isoformat() if conn.last_connected_at else None,
                "last_error_at": conn.last_error_at.isoformat() if conn.last_error_at else None,
            }

        return ToolResult(
            success=True,
            tool_name="get_sheets_connection_status",
            data=data,
            evidence=["Retrieved read-only Google Sheets connection status."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_sheets_connection_status",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_midtrans_payment_status(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    """Read-only tool for Owner AI to inspect Midtrans payment status without direct mutation capability."""
    try:
        from app.integrations import IntegrationService
        from app.billing.payments import PaymentService
        tenant_id = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
        payment_id_str = request.parameters.get("payment_id")

        pay_service = PaymentService(db_session)
        if payment_id_str:
            pmt = await pay_service.get_payment(tenant_id, uuid.UUID(str(payment_id_str)))
            if not pmt:
                return ToolResult(
                    success=False,
                    tool_name="get_midtrans_payment_status",
                    error="Payment not found for tenant",
                    correlation_id=request.correlation_id,
                )
            data = {
                "payment_id": str(pmt.id),
                "invoice_id": str(pmt.invoice_id),
                "status": pmt.status,
                "amount": str(pmt.amount),
                "provider_payment_id": pmt.provider_payment_id,
            }
        else:
            payments = await pay_service.list_payments(tenant_id)
            data = {
                "total_payments": len(payments),
                "recent_payments": [
                    {
                        "payment_id": str(p.id),
                        "status": p.status,
                        "amount": str(p.amount),
                        "provider_payment_id": p.provider_payment_id,
                    }
                    for p in payments[:5]
                ],
            }

        return ToolResult(
            success=True,
            tool_name="get_midtrans_payment_status",
            data=data,
            evidence=["Retrieved read-only Midtrans payment status information."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_midtrans_payment_status",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_create_recommendation(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        rec_service = RecommendationService(db_session)
        rec = await rec_service.create_recommendation(
            tenant_id=request.tenant_id,
            title=request.parameters.get("title", ""),
            problem=request.parameters.get("problem", ""),
            reasoning_summary=request.parameters.get("reasoning_summary", ""),
            expected_benefit=request.parameters.get("expected_benefit", ""),
            suggested_action=request.parameters.get("suggested_action", ""),
            evidence=request.parameters.get("evidence", []),
            risk=request.parameters.get("risk", "LOW"),
            confidence=request.parameters.get("confidence", 1.0),
            required_approval=request.parameters.get("required_approval", False),
            priority=request.parameters.get("priority", "NORMAL"),
        )
        return ToolResult(
            success=True,
            tool_name="create_recommendation",
            data=rec.model_dump(mode="json"),
            evidence=[f"Created recommendation '{rec.title}' with status PROPOSED."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="create_recommendation",
            error=str(exc),
            correlation_id=request.correlation_id,
        )
