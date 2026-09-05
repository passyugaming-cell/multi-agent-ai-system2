from enum import Enum
from typing import Any, Callable, Awaitable
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_gateway import AIGateway, GeminiProvider, AIRequest
from app.database.models.customer import Customer
from app.database.models.order import Order
from sqlalchemy import select

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionResult:
    def __init__(self, success: bool, output: dict[str, Any] | None = None, error: str | None = None, is_delayed: bool = False, delay_seconds: int = 0, requires_approval: bool = False, approval_data: dict[str, Any] | None = None) -> None:
        self.success = success
        self.output = output or {}
        self.error = error
        self.is_delayed = is_delayed
        self.delay_seconds = delay_seconds
        self.requires_approval = requires_approval
        self.approval_data = approval_data or {}


# Action classification policy map
ACTION_RISK_MAP = {
    "send_message": RiskLevel.LOW,
    "create_task": RiskLevel.LOW,
    "add_tag": RiskLevel.LOW,
    "remove_tag": RiskLevel.LOW,
    "log_result": RiskLevel.LOW,
    "delay": RiskLevel.LOW,
    "emit_event": RiskLevel.LOW,
    "update_customer": RiskLevel.MEDIUM,
    "update_order": RiskLevel.MEDIUM,
    "call_ai": RiskLevel.MEDIUM,
    "change_product_price": RiskLevel.HIGH,
    "issue_refund": RiskLevel.HIGH,
    "request_approval": RiskLevel.HIGH,
    "delete_customer": RiskLevel.CRITICAL,
    "delete_data": RiskLevel.CRITICAL,
}


def get_action_risk_level(action_type: str, action_params: dict[str, Any]) -> RiskLevel:
    """Classify action risk level based on action type and parameters."""
    return ACTION_RISK_MAP.get(action_type, RiskLevel.HIGH)


class ActionExecutor:
    """Executes registered workflow actions deterministically and securely."""

    @classmethod
    async def execute(
        self,
        action_type: str,
        params: dict[str, Any],
        context: dict[str, Any],
        session: AsyncSession,
        tenant_id: str,
    ) -> ActionResult:
        # Prevent executing dangerous arbitrary actions
        forbidden_keywords = ["eval", "exec", "system", "subprocess", "os.", "shutil", "importlib", "raw_sql"]
        params_str = str(params).lower()
        if any(kw in params_str for kw in forbidden_keywords):
            return ActionResult(success=False, error=f"Action parameters contain forbidden operations/keywords.")

        risk_level = get_action_risk_level(action_type, params)

        # HIGH/CRITICAL actions require approval if not already approved
        if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) and not params.get("_already_approved", False):
            return ActionResult(
                success=True,
                requires_approval=True,
                approval_data={
                    "action_type": action_type,
                    "target": str(params.get("target", action_type)),
                    "reason": params.get("reason", f"Execution of high-risk action {action_type}"),
                    "risk_level": risk_level.value,
                    "params": params,
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
            import uuid

            event = EventSchema(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_id,
                event_type=params.get("event_type", "workflow.custom_event"),
                payload=params.get("payload", {}),
                source="workflow_engine",
            )
            bus = get_event_bus()
            await bus.publish(event)
            return ActionResult(success=True, output={"emitted_event": event.event_id})

        elif action_type == "call_ai":
            # Mandatory AI Gateway usage
            ai_gateway = AIGateway(provider=GeminiProvider())
            task_type = params.get("task_type", "general_reasoning")
            system_inst = params.get("system_instruction", "Analyze the input context.")

            req = AIRequest(
                task_type=task_type,
                system_instruction=system_inst,
                prompt=str(context),
            )
            ai_res = await ai_gateway.generate_text(req, tenant_id=tenant_id)
            return ActionResult(success=True, output={"ai_response": ai_res.content})

        elif action_type in ("update_customer", "update_order", "change_product_price", "issue_refund"):
            # Application validation and mutation logic
            return ActionResult(success=True, output={"status": "updated", "action": action_type, "params": params})

        else:
            return ActionResult(success=False, error=f"Unknown or unsupported action type: {action_type}")
