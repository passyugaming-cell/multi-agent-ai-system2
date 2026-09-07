import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import BaseAgent
from app.agents.base.schemas import AgentRequest, AgentResult, AgentRequestStatus
from app.agents.client_manager.prompts import CLIENT_MANAGER_SYSTEM_INSTRUCTION
from app.agents.client_manager.schemas import ClientManagerOutputSchema
from app.agents.client_manager.tools import (
    get_client_onboarding_state_tool,
    calculate_readiness_tool,
    create_onboarding_task_tool,
    recommend_configuration_tool,
)
from app.database.models.workflow import Approval

logger = logging.getLogger(__name__)


class ClientManagerAgent(BaseAgent):
    """AI Client Manager Agent specializing in tenant onboarding and readiness monitoring."""

    def __init__(self, ai_gateway=None, enabled: bool = True):
        super().__init__(
            name="ai_client_manager",
            system_instruction=CLIENT_MANAGER_SYSTEM_INSTRUCTION,
            ai_gateway=ai_gateway,
            enabled=enabled,
        )

    async def process_task(
        self,
        request: AgentRequest,
        db_session: AsyncSession,
    ) -> AgentResult:
        # 1. Fetch DB onboarding & profile state
        state_res = await self._execute_tool(
            "get_client_onboarding_state",
            lambda tr: get_client_onboarding_state_tool(tr, db_session),
            request,
            {},
        )

        onboarding_state = state_res.data if state_res.success else {}

        # 2. Run deterministic readiness calculation
        readiness_res = await self._execute_tool(
            "calculate_readiness",
            lambda tr: calculate_readiness_tool(tr, db_session),
            request,
            {},
        )

        readiness_data = readiness_res.data if readiness_res.success else {}

        # 3. Assemble safe minimum-necessary AI context & format prompt
        assembled_ctx, formatted_prompt = await self._assemble_agent_context(
            request, db_session, query_text=request.objective
        )

        user_message = (
            f"{formatted_prompt.full_prompt}\n\n"
            f"[DETERMINISTIC ONBOARDING STATE]\n{onboarding_state}\n[/DETERMINISTIC ONBOARDING STATE]\n"
            f"[DETERMINISTIC READINESS EVALUATION]\n{readiness_data}\n[/DETERMINISTIC READINESS EVALUATION]"
        )

        # 4. Call AIGateway
        ai_res, cm_output = await self._call_ai_gateway(
            request,
            user_message,
            response_schema=ClientManagerOutputSchema,
            db_session=db_session,
        )

        if not cm_output:
            cm_output = ClientManagerOutputSchema(
                finding=f"Readiness Score: {readiness_data.get('score', 0)}% (Status: {readiness_data.get('readiness_status', 'UNKNOWN')}).",
                evidence=[{"readiness": readiness_data}],
                recommendation="Complete remaining blocking onboarding requirements.",
                confidence=0.95,
                missing_configurations=readiness_data.get("blocking_requirements", []),
            )

        actions_taken = []

        # 5. Create onboarding task if needed
        if cm_output.onboarding_task_needed or len(readiness_data.get("blocking_requirements", [])) > 0:
            blocking = readiness_data.get("blocking_requirements", [])
            task_res = await self._execute_tool(
                "create_onboarding_task",
                lambda tr: create_onboarding_task_tool(tr, db_session),
                request,
                {
                    "title": cm_output.task_title or f"Complete Onboarding: {', '.join(blocking[:2]) or 'Setup'}",
                    "description": cm_output.task_description or cm_output.recommendation,
                    "priority": "HIGH" if blocking else "NORMAL",
                },
            )
            if task_res.success:
                actions_taken.append({"type": "create_task", "result": task_res.data})

        # 6. Configuration change request handling
        already_approved = bool(request.context.get("_already_approved"))
        needs_approval = cm_output.request_config_change and not already_approved
        approval_id = None
        status = AgentRequestStatus.COMPLETED

        if needs_approval:
            status = AgentRequestStatus.WAITING_APPROVAL
            if request.source != "workflow":
                approval_rec = Approval(
                    tenant_id=request.tenant_id,
                    requested_by="agent:ai_client_manager",
                    action_type="change_critical_config",
                    target="tenant_configuration",
                    reason=cm_output.recommendation,
                    risk_level="HIGH",
                    status="PENDING",
                    evidence={"finding": cm_output.finding, "missing": cm_output.missing_configurations},
                )
                db_session.add(approval_rec)
                await db_session.flush()
                approval_id = str(approval_rec.id)

        evidence_list = cm_output.evidence or []
        evidence_list.append({"readiness_calculator": readiness_data})

        return AgentResult(
            request_id=request.request_id,
            agent=self.name,
            status=status,
            finding=cm_output.finding,
            evidence=evidence_list,
            recommendation=cm_output.recommendation,
            confidence=cm_output.confidence,
            actions=actions_taken,
            needs_approval=needs_approval,
            approval_id=approval_id,
            correlation_id=request.correlation_id,
        )
