import uuid
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events.schemas import EventSchema
from app.core.workflows.conditions import ConditionEvaluator
from app.core.workflows.actions import ActionExecutor, ActionResult, get_action_risk_level, RiskLevel
from app.database.models.workflow import (
    WorkflowConfiguration,
    WorkflowExecution,
    WorkflowExecutionHistory,
    Approval,
    Task,
    EventRecord,
)

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Deterministic, asynchronous, tenant-isolated Workflow Engine."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def handle_event(self, event: EventSchema) -> list[WorkflowExecution]:
        """Main entry point: process incoming event and match workflows."""
        if not settings.WORKFLOWS_ENABLED:
            logger.info("Workflows globally disabled by kill-switch settings.")
            return []

        tenant_uuid = uuid.UUID(event.tenant_id)

        # Establish trusted actor context at workflow engine execution boundary
        from app.core.context import set_actor_context, reset_actor_context, AuthenticatedActor
        wf_actor = AuthenticatedActor(
            user_id=None,
            tenant_id=tenant_uuid,
            role="system_workflow",
            permissions={"business.read", "product.read", "knowledge.read"},
        )
        token = set_actor_context(wf_actor)

        try:
            return await self._handle_event_internal(event, tenant_uuid)
        finally:
            reset_actor_context(token)

    async def _handle_event_internal(self, event: EventSchema, tenant_uuid: uuid.UUID) -> list[WorkflowExecution]:
        # 1. Store event record
        evt_stmt = select(EventRecord).where(
            and_(EventRecord.tenant_id == tenant_uuid, EventRecord.event_id == event.event_id)
        )
        existing_evt = (await self.session.execute(evt_stmt)).scalar_one_or_none()
        if not existing_evt:
            evt_rec = EventRecord(
                tenant_id=tenant_uuid,
                event_id=event.event_id,
                event_type=event.event_type,
                occurred_at=event.occurred_at,
                payload=event.payload,
                source=event.source,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                idempotency_key=event.idempotency_key,
                schema_version=event.schema_version,
            )
            self.session.add(evt_rec)
            await self.session.flush()

        # 2. Find matching active workflows for tenant and trigger
        wf_stmt = select(WorkflowConfiguration).where(
            and_(
                WorkflowConfiguration.tenant_id == tenant_uuid,
                WorkflowConfiguration.is_active.is_(True),
            )
        )
        active_wfs = (await self.session.execute(wf_stmt)).scalars().all()

        matched_executions = []
        for wf in active_wfs:
            # Match trigger type or config_data trigger
            trigger = wf.trigger_type or (wf.config_data or {}).get("trigger")
            if not trigger or (trigger != event.event_type and trigger != "*"):
                continue

            # Idempotency check: tenant_id + workflow_id + event_id
            exec_stmt = select(WorkflowExecution).where(
                and_(
                    WorkflowExecution.tenant_id == tenant_uuid,
                    WorkflowExecution.workflow_id == wf.id,
                    WorkflowExecution.event_id == event.event_id,
                )
            )
            existing_exec = (await self.session.execute(exec_stmt)).scalar_one_or_none()
            if existing_exec:
                logger.info("Duplicate event execution detected for tenant %s workflow %s event %s", tenant_uuid, wf.id, event.event_id)
                matched_executions.append(existing_exec)
                continue

            # Create new WorkflowExecution
            execution = WorkflowExecution(
                tenant_id=tenant_uuid,
                workflow_id=wf.id,
                event_id=event.event_id,
                correlation_id=event.correlation_id or event.event_id,
                status="PENDING",
                current_step=0,
                max_retries=wf.max_retries or settings.WORKFLOW_MAX_RETRIES,
                context={"event": event.model_dump(mode="json"), "payload": event.payload},
            )
            self.session.add(execution)
            await self.session.flush()

            # Execute pipeline
            await self.run_execution_pipeline(execution, wf)
            matched_executions.append(execution)

        await self.session.commit()
        return matched_executions

    async def run_execution_pipeline(self, execution: WorkflowExecution, workflow: WorkflowConfiguration) -> None:
        """Executes workflow steps deterministically."""
        if execution.status in ("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT", "BLOCKED"):
            return

        from app.core.context import get_actor_context, set_actor_context, reset_actor_context, AuthenticatedActor

        active_actor = get_actor_context()
        token = None
        if not active_actor:
            wf_actor = AuthenticatedActor(
                user_id=None,
                tenant_id=execution.tenant_id,
                role="system_workflow",
                permissions={"business.read", "product.read", "knowledge.read"},
            )
            token = set_actor_context(wf_actor)

        try:
            await self._run_execution_pipeline_internal(execution, workflow)
        finally:
            if token:
                reset_actor_context(token)

    async def _run_execution_pipeline_internal(self, execution: WorkflowExecution, workflow: WorkflowConfiguration) -> None:
        now = datetime.now(timezone.utc)
        execution.started_at = execution.started_at or now

        started_at = execution.started_at
        if started_at and started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

        # Max execution time timeout check
        max_time = workflow.max_execution_time or settings.WORKFLOW_TIMEOUT_SECONDS
        if started_at and (now - started_at).total_seconds() > max_time:
            execution.status = "TIMED_OUT"
            execution.failed_at = now
            execution.error = f"Workflow execution timed out after exceeding max_execution_time ({max_time}s)."
            self._record_history(execution, "WORKFLOW_TIMED_OUT", error=execution.error)
            return

        execution.status = "RUNNING"

        # Loop protection: check max steps
        max_steps = workflow.max_steps or settings.WORKFLOW_MAX_STEPS
        if execution.current_step >= max_steps:
            execution.status = "BLOCKED"
            execution.failed_at = now
            execution.error = f"Loop protection triggered: exceeded maximum allowed steps ({max_steps})."
            self._record_history(execution, "LOOP_PROTECTION_EXCEEDED", error=execution.error)
            return

        # Condition Evaluation
        conditions = workflow.conditions or (workflow.config_data or {}).get("conditions")
        condition_passed = ConditionEvaluator.evaluate_conditions(conditions, execution.context)

        self._record_history(
            execution,
            "EVALUATE_CONDITIONS",
            result={"passed": condition_passed, "conditions": conditions},
        )

        if not condition_passed:
            execution.status = "COMPLETED"
            execution.completed_at = now
            execution.result = {"condition_met": False, "message": "Workflow completed safely because trigger conditions were not met."}
            return

        # Action Execution Loop
        actions = workflow.actions or (workflow.config_data or {}).get("actions", [])
        if isinstance(actions, dict):
            actions = [actions]

        while execution.current_step < len(actions):
            action_def = actions[execution.current_step]
            action_type = action_def.get("action") or action_def.get("type") or "send_message"
            action_params = action_def.get("params") or action_def

            res = await ActionExecutor.execute(
                action_type=action_type,
                params=action_params,
                context=execution.context,
                session=self.session,
                tenant_id=str(execution.tenant_id),
            )

            # Check if action requires human approval
            if res.requires_approval:
                approval_data = res.approval_data
                approval = Approval(
                    tenant_id=execution.tenant_id,
                    workflow_execution_id=execution.id,
                    requested_by="workflow_engine",
                    action_type=approval_data["action_type"],
                    target=approval_data["target"],
                    reason=approval_data["reason"],
                    risk_level=approval_data["risk_level"],
                    status="PENDING",
                    evidence={"context": execution.context, "params": action_params},
                )
                self.session.add(approval)
                execution.status = "WAITING_APPROVAL"
                self._record_history(execution, "APPROVAL_REQUESTED", result=approval_data)
                return  # Pause execution

            if res.is_delayed:
                execution.status = "PENDING"
                execution.next_retry_at = now + timedelta(seconds=res.delay_seconds)
                self._record_history(execution, "DELAY_INITIATED", result={"seconds": res.delay_seconds})
                return

            if not res.success:
                # Retry logic
                if execution.retry_count < execution.max_retries:
                    execution.retry_count += 1
                    execution.status = "WAITING_RETRY"
                    execution.next_retry_at = now + timedelta(seconds=2 ** execution.retry_count)
                    self._record_history(execution, "STEP_FAILED_RETRYING", error=res.error)
                    return
                else:
                    execution.status = "FAILED"
                    execution.failed_at = now
                    execution.error = res.error
                    self._record_history(execution, "STEP_FAILED_MAX_RETRIES_EXCEEDED", error=res.error)
                    return

            # Success
            self._record_history(execution, f"EXECUTE_ACTION_{action_type.upper()}", result=res.output)
            execution.context.update(res.output)
            execution.current_step += 1

        # All actions completed successfully
        execution.status = "COMPLETED"
        execution.completed_at = now
        execution.result = {"status": "success", "final_context": execution.context}

    def _record_history(self, execution: WorkflowExecution, action: str, result: dict | None = None, error: str | None = None) -> None:
        history = WorkflowExecutionHistory(
            tenant_id=execution.tenant_id,
            workflow_execution_id=execution.id,
            event_id=execution.event_id,
            step_number=execution.current_step,
            action=action,
            actor_or_source="workflow_engine",
            result=result,
            error=error,
        )
        self.session.add(history)
