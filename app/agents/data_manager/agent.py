import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import BaseAgent
from app.agents.base.schemas import AgentRequest, AgentResult, AgentRequestStatus
from app.agents.data_manager.prompts import DATA_MANAGER_SYSTEM_INSTRUCTION
from app.agents.data_manager.schemas import DataManagerOutputSchema
from app.agents.data_manager.tools import (
    inspect_import_data_tool,
    validate_data_fields_tool,
    detect_data_conflicts_tool,
    create_data_change_request_tool,
)
from app.database.models.workflow import Approval

logger = logging.getLogger(__name__)


class DataManagerAgent(BaseAgent):
    """AI Data Manager Agent specializing in data validation, conflict detection, and import safety."""

    def __init__(self, ai_gateway=None, enabled: bool = True):
        super().__init__(
            name="ai_data_manager",
            system_instruction=DATA_MANAGER_SYSTEM_INSTRUCTION,
            ai_gateway=ai_gateway,
            enabled=enabled,
        )

    async def process_task(
        self,
        request: AgentRequest,
        db_session: AsyncSession,
    ) -> AgentResult:
        records = request.context.get("records") or request.context.get("data") or []
        if isinstance(records, dict):
            records = [records]

        entity_type = request.context.get("entity_type", "product")

        # 1. Deterministic field validation
        val_res = await self._execute_tool(
            "validate_data_fields",
            lambda tr: validate_data_fields_tool(tr, db_session),
            request,
            {"records": records, "entity_type": entity_type},
        )
        val_data = val_res.data if val_res.success else {}

        # 2. Check for conflicts
        conf_res = await self._execute_tool(
            "detect_data_conflicts",
            lambda tr: detect_data_conflicts_tool(tr, db_session),
            request,
            {"records": records, "entity_type": entity_type},
        )
        conf_data = conf_res.data if conf_res.success else {}

        # 3. Handle missing fields strictly - DO NOT HALLUCINATE
        missing_records = val_data.get("missing_field_records", [])
        if missing_records:
            missing_field_names = list({
                f for item in missing_records for f in item.get("missing_fields", [])
            })
            finding_msg = f"Data validation failed: Required fields {missing_field_names} are missing. Import cannot be finalized."
            return AgentResult(
                request_id=request.request_id,
                agent=self.name,
                status=AgentRequestStatus.WAITING_DATA,
                finding=finding_msg,
                evidence=[{"missing_records": missing_records, "val_data": val_data}],
                recommendation=f"Please provide missing values for required fields: {', '.join(missing_field_names)}.",
                confidence=1.0,
                needs_approval=False,
                correlation_id=request.correlation_id,
            )

        # 4. Assemble safe minimum-necessary AI context & format prompt
        assembled_ctx, formatted_prompt = await self._assemble_agent_context(
            request, db_session, query_text=request.objective
        )

        user_message = (
            f"{formatted_prompt.full_prompt}\n\n"
            f"[VALIDATION DATA]\n{val_data}\n[/VALIDATION DATA]\n"
            f"[CONFLICTS DETECTED]\n{conf_data}\n[/CONFLICTS DETECTED]"
        )

        # 5. Call AIGateway
        ai_res, dm_output = await self._call_ai_gateway(
            request,
            user_message,
            response_schema=DataManagerOutputSchema,
            db_session=db_session,
        )

        if not dm_output:
            dm_output = DataManagerOutputSchema(
                is_valid=val_data.get("overall_valid", False),
                finding="Validated input data records.",
                evidence=[{"validation": val_data}],
                recommendation="Proceed with change request generation.",
                confidence=0.95,
            )

        actions_taken = []
        conflicts = conf_data.get("conflicts_detected", [])

        # 6. High-safety rule: If conflicts exist or critical change requested -> Approval
        already_approved = bool(request.context.get("_already_approved"))
        needs_approval = (dm_output.requires_change_request or len(conflicts) > 0 or request.requested_action == "apply_import") and not already_approved
        approval_id = None
        status = AgentRequestStatus.COMPLETED

        if needs_approval:
            status = AgentRequestStatus.WAITING_APPROVAL
            if request.source != "workflow":
                approval_rec = Approval(
                    tenant_id=request.tenant_id,
                    requested_by="agent:ai_data_manager",
                    action_type="critical_data_modification",
                    target=f"{entity_type}_database",
                    reason=f"Data change request for {len(records)} records requiring approval. Conflicts: {len(conflicts)}",
                    risk_level="HIGH",
                    status="PENDING",
                    evidence={"validation": val_data, "conflicts": conflicts},
                )
                db_session.add(approval_rec)
                await db_session.flush()
                approval_id = str(approval_rec.id)

        evidence_list = dm_output.evidence or []
        evidence_list.append({"validation": val_data, "conflicts": conf_data})

        return AgentResult(
            request_id=request.request_id,
            agent=self.name,
            status=status,
            finding=dm_output.finding,
            evidence=evidence_list,
            recommendation=dm_output.recommendation,
            confidence=dm_output.confidence,
            actions=actions_taken,
            needs_approval=needs_approval,
            approval_id=approval_id,
            correlation_id=request.correlation_id,
        )
