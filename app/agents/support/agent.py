import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import BaseAgent
from app.agents.base.schemas import AgentRequest, AgentResult, AgentRequestStatus
from app.agents.support.prompts import SUPPORT_AGENT_SYSTEM_INSTRUCTION
from app.agents.support.schemas import SupportDiagnosisOutputSchema, IncidentSeverity
from app.agents.support.tools import (
    get_system_health_tool,
    get_whatsapp_status_tool,
    get_workflow_status_tool,
    create_support_incident_task_tool,
    execute_low_risk_remediation_tool,
)
from app.database.models.workflow import Approval

logger = logging.getLogger(__name__)


class SupportAgent(BaseAgent):
    """AI Support Agent specializing in diagnostic analysis, incident classification, and remediation."""

    def __init__(self, ai_gateway=None, enabled: bool = True):
        super().__init__(
            name="ai_support",
            system_instruction=SUPPORT_AGENT_SYSTEM_INSTRUCTION,
            ai_gateway=ai_gateway,
            enabled=enabled,
        )

    async def process_task(
        self,
        request: AgentRequest,
        db_session: AsyncSession,
    ) -> AgentResult:
        # 1. Fetch system health, whatsapp, and workflow status evidence
        health_res = await self._execute_tool(
            "get_system_health",
            lambda tr: get_system_health_tool(tr, db_session),
            request,
            {},
        )
        wf_res = await self._execute_tool(
            "get_workflow_status",
            lambda tr: get_workflow_status_tool(tr, db_session),
            request,
            {},
        )
        wa_res = await self._execute_tool(
            "get_whatsapp_status",
            lambda tr: get_whatsapp_status_tool(tr, db_session),
            request,
            {},
        )

        evidence_data = {
            "health": health_res.data if health_res.success else {},
            "failed_workflows": wf_res.data if wf_res.success else [],
            "whatsapp_status": wa_res.data if wa_res.success else {},
        }

        # 2. Formulate prompt
        user_message = (
            f"Objective: {request.objective}\n"
            f"Context: {request.context}\n"
            f"Observed System Evidence: {evidence_data}\n"
            f"Requested Action: {request.requested_action or 'Diagnose problem and recommend fix'}"
        )

        # 3. Call AIGateway
        ai_res, diag_output = await self._call_ai_gateway(
            request,
            user_message,
            response_schema=SupportDiagnosisOutputSchema,
            db_session=db_session,
        )

        if not diag_output:
            diag_output = SupportDiagnosisOutputSchema(
                observed_evidence=[str(evidence_data)],
                possible_cause="System error or workflow step execution failure.",
                incident_severity=IncidentSeverity.MEDIUM,
                recommendation="Inspect workflow logs and retry failed execution.",
                confidence=0.85,
            )

        actions_taken = []

        # 4. Handle support incident task creation
        if diag_output.support_task_needed or diag_output.incident_severity in (IncidentSeverity.HIGH, IncidentSeverity.CRITICAL):
            task_res = await self._execute_tool(
                "create_support_incident_task",
                lambda tr: create_support_incident_task_tool(tr, db_session),
                request,
                {
                    "title": diag_output.task_title or f"Support Incident [{diag_output.incident_severity.value}]: {request.objective[:30]}",
                    "description": f"Cause: {diag_output.possible_cause}\nRecommendation: {diag_output.recommendation}",
                    "severity": diag_output.incident_severity.value,
                },
            )
            if task_res.success:
                actions_taken.append({"type": "create_task", "result": task_res.data})

        # 5. Handle high-risk vs low-risk remediation / Approval
        already_approved = bool(request.context.get("_already_approved"))
        needs_approval = (diag_output.requires_high_risk_remediation or diag_output.incident_severity == IncidentSeverity.CRITICAL) and not already_approved
        approval_id = None
        status = AgentRequestStatus.COMPLETED

        if needs_approval:
            status = AgentRequestStatus.WAITING_APPROVAL
            if request.source != "workflow":
                approval_rec = Approval(
                    tenant_id=request.tenant_id,
                    requested_by="agent:ai_support",
                    action_type="critical_production_change",
                    target="production_environment",
                    reason=f"High-risk support remediation for {diag_output.incident_severity.value} incident: {diag_output.recommendation}",
                    risk_level="CRITICAL" if diag_output.incident_severity == IncidentSeverity.CRITICAL else "HIGH",
                    status="PENDING",
                    evidence={"cause": diag_output.possible_cause, "evidence": diag_output.observed_evidence},
                )
                db_session.add(approval_rec)
                await db_session.flush()
                approval_id = str(approval_rec.id)

        evidence_list = [{"observed_evidence": diag_output.observed_evidence, "system_health": evidence_data}]

        finding_str = f"Severity: {diag_output.incident_severity.value} | Cause: {diag_output.possible_cause}"

        return AgentResult(
            request_id=request.request_id,
            agent=self.name,
            status=status,
            finding=finding_str,
            evidence=evidence_list,
            recommendation=diag_output.recommendation,
            confidence=diag_output.confidence,
            actions=actions_taken,
            needs_approval=needs_approval,
            approval_id=approval_id,
            correlation_id=request.correlation_id,
        )
