import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authority.schemas import (
    ActionRequest,
    ActionRiskLevel,
    ExecutionDecision,
    AuthorizationDecision,
    ActionBinding,
)
from app.core.authority.risk import RiskClassifier, get_required_action_permission
from app.database.models.workflow import Approval
from app.database.models.audit import ProvisioningAudit

logger = logging.getLogger(__name__)


class ActionAuthorizationService:
    """Centralized Service for Action Risk Classification, Authorization & Approval Gate."""

    def __init__(self, db_session: Optional[AsyncSession] = None) -> None:
        self.session = db_session

    async def evaluate_action(
        self, request: ActionRequest, session: Optional[AsyncSession] = None
    ) -> AuthorizationDecision:
        """Evaluates an ActionRequest deterministically and produces an AuthorizationDecision."""
        db = session or self.session
        action_hash = request.compute_action_hash()
        risk_level = RiskClassifier.classify(request.action_type, request.params)

        # 1. TENANT ISOLATION BOUNDARY CHECK
        if request.actor and request.actor.tenant_id:
            if str(request.actor.tenant_id) != str(request.tenant_id):
                await self._record_audit_event(
                    db, request, risk_level, ExecutionDecision.DENY, "FORBIDDEN_CROSS_TENANT_ACCESS", action_hash
                )
                return AuthorizationDecision(
                    decision=ExecutionDecision.DENY,
                    risk_level=risk_level,
                    reason="FORBIDDEN_CROSS_TENANT_ACCESS: Actor tenant does not match request tenant.",
                    action_hash=action_hash,
                )

        # 2. PR #30 SECURITY BOUNDARY ENFORCEMENT FOR OWNER AI / PLATFORM OWNER ACTIONS
        is_owner_ai_target = (
            request.action_type in ("owner_ai", "run_owner_ai", "call_owner_ai")
            or request.target == "owner_ai"
            or request.params.get("agent_name") == "owner_ai"
        )
        if is_owner_ai_target:
            if not request.actor or not request.actor.is_platform_owner:
                await self._record_audit_event(
                    db, request, risk_level, ExecutionDecision.DENY, "UNAUTHORIZED_OWNER_AI_ACCESS", action_hash
                )
                return AuthorizationDecision(
                    decision=ExecutionDecision.DENY,
                    risk_level=risk_level,
                    reason="PERMISSION_DENIED: Workflows and non-platform actors are strictly forbidden from targeting or executing Owner AI.",
                    action_hash=action_hash,
                )

        # 3. OWNER AI SELF-APPROVAL PROHIBITION
        # Owner AI (or any agent) cannot approve its own high risk/critical actions
        is_owner_ai_actor = request.agent_id == "owner_ai" or (request.actor and request.actor.role == "owner_ai")
        if is_owner_ai_actor and risk_level in (ActionRiskLevel.HIGH, ActionRiskLevel.CRITICAL):
            # Must route to Human Platform Owner for approval, cannot self-approve
            if not request.approval_id:
                await self._record_audit_event(
                    db, request, risk_level, ExecutionDecision.WAITING_APPROVAL, "OWNER_AI_SELF_APPROVAL_FORBIDDEN", action_hash
                )
                return AuthorizationDecision(
                    decision=ExecutionDecision.WAITING_APPROVAL,
                    risk_level=risk_level,
                    reason="Owner AI cannot self-approve high risk or critical actions. Human Owner approval required.",
                    action_hash=action_hash,
                )

        # 4. APPROVAL GATE EVALUATION (IF APPROVAL_ID IS PROVIDED)
        if request.approval_id:
            if not db:
                return AuthorizationDecision(
                    decision=ExecutionDecision.DENY,
                    risk_level=risk_level,
                    reason="Database session required to evaluate approval binding.",
                    action_hash=action_hash,
                )

            stmt = select(Approval).where(
                and_(
                    Approval.id == request.approval_id,
                    Approval.tenant_id == request.tenant_id,
                )
            )
            appr = (await db.execute(stmt)).scalar_one_or_none()

            if not appr:
                await self._record_audit_event(
                    db, request, risk_level, ExecutionDecision.DENY, "APPROVAL_NOT_FOUND", action_hash
                )
                return AuthorizationDecision(
                    decision=ExecutionDecision.DENY,
                    risk_level=risk_level,
                    reason="Invalid approval request or cross-tenant approval reuse attempted.",
                    action_hash=action_hash,
                )

            # Check status
            if appr.status not in ("APPROVED", "MODIFIED"):
                await self._record_audit_event(
                    db, request, risk_level, ExecutionDecision.DENY, f"APPROVAL_STATUS_{appr.status}", action_hash
                )
                return AuthorizationDecision(
                    decision=ExecutionDecision.DENY,
                    risk_level=risk_level,
                    reason=f"Approval request status is {appr.status}, expected APPROVED or MODIFIED.",
                    approval_id=appr.id,
                    action_hash=action_hash,
                )

            # Check expiration
            if appr.expires_at and appr.expires_at < datetime.now(timezone.utc):
                appr.status = "EXPIRED"
                await db.commit()
                await self._record_audit_event(
                    db, request, risk_level, ExecutionDecision.DENY, "APPROVAL_EXPIRED", action_hash
                )
                return AuthorizationDecision(
                    decision=ExecutionDecision.DENY,
                    risk_level=risk_level,
                    reason="Approval request has expired.",
                    approval_id=appr.id,
                    action_hash=action_hash,
                )

            appr_meta = appr.meta_data or {}
            decided_by_str = str(appr.decided_by or "").lower()
            requested_by_str = str(appr.requested_by or "").lower()
            request_agent_str = str(request.agent_id or "").lower()

            # RISK-AWARE APPROVER IDENTITY VALIDATION FOR HIGH/CRITICAL ACTIONS
            if risk_level in (ActionRiskLevel.HIGH, ActionRiskLevel.CRITICAL):
                # 1. Self-approval prohibition
                if (
                    not appr.decided_by
                    or decided_by_str in ("owner_ai", "agent:owner_ai", "agent_owner_ai")
                    or decided_by_str == requested_by_str
                    or (request_agent_str and decided_by_str == request_agent_str)
                ):
                    await self._record_audit_event(
                        db, request, risk_level, ExecutionDecision.DENY, "SELF_APPROVAL_FORBIDDEN", action_hash
                    )
                    return AuthorizationDecision(
                        decision=ExecutionDecision.DENY,
                        risk_level=risk_level,
                        reason="PERMISSION_DENIED: Owner AI or requesting agent cannot self-approve actions.",
                        approval_id=appr.id,
                        action_hash=action_hash,
                    )

                # 2. Strict Human Platform Owner metadata check for HIGH/CRITICAL actions
                is_platform_owner_approver = (appr_meta.get("decided_by_is_platform_owner") is True)
                if not is_platform_owner_approver:
                    await self._record_audit_event(
                        db, request, risk_level, ExecutionDecision.DENY, "UNAUTHORIZED_APPROVER_IDENTITY", action_hash
                    )
                    return AuthorizationDecision(
                        decision=ExecutionDecision.DENY,
                        risk_level=risk_level,
                        reason="PERMISSION_DENIED: High and critical risk actions require approval from an authorized Human Platform Owner.",
                        approval_id=appr.id,
                        action_hash=action_hash,
                    )

            # Check action binding (Action Type + Target + Tenant + Parameters Hash)
            stored_hash = appr_meta.get("action_hash")
            if not stored_hash:
                # Recompute stored hash from approval attributes if missing
                stored_hash = ActionBinding.compute_hash(
                    action_type=appr.action_type,
                    target=appr.target,
                    tenant_id=appr.tenant_id,
                    params=appr_meta.get("params", {}),
                )

            if stored_hash != action_hash:
                await self._record_audit_event(
                    db, request, risk_level, ExecutionDecision.DENY, "APPROVAL_BINDING_MISMATCH", action_hash
                )
                return AuthorizationDecision(
                    decision=ExecutionDecision.DENY,
                    risk_level=risk_level,
                    reason="Approval binding mismatch: requested action parameters do not match approved parameters.",
                    approval_id=appr.id,
                    action_hash=action_hash,
                )

            # If MEDIUM risk, still verify actor permissions for the medium action
            if risk_level == ActionRiskLevel.MEDIUM:
                required_perm = get_required_action_permission(request.action_type)
                if not request.actor or required_perm not in request.actor.permissions:
                    await self._record_audit_event(
                        db, request, risk_level, ExecutionDecision.DENY, "PERMISSION_DENIED_MEDIUM_RISK", action_hash
                    )
                    return AuthorizationDecision(
                        decision=ExecutionDecision.DENY,
                        risk_level=risk_level,
                        reason=f"PERMISSION_DENIED: Actor lacks required permission '{required_perm}' for action '{request.action_type}'.",
                        action_hash=action_hash,
                        required_permissions={required_perm},
                    )

            # Approval is valid, bound, active, and matching!
            await self._record_audit_event(
                db, request, risk_level, ExecutionDecision.ALLOW, "APPROVED_EXECUTION_AUTHORIZED", action_hash
            )
            return AuthorizationDecision(
                decision=ExecutionDecision.ALLOW,
                risk_level=risk_level,
                reason="Action execution approved by valid, bound Human Owner decision.",
                approval_id=appr.id,
                action_hash=action_hash,
            )

        # 5. NO APPROVAL PRESENT: RISK-BASED DECISION POLICY
        if risk_level == ActionRiskLevel.LOW:
            await self._record_audit_event(
                db, request, risk_level, ExecutionDecision.ALLOW, "LOW_RISK_AUTHORIZED", action_hash
            )
            return AuthorizationDecision(
                decision=ExecutionDecision.ALLOW,
                risk_level=risk_level,
                reason="Low-risk action authorized for autonomous execution.",
                action_hash=action_hash,
            )

        elif risk_level == ActionRiskLevel.MEDIUM:
            required_perm = get_required_action_permission(request.action_type)
            if not request.actor or required_perm not in request.actor.permissions:
                await self._record_audit_event(
                    db, request, risk_level, ExecutionDecision.DENY, "PERMISSION_DENIED_MEDIUM_RISK", action_hash
                )
                return AuthorizationDecision(
                    decision=ExecutionDecision.DENY,
                    risk_level=risk_level,
                    reason=f"PERMISSION_DENIED: Actor lacks required permission '{required_perm}' for action '{request.action_type}'.",
                    action_hash=action_hash,
                    required_permissions={required_perm},
                )

            await self._record_audit_event(
                db, request, risk_level, ExecutionDecision.ALLOW, "MEDIUM_RISK_AUTHORIZED", action_hash
            )
            return AuthorizationDecision(
                decision=ExecutionDecision.ALLOW,
                risk_level=risk_level,
                reason=f"Medium-risk action '{request.action_type}' authorized with required permission '{required_perm}'.",
                action_hash=action_hash,
                required_permissions={required_perm},
            )

        else: # HIGH or CRITICAL
            await self._record_audit_event(
                db, request, risk_level, ExecutionDecision.WAITING_APPROVAL, "HIGH_RISK_APPROVAL_REQUIRED", action_hash
            )
            return AuthorizationDecision(
                decision=ExecutionDecision.WAITING_APPROVAL,
                risk_level=risk_level,
                reason=f"{risk_level.value}-risk action requires explicit Human Owner approval.",
                action_hash=action_hash,
            )

    async def _record_audit_event(
        self,
        db: Optional[AsyncSession],
        request: ActionRequest,
        risk_level: ActionRiskLevel,
        decision: ExecutionDecision,
        result_code: str,
        action_hash: str,
    ) -> None:
        """Helper to record audit trail of action evaluation decision."""
        if not db:
            return

        actor_str = "system"
        if request.actor:
            actor_str = f"user_{request.actor.user_id}"
        elif request.agent_id:
            actor_str = f"agent_{request.agent_id}"

        audit = ProvisioningAudit(
            tenant_id=request.tenant_id,
            action=f"action_authorization.{request.action_type}",
            previous_state=None,
            new_state=decision.value,
            actor=actor_str,
            reason=f"Risk: {risk_level.value}, Decision: {decision.value}, Code: {result_code}",
            result=result_code,
            metadata_info={
                "action_type": request.action_type,
                "target": request.target,
                "risk_level": risk_level.value,
                "action_hash": action_hash,
                "approval_id": str(request.approval_id) if request.approval_id else None,
                "correlation_id": request.correlation_id,
            },
        )
        db.add(audit)
