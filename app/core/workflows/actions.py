from enum import Enum
from typing import Any
import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_gateway import AIGateway, GeminiProvider, AIRequest
from app.core.authority.schemas import ActionRequest, ExecutionDecision, ActionBinding
from app.core.authority.risk import RiskClassifier
from app.core.authority.service import ActionAuthorizationService
from app.core.context import get_actor_context

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionResult:
    def __init__(
        self,
        success: bool,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        is_delayed: bool = False,
        delay_seconds: int = 0,
        requires_approval: bool = False,
        approval_data: dict[str, Any] | None = None,
    ) -> None:
        self.success = success
        self.output = output or {}
        self.error = error
        self.is_delayed = is_delayed
        self.delay_seconds = delay_seconds
        self.requires_approval = requires_approval
        self.approval_data = approval_data or {}


def get_action_risk_level(action_type: str, action_params: dict[str, Any]) -> RiskLevel:
    """Classify action risk level using centralized RiskClassifier."""
    c_risk = RiskClassifier.classify(action_type, action_params)
    return RiskLevel(c_risk.value)


class ActionExecutor:
    """Executes registered workflow actions deterministically and securely."""

    @classmethod
    async def execute(
        cls,
        action_type: str,
        params: dict[str, Any],
        context: dict[str, Any],
        session: AsyncSession,
        tenant_id: str,
    ) -> ActionResult:
        # Prevent executing dangerous arbitrary operations
        forbidden_keywords = ["eval", "exec", "system", "subprocess", "os.", "shutil", "importlib", "raw_sql"]
        params_str = str(params).lower()
        if any(kw in params_str for kw in forbidden_keywords):
            return ActionResult(success=False, error="Action parameters contain forbidden operations/keywords.")

        tenant_uuid = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
        active_actor = get_actor_context()

        # Parse approval_id if passed in params or context
        approval_id_val = params.get("approval_id") or params.get("_approval_id") or context.get("approval_id")
        approval_uuid = None
        if approval_id_val:
            try:
                approval_uuid = approval_id_val if isinstance(approval_id_val, uuid.UUID) else uuid.UUID(str(approval_id_val))
            except (ValueError, TypeError):
                approval_uuid = None

        action_req = ActionRequest(
            action_type=action_type,
            target=str(params.get("target", action_type)),
            tenant_id=tenant_uuid,
            actor=active_actor,
            agent_id=params.get("agent_id") or context.get("agent_id"),
            params=params,
            approval_id=approval_uuid,
            correlation_id=params.get("correlation_id") or context.get("correlation_id"),
        )

        auth_service = ActionAuthorizationService(session)
        auth_decision = await auth_service.evaluate_action(action_req)

        if auth_decision.decision == ExecutionDecision.DENY:
            return ActionResult(success=False, error=auth_decision.reason)

        if auth_decision.decision == ExecutionDecision.WAITING_APPROVAL and not params.get("_already_approved", False):
            return ActionResult(
                success=True,
                requires_approval=True,
                approval_data={
                    "action_type": action_type,
                    "target": str(params.get("target", action_type)),
                    "reason": params.get("reason", f"Execution of {auth_decision.risk_level.value}-risk action {action_type}"),
                    "risk_level": auth_decision.risk_level.value,
                    "params": params,
                    "action_hash": auth_decision.action_hash,
                },
            )

        # Dispatch built-in actions
        if action_type == "send_message":
            msg = params.get("message", "Default message")
            return ActionResult(success=True, output={"sent_message": msg})

        elif action_type == "create_task":
            title = params.get("title", "Workflow Task")
            desc = params.get("description", "")
            return ActionResult(success=True, output={"task_created": title, "description": desc})

        elif action_type == "add_tag":
            tag = params.get("tag")
            tags = context.get("tags", [])
            if tag and tag not in tags:
                tags.append(tag)
            return ActionResult(success=True, output={"tags": tags})

        elif action_type == "remove_tag":
            tag = params.get("tag")
            tags = context.get("tags", [])
            if tag and tag in tags:
                tags.remove(tag)
            return ActionResult(success=True, output={"tags": tags})

        elif action_type == "delay":
            delay_sec = int(params.get("seconds", 0))
            return ActionResult(success=True, is_delayed=True, delay_seconds=delay_sec)

        elif action_type == "log_result":
            logger.info("Workflow Log Result: %s", params.get("message"))
            return ActionResult(success=True, output={"logged": params.get("message")})

        elif action_type == "emit_event":
            from app.core.events.publisher import get_event_bus
            from app.core.events.schemas import EventSchema

            event = EventSchema(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                tenant_id=str(tenant_uuid),
                event_type=params.get("event_type", "workflow.custom_event"),
                payload=params.get("payload", {}),
                source="workflow_engine",
            )
            bus = get_event_bus()
            await bus.publish(event)
            return ActionResult(success=True, output={"emitted_event": event.event_id})

        elif action_type == "call_ai":
            ai_gateway = AIGateway(provider=GeminiProvider())
            task_type = params.get("task_type", "general_reasoning")
            system_inst = params.get("system_instruction", "Analyze the input context.")

            req = AIRequest(
                tenant_id=tenant_uuid,
                task_type=task_type,
                system_instruction=system_inst,
                user_message=str(context),
            )
            ai_res = await ai_gateway.generate(req, db_session=session)
            return ActionResult(success=True, output={"ai_response": ai_res.text})

        elif action_type == "call_agent":
            from app.agents import agent_registry, AgentRequest, AgentRequestStatus

            target_agent = params.get("agent_name") or params.get("agent", "ai_sales")
            if target_agent == "owner_ai":
                return ActionResult(
                    success=False,
                    error="Workflows are strictly forbidden from targeting or executing Owner AI.",
                )
            task_type = params.get("task_type", "workflow_execution")
            objective = params.get("objective") or params.get("prompt", "Analyze workflow context")

            agent_context = dict(context)
            if params.get("_already_approved"):
                agent_context["_already_approved"] = True

            agent_req = AgentRequest(
                tenant_id=tenant_uuid,
                source="workflow",
                target_agent=target_agent,
                task_type=task_type,
                objective=objective,
                context=agent_context,
                constraints=params.get("constraints", {}),
                requested_action=params.get("requested_action"),
                correlation_id=params.get("correlation_id"),
            )

            agent_res = await agent_registry.delegate_task(agent_req, session)

            if not params.get("_already_approved") and (agent_res.needs_approval or agent_res.status == AgentRequestStatus.WAITING_APPROVAL):
                return ActionResult(
                    success=True,
                    requires_approval=True,
                    approval_data={
                        "action_type": "call_agent",
                        "target": target_agent,
                        "reason": agent_res.recommendation or f"Specialist agent {target_agent} requested approval.",
                        "risk_level": "HIGH",
                        "params": params,
                        "action_hash": ActionBinding.compute_hash(
                            action_type="call_agent",
                            target=target_agent,
                            tenant_id=tenant_uuid,
                            params=params,
                        ),
                    },
                )

            if agent_res.status == AgentRequestStatus.FAILED:
                return ActionResult(success=False, error=agent_res.error or "Agent execution failed.")

            return ActionResult(
                success=True,
                output={
                    "agent_result": agent_res.model_dump(mode="json"),
                    "finding": agent_res.finding,
                    "recommendation": agent_res.recommendation,
                    "status": agent_res.status.value,
                },
            )

        elif action_type == "whatsapp_send_message":
            from app.integrations import IntegrationService
            service = IntegrationService(session)
            conn = await service.get_connection_by_provider(tenant_uuid, "whatsapp_cloud_api", allow_internal=True) or await service.get_connection_by_provider(tenant_uuid, "whatsapp", allow_internal=True)
            if not conn:
                return ActionResult(success=False, error="WhatsApp integration connection not active")

            res = await service.execute_operation(
                tenant_id=tenant_uuid,
                connection_id=conn.id,
                operation="send_message",
                params=params,
                idempotency_key=params.get("idempotency_key"),
                allow_internal=True,
            )
            return ActionResult(success=res.status == "COMPLETED", output=res.result or {}, error=res.safe_error_message)

        elif action_type in ("midtrans_create_payment", "midtrans_check_status", "midtrans_cancel_payment", "midtrans_request_refund"):
            from app.integrations import IntegrationService
            from app.billing.payments import PaymentService
            service = IntegrationService(session)

            conn = await service.get_connection_by_provider(tenant_uuid, "midtrans", allow_internal=True)
            if not conn:
                return ActionResult(success=False, error="Midtrans integration connection not active")

            if action_type == "midtrans_check_status":
                order_id = params.get("order_id")
                if not order_id:
                    return ActionResult(success=False, error="order_id is required")
                res = await service.execute_operation(
                    tenant_id=tenant_uuid,
                    connection_id=conn.id,
                    operation="get_payment_status",
                    params={"order_id": str(order_id)},
                    allow_internal=True,
                )
                return ActionResult(success=res.status == "COMPLETED", output=res.result or {}, error=res.safe_error_message)

            elif action_type == "midtrans_create_payment":
                inv_id_str = params.get("invoice_id")
                if not inv_id_str:
                    return ActionResult(success=False, error="invoice_id is required")
                pay_srv = PaymentService(session)
                from app.billing.invoices import InvoiceService
                inv_srv = InvoiceService(session)
                inv = await inv_srv.get_invoice(tenant_uuid, uuid.UUID(str(inv_id_str)))
                pmt = await pay_srv.create_payment_intent(
                    tenant_id=tenant_uuid,
                    invoice_id=inv.id,
                    amount=inv.total,
                )
                return ActionResult(success=True, output={"payment_id": str(pmt.id), "status": pmt.status})

            elif action_type == "midtrans_cancel_payment":
                order_id = params.get("order_id")
                res = await service.execute_operation(
                    tenant_id=tenant_uuid,
                    connection_id=conn.id,
                    operation="cancel_payment",
                    params={"order_id": str(order_id)},
                    allow_internal=True,
                )
                return ActionResult(success=res.status == "COMPLETED", output=res.result or {}, error=res.safe_error_message)

            elif action_type == "midtrans_request_refund":
                order_id = params.get("order_id")
                amount = params.get("amount")
                res = await service.execute_operation(
                    tenant_id=tenant_uuid,
                    connection_id=conn.id,
                    operation="refund_payment",
                    params={"order_id": str(order_id), "amount": str(amount), "reason": params.get("reason", "Refund")},
                    allow_internal=True,
                )
                return ActionResult(success=res.status == "COMPLETED", output=res.result or {}, error=res.safe_error_message)

        elif action_type in ("execute_integration", "google_sheets_append", "google_sheets_update", "google_calendar_create_event"):
            from app.integrations import IntegrationService
            service = IntegrationService(session)
            conn_id_str = params.get("connection_id")
            if not conn_id_str:
                return ActionResult(success=False, error="Missing connection_id for integration action")

            try:
                conn_id = conn_id_str if isinstance(conn_id_str, uuid.UUID) else uuid.UUID(str(conn_id_str))
                if action_type == "google_calendar_create_event":
                    op = "create_event"
                elif action_type == "google_sheets_append":
                    op = "append_values"
                elif action_type == "google_sheets_update":
                    op = "update_values"
                else:
                    op = params.get("operation", "ping")

                res = await service.execute_operation(
                    tenant_id=tenant_uuid,
                    connection_id=conn_id,
                    operation=op,
                    params=params,
                    idempotency_key=params.get("idempotency_key"),
                    allow_internal=True,
                )
                if res.status == "COMPLETED":
                    return ActionResult(success=True, output=res.result or {})
                else:
                    return ActionResult(success=False, error=res.safe_error_message or "Integration action failed")
            except Exception as e:
                return ActionResult(success=False, error=str(e))

        elif action_type in ("update_customer", "update_order", "change_product_price", "issue_refund"):
            return ActionResult(success=True, output={"status": "updated", "action": action_type, "params": params})

        else:
            return ActionResult(success=False, error=f"Unknown or unsupported action type: {action_type}")
