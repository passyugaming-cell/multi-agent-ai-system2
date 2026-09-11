import uuid
from datetime import datetime, timezone
from typing import Sequence, Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.workflow import Approval, WorkflowExecution, WorkflowConfiguration
from app.core.workflows.engine import WorkflowEngine
from app.core.workflows.actions import ActionExecutor, get_action_risk_level, RiskLevel
from app.core.exceptions import AppError


class ApprovalService:
    """Service layer managing Approval requests and Workflow execution resume/cancellation."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def get_approval(self, tenant_id: uuid.UUID, approval_id: uuid.UUID) -> Approval:
        stmt = select(Approval).where(and_(Approval.id == approval_id, Approval.tenant_id == tenant_id))
        appr = (await self.session.execute(stmt)).scalar_one_or_none()
        if not appr:
            raise AppError("Approval request not found or access denied.", status_code=404)
        return appr

    async def list_approvals(self, tenant_id: uuid.UUID, status: str | None = None) -> Sequence[Approval]:
        filters = [Approval.tenant_id == tenant_id]
        if status:
            filters.append(Approval.status == status)

        stmt = select(Approval).where(and_(*filters)).order_by(Approval.requested_at.desc())
        return (await self.session.execute(stmt)).scalars().all()

    async def approve(
        self,
        tenant_id: uuid.UUID,
        approval_id: uuid.UUID,
        decided_by: str,
        reason: str | None = None,
    ) -> Approval:
        approval = await self.get_approval(tenant_id, approval_id)

        if approval.status != "PENDING":
            raise AppError(f"Approval request is not PENDING (current status: {approval.status}).", status_code=400)

        # Check expiration
        if approval.expires_at and approval.expires_at < datetime.now(timezone.utc):
            approval.status = "EXPIRED"
            await self.session.commit()
            raise AppError("Approval request has expired.", status_code=400)

        # Check approver identity & platform owner authority for HIGH/CRITICAL risk actions
        from app.core.context import get_actor_context
        active_actor = get_actor_context()

        if approval.risk_level in ("HIGH", "CRITICAL"):
            if not active_actor or not active_actor.is_platform_owner:
                raise AppError(
                    "PERMISSION_DENIED: Only an authorized Human Platform Owner can approve high or critical risk actions.",
                    status_code=403,
                )

        decided_by_lower = str(decided_by).lower()
        requested_by_lower = str(approval.requested_by).lower()

        if (
            decided_by_lower in ("owner_ai", "agent:owner_ai", "agent_owner_ai")
            or (active_actor and active_actor.role in ("owner_ai", "agent:owner_ai"))
            or (decided_by_lower == requested_by_lower and ("agent" in decided_by_lower or "owner_ai" in decided_by_lower))
        ):
            raise AppError("PERMISSION_DENIED: Owner AI or requesting agent cannot self-approve actions.", status_code=403)

        approval.status = "APPROVED"
        approval.decided_at = datetime.now(timezone.utc)
        approval.decided_by = decided_by
        approval.decision_reason = reason
        approval.meta_data = approval.meta_data or {}

        if active_actor and active_actor.is_platform_owner:
            approval.meta_data["decided_by_is_platform_owner"] = True
            approval.meta_data["decided_by_user_id"] = str(active_actor.user_id) if active_actor.user_id else "platform_owner"

        # Resume workflow execution if associated
        if approval.workflow_execution_id:
            await self._resume_workflow_execution(approval, modified_params=None)

        await self.session.commit()
        await self.session.refresh(approval)
        return approval

    async def reject(
        self,
        tenant_id: uuid.UUID,
        approval_id: uuid.UUID,
        decided_by: str,
        reason: str,
    ) -> Approval:
        approval = await self.get_approval(tenant_id, approval_id)

        if approval.status != "PENDING":
            raise AppError(f"Approval request is not PENDING (current status: {approval.status}).", status_code=400)

        approval.status = "REJECTED"
        approval.decided_at = datetime.now(timezone.utc)
        approval.decided_by = decided_by
        approval.decision_reason = reason

        # Cancel workflow execution if associated
        if approval.workflow_execution_id:
            exec_stmt = select(WorkflowExecution).where(WorkflowExecution.id == approval.workflow_execution_id)
            execution = (await self.session.execute(exec_stmt)).scalar_one_or_none()
            if execution:
                execution.status = "CANCELLED"
                execution.error = f"Protected action {approval.action_type} rejected by {decided_by}: {reason}"

        await self.session.commit()
        await self.session.refresh(approval)
        return approval

    async def modify_and_approve(
        self,
        tenant_id: uuid.UUID,
        approval_id: uuid.UUID,
        decided_by: str,
        modified_params: dict[str, Any],
        reason: str,
    ) -> Approval:
        approval = await self.get_approval(tenant_id, approval_id)

        if approval.status != "PENDING":
            raise AppError(f"Approval request is not PENDING (current status: {approval.status}).", status_code=400)

        # Re-evaluate risk level of modified parameters
        new_risk = get_action_risk_level(approval.action_type, modified_params)
        if new_risk == RiskLevel.CRITICAL and approval.risk_level != "CRITICAL":
            raise AppError("Modification increased risk level to CRITICAL. A new approval request is required.", status_code=400)

        from app.core.context import get_actor_context
        active_actor = get_actor_context()

        if approval.risk_level in ("HIGH", "CRITICAL") or new_risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            if not active_actor or not active_actor.is_platform_owner:
                raise AppError(
                    "PERMISSION_DENIED: Only an authorized Human Platform Owner can approve high or critical risk actions.",
                    status_code=403,
                )

        decided_by_lower = str(decided_by).lower()
        requested_by_lower = str(approval.requested_by).lower()

        if (
            decided_by_lower in ("owner_ai", "agent:owner_ai", "agent_owner_ai")
            or (active_actor and active_actor.role in ("owner_ai", "agent:owner_ai"))
            or (decided_by_lower == requested_by_lower and ("agent" in decided_by_lower or "owner_ai" in decided_by_lower))
        ):
            raise AppError("PERMISSION_DENIED: Owner AI or requesting agent cannot self-approve actions.", status_code=403)

        approval.status = "MODIFIED"
        approval.decided_at = datetime.now(timezone.utc)
        approval.decided_by = decided_by
        approval.decision_reason = reason
        approval.meta_data = approval.meta_data or {}
        approval.meta_data["modified_params"] = modified_params

        if active_actor and active_actor.is_platform_owner:
            approval.meta_data["decided_by_is_platform_owner"] = True
            approval.meta_data["decided_by_user_id"] = str(active_actor.user_id) if active_actor.user_id else "platform_owner"

        # Update action_hash in meta_data for modified parameters
        from app.core.authority.schemas import ActionBinding
        approval.meta_data["action_hash"] = ActionBinding.compute_hash(
            action_type=approval.action_type,
            target=approval.target,
            tenant_id=approval.tenant_id,
            params=modified_params,
        )

        # Resume workflow execution with modified parameters
        if approval.workflow_execution_id:
            await self._resume_workflow_execution(approval, modified_params=modified_params)

        await self.session.commit()
        await self.session.refresh(approval)
        return approval

    async def _resume_workflow_execution(self, approval: Approval, modified_params: dict[str, Any] | None) -> None:
        exec_stmt = select(WorkflowExecution).where(WorkflowExecution.id == approval.workflow_execution_id)
        execution = (await self.session.execute(exec_stmt)).scalar_one_or_none()
        if not execution:
            return

        wf_stmt = select(WorkflowConfiguration).where(WorkflowConfiguration.id == execution.workflow_id)
        wf = (await self.session.execute(wf_stmt)).scalar_one_or_none()
        if not wf:
            return

        actions = wf.actions or (wf.config_data or {}).get("actions", [])
        if isinstance(actions, dict):
            actions = [actions]

        from app.core.context import get_actor_context
        active_actor = get_actor_context()
        if not active_actor:
            raise AppError("Authentication required: no active trusted actor context to resume workflow execution.", status_code=403)

        if execution.current_step < len(actions):
            action_def = actions[execution.current_step]
            action_type = approval.action_type
            params = dict(modified_params or action_def.get("params") or action_def)
            params["_approval_id"] = str(approval.id)

            res = await ActionExecutor.execute(
                action_type=action_type,
                params=params,
                context=execution.context,
                session=self.session,
                tenant_id=str(execution.tenant_id),
            )

            if res.success and not res.requires_approval:
                execution.context.update(res.output)
                execution.current_step += 1
                execution.status = "RUNNING"

                # Resume engine loop for subsequent steps
                engine = WorkflowEngine(self.session)
                await engine.run_execution_pipeline(execution, wf)
            else:
                execution.status = "FAILED"
                execution.error = res.error
