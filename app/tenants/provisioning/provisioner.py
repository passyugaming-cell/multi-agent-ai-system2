import uuid
from datetime import datetime, timezone
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tenant import Tenant
from app.database.models.onboarding import OnboardingChecklist
from app.database.models.knowledge import KnowledgeCategory
from app.database.models.guardrail import AIGuardrail
from app.database.models.workflow import WorkflowConfiguration
from app.database.models.audit import ProvisioningAudit
from app.core.exceptions import TenantNotFoundException, TenantInactiveException
from app.tenants.provisioning.templates import (
    DEFAULT_CHECKLIST_TEMPLATES,
    DEFAULT_KNOWLEDGE_CATEGORIES,
    DEFAULT_AI_GUARDRAILS,
    DEFAULT_WORKFLOW_CONFIGURATIONS,
)
from app.tenants.provisioning.validators import TenantValidatorEngine
from app.tenants.provisioning.readiness import ReadinessCalculator
from app.tenants.provisioning.schemas import ProvisioningResponse, ChecklistSummary


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantProvisioner:
    """Transactional and idempotent provisioner for tenant configuration and readiness."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def provision_tenant(self, tenant_id: uuid.UUID) -> ProvisioningResponse:
        """Initialize default tenant configuration, run validation, and calculate readiness.

        Must be IDEMPOTENT. Calling multiple times for the same tenant must not create duplicate records.
        Executed within a database transaction.
        """
        # 1. Fetch tenant and verify existence
        tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
        tenant = (await self.session.execute(tenant_stmt)).scalar_one_or_none()
        if not tenant:
            raise TenantNotFoundException()
        if not tenant.is_active:
            raise TenantInactiveException()

        initialized_components: list[str] = []

        # Begin transaction nesting / flush points for safety
        async with self.session.begin_nested():
            # A. Initialize Checklist Items
            existing_cl_stmt = select(OnboardingChecklist).where(OnboardingChecklist.tenant_id == tenant_id)
            existing_cls = (await self.session.execute(existing_cl_stmt)).scalars().all()
            existing_cl_keys = {cl.key for cl in existing_cls}

            cl_added = False
            for tpl in DEFAULT_CHECKLIST_TEMPLATES:
                if tpl["key"] not in existing_cl_keys:
                    cl_item = OnboardingChecklist(
                        tenant_id=tenant_id,
                        key=tpl["key"],
                        title=tpl["title"],
                        description=tpl["description"],
                        category=tpl["category"],
                        required=tpl["required"],
                        status="PENDING",
                        completion_percentage=0.0,
                    )
                    self.session.add(cl_item)
                    cl_added = True
            if cl_added:
                initialized_components.append("onboarding_checklist")

            # B. Initialize Default Knowledge Categories
            existing_kc_stmt = select(KnowledgeCategory).where(KnowledgeCategory.tenant_id == tenant_id)
            existing_kcs = (await self.session.execute(existing_kc_stmt)).scalars().all()
            existing_kc_keys = {kc.key for kc in existing_kcs}

            kc_added = False
            for tpl in DEFAULT_KNOWLEDGE_CATEGORIES:
                if tpl["key"] not in existing_kc_keys:
                    kc_item = KnowledgeCategory(
                        tenant_id=tenant_id,
                        key=tpl["key"],
                        name=tpl["name"],
                        description=tpl["description"],
                        is_active=True,
                    )
                    self.session.add(kc_item)
                    kc_added = True
            if kc_added:
                initialized_components.append("knowledge_categories")

            # C. Initialize Default AI Guardrails
            existing_gr_stmt = select(AIGuardrail).where(AIGuardrail.tenant_id == tenant_id)
            existing_grs = (await self.session.execute(existing_gr_stmt)).scalars().all()
            existing_gr_keys = {gr.key for gr in existing_grs}

            gr_added = False
            for tpl in DEFAULT_AI_GUARDRAILS:
                if tpl["key"] not in existing_gr_keys:
                    gr_item = AIGuardrail(
                        tenant_id=tenant_id,
                        key=tpl["key"],
                        name=tpl["name"],
                        rule_definition=tpl["rule_definition"],
                        severity=tpl["severity"],
                        is_enabled=True,
                    )
                    self.session.add(gr_item)
                    gr_added = True
            if gr_added:
                initialized_components.append("ai_guardrails")

            # D. Initialize Default Workflow Configurations
            existing_wf_stmt = select(WorkflowConfiguration).where(WorkflowConfiguration.tenant_id == tenant_id)
            existing_wfs = (await self.session.execute(existing_wf_stmt)).scalars().all()
            existing_wf_keys = {wf.key for wf in existing_wfs}

            wf_added = False
            for tpl in DEFAULT_WORKFLOW_CONFIGURATIONS:
                if tpl["key"] not in existing_wf_keys:
                    wf_item = WorkflowConfiguration(
                        tenant_id=tenant_id,
                        key=tpl["key"],
                        name=tpl["name"],
                        description=tpl["description"],
                        config_data=tpl["config_data"],
                        is_active=True,
                    )
                    self.session.add(wf_item)
                    wf_added = True
            if wf_added:
                initialized_components.append("workflow_configurations")

            await self.session.flush()

        # E. Run Deterministic Validation & Update Checklist Statuses
        validator = TenantValidatorEngine(self.session)
        val_results = await validator.validate_all(tenant_id)

        all_cl_stmt = select(OnboardingChecklist).where(OnboardingChecklist.tenant_id == tenant_id)
        checklist_items = (await self.session.execute(all_cl_stmt)).scalars().all()

        completed_count = 0
        for item in checklist_items:
            is_valid = val_results.get(item.key, False)
            if is_valid:
                item.status = "COMPLETED"
                item.completion_percentage = 100.0
                if not item.completed_at:
                    item.completed_at = utc_now()
                completed_count += 1
            else:
                if item.status == "COMPLETED":
                    item.status = "IN_PROGRESS"
                    item.completion_percentage = 50.0
                    item.completed_at = None

        await self.session.flush()

        # F. Calculate Readiness Score
        readiness = ReadinessCalculator.calculate(checklist_items, val_results)

        # G. Update Client Lifecycle State
        prev_state = tenant.lifecycle_state
        new_state = prev_state

        if prev_state in ("PROSPECT", "ONBOARDING"):
            new_state = "CONFIGURING"

        if readiness.readiness_status == "READY":
            new_state = "READY"

        if new_state != prev_state:
            tenant.previous_state = prev_state
            tenant.lifecycle_state = new_state
            tenant.state_transition_at = utc_now()
            tenant.transition_reason = f"Provisioning completed with readiness status {readiness.readiness_status}"

        # H. Log Provisioning Audit
        audit = ProvisioningAudit(
            tenant_id=tenant_id,
            action="PROVISION_TENANT",
            previous_state=prev_state,
            new_state=new_state,
            actor="system",
            reason=f"Provisioning run. Readiness score: {readiness.score}%",
            result="SUCCESS",
            metadata_info={
                "readiness_score": readiness.score,
                "readiness_status": readiness.readiness_status,
                "blocking_items": readiness.blocking_requirements,
                "initialized_components": initialized_components,
            },
        )
        self.session.add(audit)
        await self.session.flush()

        # Build warnings
        warnings: list[str] = []
        if readiness.blocking_requirements:
            warnings.append(f"Blocking requirements incomplete: {', '.join(readiness.blocking_requirements)}")
        if readiness.score < 90.0:
            warnings.append(f"Readiness score is below 90% (current: {readiness.score}%)")

        total_items = len(checklist_items)
        pending_items = total_items - completed_count
        summary = ChecklistSummary(
            total=total_items,
            completed=completed_count,
            pending=pending_items,
            completion_percentage=round((completed_count / total_items * 100) if total_items > 0 else 0.0, 2),
        )

        return ProvisioningResponse(
            tenant_id=tenant_id,
            lifecycle_state=new_state,
            provisioning_status="COMPLETED",
            readiness_score=readiness.score,
            checklist=summary,
            initialized_components=initialized_components if initialized_components else ["existing_configuration_verified"],
            warnings=warnings,
            blocking_items=readiness.blocking_requirements,
        )
