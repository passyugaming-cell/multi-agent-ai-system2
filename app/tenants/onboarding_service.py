import uuid
from datetime import datetime, timezone
from typing import Sequence
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tenant import Tenant
from app.database.models.onboarding import OnboardingChecklist
from app.database.models.integrations import IntegrationConnection, Integration, IntegrationCredential
from app.database.models.audit import ProvisioningAudit
from app.core.exceptions import TenantNotFoundException, AppException
from app.tenants.lifecycle import ClientLifecycleManager
from app.tenants.provisioning.provisioner import TenantProvisioner
from app.tenants.provisioning.validators import TenantValidatorEngine
from app.tenants.provisioning.readiness import ReadinessCalculator
from app.tenants.provisioning.exceptions import ChecklistRequirementError, ReadinessValidationError
from app.integrations.service import IntegrationService
from app.integrations.events import publish_integration_event
from app.integrations.registry import integration_registry
from app.integrations.exceptions import PermissionDeniedError, IntegrationError
from app.billing.entitlement import EntitlementResolver
from app.billing.state_machine import SubscriptionStatus
from app.core.ai_gateway import AIGateway, AIRequest
from app.tenants.provisioning.schemas import (
    OnboardingSummaryResponse,
    ChecklistSummary,
    ChecklistItemResponse,
    ChecklistItemUpdate,
    WhatsAppConnectRequest,
    WhatsAppConnectResponse,
    WhatsAppVerifyResponse,
    AITestRequest,
    AITestResponse,
    TenantActivationRequest,
    TenantActivationResponse,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OnboardingService:
    """Service layer for tenant onboarding management, checklists, and readiness validation."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.lifecycle_manager = ClientLifecycleManager(session)
        self.provisioner = TenantProvisioner(session)
        self.integration_service = IntegrationService(session)
        self.entitlement = EntitlementResolver(session)

    async def start_onboarding(self, tenant_id: uuid.UUID) -> OnboardingSummaryResponse:
        """Starts tenant onboarding flow."""
        tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
        tenant = (await self.session.execute(tenant_stmt)).scalar_one_or_none()
        if not tenant:
            raise TenantNotFoundException()

        if tenant.lifecycle_state == "PROSPECT":
            await self.lifecycle_manager.transition_state(
                tenant_id=tenant_id,
                target_state="ONBOARDING",
                reason="Onboarding process started by client",
            )

        # Run provisioner to ensure default templates exist and are initialized
        await self.provisioner.provision_tenant(tenant_id)
        return await self.get_onboarding_summary(tenant_id)

    async def get_onboarding_summary(self, tenant_id: uuid.UUID) -> OnboardingSummaryResponse:
        """Get summary of onboarding checklist, readiness score, and blocking items."""
        tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
        tenant = (await self.session.execute(tenant_stmt)).scalar_one_or_none()
        if not tenant:
            raise TenantNotFoundException()

        cl_stmt = select(OnboardingChecklist).where(OnboardingChecklist.tenant_id == tenant_id)
        checklist_items = (await self.session.execute(cl_stmt)).scalars().all()

        if not checklist_items:
            # Provision if not initialized
            await self.provisioner.provision_tenant(tenant_id)
            checklist_items = (await self.session.execute(cl_stmt)).scalars().all()

        val_results = await TenantValidatorEngine(self.session).validate_all(tenant_id)
        readiness = ReadinessCalculator.calculate(checklist_items, val_results)

        completed_count = len(readiness.completed_requirements)
        total_count = len(checklist_items)
        pending_count = total_count - completed_count

        summary = ChecklistSummary(
            total=total_count,
            completed=completed_count,
            pending=pending_count,
            completion_percentage=round((completed_count / total_count * 100) if total_count > 0 else 0.0, 2),
        )

        warnings: list[str] = []
        if readiness.blocking_requirements:
            warnings.append(f"Incomplete blocking requirements: {', '.join(readiness.blocking_requirements)}")

        item_responses = [ChecklistItemResponse.model_validate(item) for item in checklist_items]

        return OnboardingSummaryResponse(
            tenant_id=tenant_id,
            lifecycle_state=tenant.lifecycle_state,
            readiness_score=readiness.score,
            readiness_status=readiness.readiness_status,
            checklist_summary=summary,
            checklist_items=item_responses,
            blocking_items=readiness.blocking_requirements,
            warnings=warnings,
        )

    async def get_checklist(self, tenant_id: uuid.UUID) -> list[ChecklistItemResponse]:
        """List all checklist items for a tenant."""
        cl_stmt = select(OnboardingChecklist).where(OnboardingChecklist.tenant_id == tenant_id)
        items = (await self.session.execute(cl_stmt)).scalars().all()
        return [ChecklistItemResponse.model_validate(item) for item in items]

    async def update_checklist_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID, update_data: ChecklistItemUpdate
    ) -> ChecklistItemResponse:
        """Update a checklist item's status, enforcing tenant isolation and required constraints."""
        cl_stmt = select(OnboardingChecklist).where(
            OnboardingChecklist.tenant_id == tenant_id,
            OnboardingChecklist.id == item_id,
        )
        item = (await self.session.execute(cl_stmt)).scalar_one_or_none()
        if not item:
            raise AppException(code="CHECKLIST_ITEM_NOT_FOUND", message="Checklist item not found", status_code=404)

        if update_data.status:
            status_upper = update_data.status.upper()
            if status_upper == "SKIPPED" and item.required:
                raise ChecklistRequirementError("Required checklist items cannot be skipped")

            item.status = status_upper
            if status_upper == "COMPLETED":
                item.completion_percentage = 100.0
                item.completed_at = utc_now()
            elif status_upper == "PENDING":
                item.completion_percentage = 0.0
                item.completed_at = None

        if update_data.completion_percentage is not None:
            item.completion_percentage = update_data.completion_percentage

        if update_data.metadata_info is not None:
            item.metadata_info = update_data.metadata_info

        await self.session.flush()
        await self.session.refresh(item)
        return ChecklistItemResponse.model_validate(item)

    async def validate_onboarding(self, tenant_id: uuid.UUID) -> OnboardingSummaryResponse:
        """Runs validation checks, updates checklist items, and updates readiness score."""
        val_results = await TenantValidatorEngine(self.session).validate_all(tenant_id)

        cl_stmt = select(OnboardingChecklist).where(OnboardingChecklist.tenant_id == tenant_id)
        checklist_items = (await self.session.execute(cl_stmt)).scalars().all()

        for item in checklist_items:
            is_valid = val_results.get(item.key, False)
            if is_valid:
                item.status = "COMPLETED"
                item.completion_percentage = 100.0
                if not item.completed_at:
                    item.completed_at = utc_now()

        await self.session.flush()

        readiness = ReadinessCalculator.calculate(checklist_items, val_results)
        tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
        tenant = (await self.session.execute(tenant_stmt)).scalar_one_or_none()

        if tenant and readiness.readiness_status == "READY":
            await self.lifecycle_manager.transition_state(
                tenant_id=tenant_id,
                target_state="READY",
                reason="Onboarding validation passed minimum readiness score >= 90%",
            )

        return await self.get_onboarding_summary(tenant_id)

    async def complete_onboarding(self, tenant_id: uuid.UUID) -> OnboardingSummaryResponse:
        """Complete onboarding and transition tenant to READY if readiness conditions are satisfied."""
        summary = await self.get_onboarding_summary(tenant_id)
        if summary.readiness_status != "READY" or summary.blocking_items:
            raise ReadinessValidationError(
                f"Cannot complete onboarding: Readiness score is {summary.readiness_score}% "
                f"and blocking items remain: {summary.blocking_items}"
            )

        await self.lifecycle_manager.transition_state(
            tenant_id=tenant_id,
            target_state="READY",
            reason="Onboarding explicitly completed with readiness score >= 90%",
        )

        return await self.get_onboarding_summary(tenant_id)

    async def connect_whatsapp(
        self,
        tenant_id: uuid.UUID,
        connect_req: WhatsAppConnectRequest,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> WhatsAppConnectResponse:
        """Connects WhatsApp Cloud API account after verifying subscription, entitlement, and limits."""
        tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
        tenant = (await self.session.execute(tenant_stmt)).scalar_one_or_none()
        if not tenant:
            raise TenantNotFoundException()

        # 1. Subscription check
        sub = await self.entitlement.get_tenant_subscription(tenant_id)
        if not sub or sub.status in (
            SubscriptionStatus.EXPIRED,
            SubscriptionStatus.ARCHIVED,
            SubscriptionStatus.SUSPENDED,
        ):
            raise AppException(
                code="SUBSCRIPTION_INVALID",
                message="Active subscription or valid trial is required to connect WhatsApp",
                status_code=400,
            )

        # 2. Entitlement check
        can_use_res = await self.entitlement.can_use(tenant_id, "whatsapp_cloud_api")
        if not can_use_res.allowed:
            raise AppException(
                code="ENTITLEMENT_DENIED",
                message=can_use_res.reason or "WhatsApp feature is not enabled for tenant plan",
                status_code=403,
            )

        # 3. Usage Limit check
        conn_limit = await self.entitlement.get_limit(tenant_id, "whatsapp_connections")
        if conn_limit != -1:
            active_stmt = (
                select(func.count(IntegrationConnection.id))
                .join(Integration, IntegrationConnection.integration_id == Integration.id)
                .where(
                    and_(
                        IntegrationConnection.tenant_id == tenant_id,
                        IntegrationConnection.status.in_(["ACTIVE", "CONNECTED"]),
                        Integration.provider_key.in_(["whatsapp_cloud_api", "whatsapp"]),
                    )
                )
            )
            active_count = (await self.session.execute(active_stmt)).scalar() or 0

            # Find connection for THIS specific external account if updating
            existing_conn_stmt = (
                select(IntegrationConnection)
                .join(Integration, IntegrationConnection.integration_id == Integration.id)
                .where(
                    and_(
                        IntegrationConnection.tenant_id == tenant_id,
                        IntegrationConnection.external_account_id == connect_req.phone_number_id,
                        Integration.provider_key.in_(["whatsapp_cloud_api", "whatsapp"]),
                    )
                )
            )
            existing_conn = (await self.session.execute(existing_conn_stmt)).scalars().first()

            if active_count >= conn_limit and not (existing_conn and existing_conn.status in ("ACTIVE", "CONNECTED")):
                raise AppException(
                    code="CONNECTION_LIMIT_EXCEEDED",
                    message=f"WhatsApp connection limit ({conn_limit}) reached for current plan",
                    status_code=403,
                )

        await publish_integration_event(
            tenant_id=tenant_id,
            event_type="whatsapp.connection_requested",
            payload={"phone_number_id": connect_req.phone_number_id},
        )

        # Ensure system Integration record exists for whatsapp_cloud_api
        int_stmt = select(Integration).where(Integration.integration_key == "whatsapp_cloud_api")
        integration = (await self.session.execute(int_stmt)).scalars().first()
        if not integration:
            integration = Integration(
                integration_key="whatsapp_cloud_api",
                provider_key="whatsapp_cloud_api",
                display_name="WhatsApp Cloud API",
                category="messaging",
                is_enabled=True,
            )
            self.session.add(integration)
            await self.session.flush()

        credentials = {
            "phone_number_id": connect_req.phone_number_id,
            "access_token": connect_req.access_token,
            "waba_id": connect_req.waba_id,
            "app_secret": connect_req.app_secret,
            "webhook_secret": connect_req.webhook_secret,
        }

        try:
            connection = await self.integration_service.connect_integration(
                tenant_id=tenant_id,
                integration_key="whatsapp_cloud_api",
                credentials=credentials,
                external_account_id=connect_req.phone_number_id,
                config=connect_req.config,
                actor_permissions=actor_permissions,
            )
        except PermissionDeniedError as exc:
            raise AppException(code="PERMISSION_DENIED", message=str(exc), status_code=403)
        except IntegrationError as exc:
            raise AppException(code="INTEGRATION_ERROR", message=str(exc), status_code=400)

        is_verified = connection.status in ("ACTIVE", "CONNECTED")

        event_type = "whatsapp.connection_connected" if is_verified else "whatsapp.connection_failed"
        await publish_integration_event(
            tenant_id=tenant_id,
            event_type=event_type,
            payload={
                "connection_id": str(connection.id),
                "phone_number_id": connect_req.phone_number_id,
                "status": connection.status,
            },
        )

        if is_verified:
            cl_stmt = select(OnboardingChecklist).where(
                OnboardingChecklist.tenant_id == tenant_id,
                OnboardingChecklist.key == "whatsapp_integration_available",
            )
            cl_item = (await self.session.execute(cl_stmt)).scalar_one_or_none()
            if cl_item:
                cl_item.status = "COMPLETED"
                cl_item.completion_percentage = 100.0
                cl_item.completed_at = utc_now()
                await self.session.flush()

        audit = ProvisioningAudit(
            tenant_id=tenant_id,
            action="WHATSAPP_CONNECT",
            previous_state=tenant.lifecycle_state,
            new_state=tenant.lifecycle_state,
            actor="onboarding_service",
            reason=f"Connected WhatsApp phone_number_id {connect_req.phone_number_id} with status {connection.status}",
            result="SUCCESS" if is_verified else "FAILED",
        )
        self.session.add(audit)
        await self.session.flush()

        return WhatsAppConnectResponse(
            connection_id=connection.id,
            status=connection.status,
            phone_number_id=connect_req.phone_number_id,
            waba_id=connect_req.waba_id,
            is_verified=is_verified,
            created_at=connection.created_at,
        )

    async def verify_whatsapp_connection(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> WhatsAppVerifyResponse:
        """Verifies WhatsApp Cloud API connection health and credentials."""
        try:
            self.integration_service._check_permission(actor_permissions, "VIEW_INTEGRATIONS")
        except PermissionDeniedError as exc:
            raise AppException(code="PERMISSION_DENIED", message=str(exc), status_code=403)

        connection = await self.integration_service._get_connection(tenant_id, connection_id)
        if not connection:
            raise AppException(code="CONNECTION_NOT_FOUND", message="WhatsApp connection not found", status_code=404)

        cred_stmt = select(IntegrationCredential).where(
            and_(
                IntegrationCredential.tenant_id == tenant_id,
                IntegrationCredential.connection_id == connection_id,
                IntegrationCredential.revoked_at == None,
            )
        )
        cred = (await self.session.execute(cred_stmt)).scalar_one_or_none()
        if not cred:
            raise AppException(code="CREDENTIAL_NOT_FOUND", message="Credentials for connection not found", status_code=404)

        creds_dict = self.integration_service.vault.decrypt_credentials(cred.encrypted_secret)
        adapter = integration_registry.get_adapter(connection.integration.provider_key)

        is_healthy = await adapter.health_check(
            tenant_id=tenant_id,
            connection_id=connection_id,
            credentials=creds_dict,
            session=self.session,
        )

        if is_healthy:
            connection.status = "ACTIVE"
            connection.last_success_at = utc_now()
            connection.error_message = None
            msg = "WhatsApp connection verified successfully."
            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="whatsapp.connection_verified",
                payload={"connection_id": str(connection_id), "status": "ACTIVE"},
            )
        else:
            connection.status = "ERROR"
            connection.last_error_at = utc_now()
            connection.error_message = "WhatsApp health check verification failed"
            msg = "WhatsApp connection health check failed."
            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="whatsapp.connection_failed",
                payload={"connection_id": str(connection_id), "status": "ERROR"},
            )

        await self.session.commit()

        return WhatsAppVerifyResponse(
            connection_id=connection_id,
            status=connection.status,
            is_verified=is_healthy,
            phone_number_id=creds_dict.get("phone_number_id"),
            message=msg,
        )

    async def reconnect_whatsapp(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        connect_req: WhatsAppConnectRequest,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> WhatsAppConnectResponse:
        """Re-authenticates and reconnects an existing WhatsApp integration connection safely without creating duplicate connection records."""
        connection = await self.integration_service._get_connection(tenant_id, connection_id)
        if not connection:
            raise AppException(code="CONNECTION_NOT_FOUND", message="WhatsApp connection not found", status_code=404)

        res = await self.connect_whatsapp(tenant_id, connect_req, actor_permissions=actor_permissions)

        await publish_integration_event(
            tenant_id=tenant_id,
            event_type="whatsapp.connection_reconnected",
            payload={"connection_id": str(connection_id), "status": res.status},
        )
        return WhatsAppConnectResponse(
            connection_id=connection_id,
            status=res.status,
            phone_number_id=res.phone_number_id,
            waba_id=res.waba_id,
            is_verified=res.is_verified,
            created_at=connection.created_at,
        )

    async def disconnect_whatsapp(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> WhatsAppConnectResponse:
        """Disconnects WhatsApp connection and revokes credentials."""
        try:
            connection = await self.integration_service.disconnect_integration(
                tenant_id=tenant_id,
                connection_id=connection_id,
                actor_permissions=actor_permissions,
            )
        except PermissionDeniedError as exc:
            raise AppException(code="PERMISSION_DENIED", message=str(exc), status_code=403)
        except IntegrationError as exc:
            raise AppException(code="INTEGRATION_ERROR", message=str(exc), status_code=400)

        await publish_integration_event(
            tenant_id=tenant_id,
            event_type="whatsapp.connection_disconnected",
            payload={"connection_id": str(connection_id), "status": "DISCONNECTED"},
        )

        return WhatsAppConnectResponse(
            connection_id=connection_id,
            status="DISCONNECTED",
            phone_number_id=connection.external_account_id or "",
            is_verified=False,
            created_at=connection.created_at,
        )

    async def run_ai_test(
        self,
        tenant_id: uuid.UUID,
        test_req: AITestRequest | None = None,
    ) -> AITestResponse:
        """Executes a deterministic AI readiness test gate using AIGateway."""
        tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
        tenant = (await self.session.execute(tenant_stmt)).scalar_one_or_none()
        if not tenant:
            raise TenantNotFoundException()

        prompt_msg = (test_req.test_message if test_req and test_req.test_message else "Hello, please confirm AI assistant status for this store.")

        ai_req = AIRequest(
            tenant_id=tenant_id,
            user_message=prompt_msg,
            system_instruction="You are an AI store assistant performing an automated onboarding test. Confirm store readiness concisely.",
            task_type="ai_test",
            temperature=0.1,
        )

        gateway = AIGateway()
        test_resp = await gateway.generate(ai_req, db_session=self.session)

        success = bool(test_resp and test_resp.text and test_resp.text.strip())
        now = utc_now()

        await publish_integration_event(
            tenant_id=tenant_id,
            event_type="tenant.ai_test_completed",
            payload={"success": success, "model": test_resp.model if test_resp else "unknown"},
        )

        return AITestResponse(
            success=success,
            ai_gateway_status="REACHABLE" if success else "UNREACHABLE",
            sample_response=test_resp.text if test_resp else None,
            details={
                "model": test_resp.model if test_resp else None,
                "tokens_used": test_resp.total_tokens if test_resp else 0,
            },
            tested_at=now,
        )

    async def activate_tenant(
        self,
        tenant_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
    ) -> TenantActivationResponse:
        """Activation gate to transition tenant to ACTIVE after satisfying all eligibility and readiness requirements."""
        try:
            self.integration_service._check_permission(actor_permissions, "MANAGE_INTEGRATIONS")
        except PermissionDeniedError as exc:
            raise AppException(code="PERMISSION_DENIED", message=str(exc), status_code=403)

        tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
        tenant = (await self.session.execute(tenant_stmt)).scalar_one_or_none()
        if not tenant:
            raise TenantNotFoundException()

        if tenant.lifecycle_state == "ACTIVE":
            summary = await self.get_onboarding_summary(tenant_id)
            prev = getattr(tenant, "previous_state", "READY") or "READY"
            return TenantActivationResponse(
                tenant_id=tenant_id,
                previous_state=prev,
                current_state="ACTIVE",
                activated_at=tenant.state_transition_at or utc_now(),
                readiness_score=summary.readiness_score,
                summary=summary,
            )

        # 1. Subscription check
        sub = await self.entitlement.get_tenant_subscription(tenant_id)
        if not sub or sub.status in (
            SubscriptionStatus.EXPIRED,
            SubscriptionStatus.ARCHIVED,
            SubscriptionStatus.SUSPENDED,
        ):
            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="tenant.activation_blocked",
                payload={"reason": "Invalid or expired subscription"},
            )
            raise AppException(
                code="ACTIVATION_BLOCKED",
                message="Tenant subscription is expired or inactive",
                status_code=400,
            )

        # 2. Entitlement check
        can_use_res = await self.entitlement.can_use(tenant_id, "whatsapp_cloud_api")
        if not can_use_res.allowed:
            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="tenant.activation_blocked",
                payload={"reason": "Missing whatsapp_cloud_api entitlement"},
            )
            raise AppException(
                code="ACTIVATION_BLOCKED",
                message=f"Missing required entitlement: {can_use_res.reason}",
                status_code=403,
            )

        # 3. Readiness check
        summary = await self.get_onboarding_summary(tenant_id)
        if summary.readiness_status != "READY" or summary.blocking_items:
            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="tenant.activation_blocked",
                payload={"reason": f"Readiness score {summary.readiness_score}% with blocking items: {summary.blocking_items}"},
            )
            raise ReadinessValidationError(
                f"Activation blocked: Readiness score is {summary.readiness_score}% "
                f"and blocking items remain: {summary.blocking_items}"
            )

        # 4. WhatsApp connection check
        wa_conn_stmt = (
            select(IntegrationConnection)
            .join(Integration, IntegrationConnection.integration_id == Integration.id)
            .where(
                and_(
                    IntegrationConnection.tenant_id == tenant_id,
                    IntegrationConnection.status.in_(["ACTIVE", "CONNECTED"]),
                    Integration.provider_key.in_(["whatsapp_cloud_api", "whatsapp"]),
                )
            )
        )
        wa_conn = (await self.session.execute(wa_conn_stmt)).scalars().first()
        if not wa_conn:
            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="tenant.activation_blocked",
                payload={"reason": "No active WhatsApp connection found"},
            )
            raise AppException(
                code="ACTIVATION_BLOCKED",
                message="Active WhatsApp Cloud API connection is required for tenant activation",
                status_code=400,
            )

        prev_state = tenant.lifecycle_state
        if prev_state not in ("READY", "SUSPENDED"):
            await self.lifecycle_manager.transition_state(
                tenant_id=tenant_id,
                target_state="READY",
                reason="Pre-activation state transition to READY",
            )

        await publish_integration_event(
            tenant_id=tenant_id,
            event_type="tenant.activation_ready",
            payload={"tenant_id": str(tenant_id)},
        )

        tenant = await self.lifecycle_manager.transition_state(
            tenant_id=tenant_id,
            target_state="ACTIVE",
            reason="Tenant onboarding, WhatsApp connection, and activation gate satisfied",
        )

        await publish_integration_event(
            tenant_id=tenant_id,
            event_type="tenant.activated",
            payload={"tenant_id": str(tenant_id), "activated_at": utc_now().isoformat()},
        )

        summary_final = await self.get_onboarding_summary(tenant_id)
        return TenantActivationResponse(
            tenant_id=tenant_id,
            previous_state=prev_state,
            current_state="ACTIVE",
            activated_at=tenant.state_transition_at or utc_now(),
            readiness_score=summary_final.readiness_score,
            summary=summary_final,
        )
