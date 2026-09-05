from abc import ABC, abstractmethod
from datetime import datetime, timezone
import logging
import time
from typing import Any, Type
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_gateway import AIGateway, AIRequest, AIResponse
from app.database.models.agent import AgentExecution
from app.agents.base.schemas import (
    AgentRequest,
    AgentResult,
    AgentRequestStatus,
    ToolRequest,
    ToolResult,
)
from app.agents.base.exceptions import (
    AgentExecutionError,
    AgentValidationError,
    AgentPermissionError,
    ToolExecutionError,
)
from app.agents.base.permissions import check_tool_permission

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract Base Class for all Specialist AI Agents."""

    def __init__(
        self,
        name: str,
        system_instruction: str,
        ai_gateway: AIGateway | None = None,
        enabled: bool = True,
        max_retries: int = 1,
    ):
        self.name = name
        self.system_instruction = system_instruction
        self.ai_gateway = ai_gateway or AIGateway()
        self.enabled = enabled
        self.max_retries = max_retries

    @abstractmethod
    async def process_task(
        self,
        request: AgentRequest,
        db_session: AsyncSession,
    ) -> AgentResult:
        """Internal agent processing logic implemented by specialist subclasses."""
        pass

    async def run(
        self,
        request: AgentRequest,
        db_session: AsyncSession,
    ) -> AgentResult:
        """Controlled, audited execution interface for the agent."""
        if not self.enabled:
            return AgentResult(
                request_id=request.request_id,
                agent=self.name,
                status=AgentRequestStatus.BLOCKED,
                error=f"Agent '{self.name}' is currently disabled.",
                correlation_id=request.correlation_id,
            )

        start_time = time.time()
        result: AgentResult

        try:
            result = await self.process_task(request, db_session)
        except AgentValidationError as val_err:
            logger.warning("Agent %s validation failure for request %s: %s", self.name, request.request_id, val_err)
            result = AgentResult(
                request_id=request.request_id,
                agent=self.name,
                status=AgentRequestStatus.FAILED,
                error=f"Validation failure: {str(val_err)}",
                correlation_id=request.correlation_id,
            )
        except Exception as exc:
            logger.error("Agent %s unhandled error for request %s: %s", self.name, request.request_id, exc, exc_info=True)
            result = AgentResult(
                request_id=request.request_id,
                agent=self.name,
                status=AgentRequestStatus.FAILED,
                error=f"Agent execution error: {str(exc)}",
                correlation_id=request.correlation_id,
            )

        execution_time_ms = (time.time() - start_time) * 1000.0

        # Record persistent audit history
        try:
            execution_record = AgentExecution(
                tenant_id=request.tenant_id,
                request_id=request.request_id,
                agent_name=self.name,
                task_type=request.task_type,
                status=result.status.value,
                finding=result.finding,
                evidence=result.evidence,
                recommendation=result.recommendation,
                confidence=result.confidence,
                needs_approval=result.needs_approval,
                approval_id=result.approval_id,
                actions=result.actions,
                error=result.error,
                correlation_id=result.correlation_id or request.correlation_id,
                execution_time_ms=execution_time_ms,
            )
            db_session.add(execution_record)
            await db_session.flush()
        except Exception as audit_exc:
            logger.error("Failed to record AgentExecution audit for %s: %s", request.request_id, audit_exc)

        return result

    async def _call_ai_gateway(
        self,
        request: AgentRequest,
        user_message: str,
        response_schema: Type[BaseModel] | None = None,
        db_session: AsyncSession | None = None,
    ) -> tuple[AIResponse, Any | None]:
        """Calls central AIGateway with Pydantic structured output validation."""
        ai_request = AIRequest(
            tenant_id=request.tenant_id,
            task_type=f"{self.name}:{request.task_type}",
            system_instruction=self.system_instruction,
            user_message=user_message,
            context={
                "objective": request.objective,
                "context": request.context,
                "constraints": request.constraints,
                "requested_action": request.requested_action,
            },
            response_schema=response_schema,
        )

        attempts = 0
        last_error = None

        while attempts <= self.max_retries:
            attempts += 1
            try:
                ai_response = await self.ai_gateway.generate(ai_request, db_session=db_session)

                if response_schema and ai_response.structured_output is not None:
                    if isinstance(ai_response.structured_output, response_schema):
                        return ai_response, ai_response.structured_output
                    elif isinstance(ai_response.structured_output, dict):
                        validated = response_schema.model_validate(ai_response.structured_output)
                        return ai_response, validated

                return ai_response, ai_response.structured_output

            except ValidationError as val_err:
                last_error = f"Malformed structured AI output: {val_err}"
                logger.warning("AI output schema validation failed (attempt %d/%d): %s", attempts, self.max_retries + 1, val_err)
            except Exception as exc:
                last_error = str(exc)
                logger.warning("AIGateway call failed (attempt %d/%d): %s", attempts, self.max_retries + 1, exc)

        raise AgentValidationError(f"Structured AI output validation failed after {attempts} attempts: {last_error}")

    async def _execute_tool(
        self,
        tool_name: str,
        tool_func: Any,
        request: AgentRequest,
        parameters: dict[str, Any],
    ) -> ToolResult:
        """Executes a registered tool after permission and tenant isolation checks."""
        if not check_tool_permission(self.name, tool_name):
            raise AgentPermissionError(f"Agent '{self.name}' is not permitted to execute tool '{tool_name}'.")

        tool_request = ToolRequest(
            tool_name=tool_name,
            tenant_id=request.tenant_id,
            parameters=parameters,
            correlation_id=request.correlation_id,
        )

        try:
            tool_result = await tool_func(tool_request)
            return tool_result
        except Exception as exc:
            logger.error("Tool execution error for %s in agent %s: %s", tool_name, self.name, exc)
            return ToolResult(
                success=False,
                tool_name=tool_name,
                error=f"Tool execution failed: {str(exc)}",
                correlation_id=request.correlation_id,
            )
