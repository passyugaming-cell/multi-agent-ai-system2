import uuid
import logging
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.integrations import (
    Integration,
    IntegrationConnection,
    IntegrationCredential,
    IntegrationExecution,
    WebhookConfig,
)
from sqlalchemy.exc import IntegrityError
from app.integrations.exceptions import (
    IntegrationNotFoundError,
    ConnectionNotFoundError,
    CredentialNotFoundError,
    InvalidStateTransitionError,
    EntitlementDeniedError,
    PermissionDeniedError,
    PermanentIntegrationError,
)
from app.integrations.schemas import OperationExecutionResult
from app.integrations.credentials import CredentialVault, redact_secrets
from app.integrations.registry import integration_registry
from app.integrations.events import publish_integration_event
from app.integrations.idempotency import IntegrationIdempotencyChecker
from app.integrations.retry import execute_with_retry
from app.billing.entitlement import EntitlementResolver
from app.integrations.permissions import (
    VIEW_INTEGRATIONS,
    MANAGE_INTEGRATIONS,
    MANAGE_CREDENTIALS,
    EXECUTE_INTEGRATION,
)

logger = logging.getLogger(__name__)

VALID_TRANSITIONS = {
    "DISCONNECTED": {"CONNECTING", "DISABLED"},
    "CONNECTING": {"CONNECTED", "ERROR", "DISCONNECTED"},
    "CONNECTED": {"ACTIVE", "ERROR", "RECONNECTING", "DISCONNECTED", "EXPIRED", "REVOKED", "DISABLED"},
    "ACTIVE": {"CONNECTED", "CONNECTING", "ERROR", "RECONNECTING", "DISCONNECTED", "EXPIRED", "REVOKED", "DISABLED"},
    "ERROR": {"RECONNECTING", "DISCONNECTED", "CONNECTED", "DISABLED"},
    "RECONNECTING": {"CONNECTED", "ACTIVE", "ERROR", "DISCONNECTED"},
    "EXPIRED": {"RECONNECTING", "DISCONNECTED", "DISABLED"},
    "REVOKED": {"DISCONNECTED", "DISABLED"},
    "DISABLED": {"DISCONNECTED", "CONNECTED"},
}


class IntegrationService:
    """Universal Service Layer for multi-tenant integrations with strict tenant boundary & permission enforcement."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session
        self.vault = CredentialVault()
        self.entitlement = EntitlementResolver(db_session)
        self.idempotency = IntegrationIdempotencyChecker(db_session)

    def _check_permission(
        self,
        actor_permissions: set[str] | list[str] | None,
        required_permission: str,
        allow_internal: bool = False,
    ) -> None:
        if actor_permissions is None:
            if allow_internal:
                return
            raise PermissionDeniedError(required_permission)

        perms_set = set(actor_permissions)
        if required_permission not in perms_set:
            raise PermissionDeniedError(required_permission)

    async def list_integrations(
        self,
        tenant_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
        allow_internal: bool = False,
    ) -> list[Integration]:
        """List all available integrations for tenant."""
        self._check_permission(actor_permissions, VIEW_INTEGRATIONS, allow_internal=allow_internal)
        stmt = select(Integration).where(
            and_(
                Integration.is_enabled == True,
                (Integration.tenant_id == None) | (Integration.tenant_id == tenant_id),
            )
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_tenant_connections(
        self,
        tenant_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
        allow_internal: bool = False,
    ) -> list[IntegrationConnection]:
        """List all integration connections created for tenant."""
        self._check_permission(actor_permissions, VIEW_INTEGRATIONS, allow_internal=allow_internal)
        stmt = (
            select(IntegrationConnection)
            .options(selectinload(IntegrationConnection.integration))
            .where(IntegrationConnection.tenant_id == tenant_id)
            .order_by(IntegrationConnection.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def connect_integration(
        self,
        tenant_id: uuid.UUID,
        integration_key: str,
        credentials: dict[str, Any],
        external_account_id: str | None = None,
        config: dict[str, Any] | None = None,
        actor_permissions: set[str] | list[str] | None = None,
        allow_internal: bool = False,
    ) -> IntegrationConnection:
        """Establishes or updates an integration connection securely."""
        self._check_permission(actor_permissions, MANAGE_INTEGRATIONS, allow_internal=allow_internal)
        self._check_permission(actor_permissions, MANAGE_CREDENTIALS, allow_internal=allow_internal)

        feature_map = {
            "rest_api": "api_access",
            "webhook": "webhooks",
            "google_sheets": "google_sheets",
            "google_calendar": "google_calendar",
            "midtrans": "midtrans_payment",
        }
        required_feature = feature_map.get(integration_key.lower(), "api_access")
        if not await self.entitlement.has_feature(tenant_id, required_feature):
            raise EntitlementDeniedError(required_feature)

        stmt = select(Integration).where(
            and_(
                Integration.integration_key == integration_key,
                (Integration.tenant_id == None) | (Integration.tenant_id == tenant_id),
            )
        )
        integration = (await self.session.execute(stmt)).scalars().first()
        if not integration:
            raise IntegrationNotFoundError(integration_key)

        conn_stmt = select(IntegrationConnection).where(
            and_(
                IntegrationConnection.tenant_id == tenant_id,
                IntegrationConnection.integration_id == integration.id,
            )
        )
        connection = (await self.session.execute(conn_stmt)).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        try:
            if not connection:
                connection = IntegrationConnection(
                    tenant_id=tenant_id,
                    integration_id=integration.id,
                    provider_key=integration.provider_key,
                    status="CONNECTING",
                    external_account_id=external_account_id,
                    meta_data=config,
                )
                self.session.add(connection)
                await self.session.flush()
            else:
                self._validate_transition(connection.status, "CONNECTING")
                connection.status = "CONNECTING"
                connection.provider_key = integration.provider_key
                if external_account_id:
                    connection.external_account_id = external_account_id
                if config:
                    connection.meta_data = config
        except IntegrityError as exc:
            await self.session.rollback()
            self._handle_integrity_error(exc, external_account_id)

        encrypted_str = self.vault.encrypt_credentials(credentials)

        cred_stmt = select(IntegrationCredential).where(
            and_(
                IntegrationCredential.tenant_id == tenant_id,
                IntegrationCredential.connection_id == connection.id,
            )
        )
        credential = (await self.session.execute(cred_stmt)).scalar_one_or_none()

        if credential:
            credential.encrypted_secret = encrypted_str
            credential.revoked_at = None
        else:
            credential = IntegrationCredential(
                tenant_id=tenant_id,
                connection_id=connection.id,
                credential_type="api_key",
                encrypted_secret=encrypted_str,
            )
            self.session.add(credential)

        # Store WebhookConfig if secret or url provided
        webhook_secret = credentials.get("webhook_secret") or credentials.get("secret")
        if webhook_secret:
            web_stmt = select(WebhookConfig).where(
                and_(
                    WebhookConfig.tenant_id == tenant_id,
                    WebhookConfig.connection_id == connection.id,
                )
            )
            web_cfg = (await self.session.execute(web_stmt)).scalar_one_or_none()
            enc_web_secret = self.vault.encrypt_credentials({"secret": webhook_secret})
            if web_cfg:
                web_cfg.encrypted_secret = enc_web_secret
                web_cfg.is_active = True
            else:
                web_cfg = WebhookConfig(
                    tenant_id=tenant_id,
                    connection_id=connection.id,
                    webhook_type="INBOUND",
                    encrypted_secret=enc_web_secret,
                    is_active=True,
                )
                self.session.add(web_cfg)

        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            self._handle_integrity_error(exc, external_account_id)

        adapter = integration_registry.get_adapter(integration.provider_key)
        try:
            connected = await adapter.connect(
                tenant_id=tenant_id,
                connection_id=connection.id,
                credentials=credentials,
                config=config or integration.configuration,
                session=self.session,
            )
            if connected:
                connection.status = "ACTIVE"
                connection.last_connected_at = now
                connection.last_success_at = now
                connection.error_message = None
            else:
                connection.status = "ERROR"
                connection.last_error_at = now
                connection.error_message = "Adapter connect returned False"
        except Exception as e:
            logger.error("Adapter connect failed for tenant %s integration %s: %s", tenant_id, integration_key, e)
            connection.status = "ERROR"
            connection.last_error_at = now
            connection.error_message = redact_secrets(str(e))

        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            self._handle_integrity_error(exc, external_account_id)

        await publish_integration_event(
            tenant_id=tenant_id,
            event_type="integration.connected" if connection.status == "ACTIVE" else "integration.connection_failed",
            payload={
                "connection_id": str(connection.id),
                "integration_key": integration_key,
                "status": connection.status,
            },
        )

        return connection

    async def disconnect_integration(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        actor_permissions: set[str] | list[str] | None = None,
        allow_internal: bool = False,
    ) -> IntegrationConnection:
        """Disconnects an integration and revokes stored credentials."""
        self._check_permission(actor_permissions, MANAGE_INTEGRATIONS, allow_internal=allow_internal)
        connection = await self._get_connection(tenant_id, connection_id)
        self._validate_transition(connection.status, "DISCONNECTED")

        cred_stmt = select(IntegrationCredential).where(
            and_(
                IntegrationCredential.tenant_id == tenant_id,
                IntegrationCredential.connection_id == connection_id,
            )
        )
        credential = (await self.session.execute(cred_stmt)).scalar_one_or_none()

        if credential:
            credential.revoked_at = datetime.now(timezone.utc)
            credentials_dict = self.vault.decrypt_credentials(credential.encrypted_secret)
            adapter = integration_registry.get_adapter(connection.integration.provider_key)
            try:
                await adapter.disconnect(
                    tenant_id=tenant_id,
                    connection_id=connection.id,
                    credentials=credentials_dict,
                    session=self.session,
                )
            except Exception as e:
                logger.warning("Adapter disconnect encountered exception: %s", e)

        connection.status = "DISCONNECTED"
        await self.session.commit()

        await publish_integration_event(
            tenant_id=tenant_id,
            event_type="integration.disconnected",
            payload={"connection_id": str(connection_id), "status": "DISCONNECTED"},
        )

        return connection

    async def execute_operation(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        operation: str,
        params: dict[str, Any],
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        actor_permissions: set[str] | list[str] | None = None,
        allow_internal: bool = False,
    ) -> OperationExecutionResult:
        """Executes an operation deterministically with retries, audit logs, and credential decryption."""
        self._check_permission(actor_permissions, EXECUTE_INTEGRATION, allow_internal=allow_internal)

        if idempotency_key:
            existing = await self.idempotency.get_existing_execution(tenant_id, idempotency_key)
            if existing:
                return OperationExecutionResult(
                    execution_id=existing.id,
                    connection_id=existing.connection_id,
                    operation=existing.operation,
                    status=existing.status,
                    result=existing.response_payload,
                    error_code=existing.error_code,
                    safe_error_message=existing.safe_error_message,
                    started_at=existing.started_at,
                    completed_at=existing.completed_at,
                    retry_count=existing.retry_count,
                )

        connection = await self._get_connection(tenant_id, connection_id)
        if connection.status not in ("ACTIVE", "CONNECTED"):
            raise ConnectionNotFoundError(f"Connection {connection_id} is not active (status: {connection.status})")

        cred_stmt = select(IntegrationCredential).where(
            and_(
                IntegrationCredential.tenant_id == tenant_id,
                IntegrationCredential.connection_id == connection_id,
                IntegrationCredential.revoked_at == None,
            )
        )
        credential = (await self.session.execute(cred_stmt)).scalar_one_or_none()
        if not credential:
            raise CredentialNotFoundError(str(connection_id))

        credentials_dict = self.vault.decrypt_credentials(credential.encrypted_secret)
        adapter = integration_registry.get_adapter(connection.integration.provider_key)

        now = datetime.now(timezone.utc)
        execution = IntegrationExecution(
            tenant_id=tenant_id,
            connection_id=connection_id,
            operation=operation,
            status="RUNNING",
            idempotency_key=idempotency_key,
            correlation_id=correlation_id or f"corr_{uuid.uuid4().hex[:12]}",
            started_at=now,
            request_payload=redact_secrets(params),
        )
        self.session.add(execution)
        await self.session.flush()

        try:
            async def _run():
                return await adapter.execute(
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    credentials=credentials_dict,
                    operation=operation,
                    params=params,
                    session=self.session,
                )

            res = await execute_with_retry(_run, max_retries=3)

            execution.status = "COMPLETED"
            execution.completed_at = datetime.now(timezone.utc)
            execution.response_payload = redact_secrets(res)

            connection.last_success_at = datetime.now(timezone.utc)
            connection.error_message = None

            await self.session.commit()

            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="integration.operation_succeeded",
                payload={
                    "execution_id": str(execution.id),
                    "connection_id": str(connection_id),
                    "operation": operation,
                },
                correlation_id=execution.correlation_id,
                idempotency_key=idempotency_key,
            )

            return OperationExecutionResult(
                execution_id=execution.id,
                connection_id=connection_id,
                operation=operation,
                status="COMPLETED",
                result=execution.response_payload,
                started_at=execution.started_at,
                completed_at=execution.completed_at,
            )

        except Exception as e:
            logger.error("Integration operation execution failed: %s", e)
            execution.status = "FAILED"
            execution.completed_at = datetime.now(timezone.utc)
            execution.safe_error_message = redact_secrets(str(e))
            execution.error_code = getattr(e, "error_code", "EXECUTION_FAILED")

            connection.last_error_at = datetime.now(timezone.utc)
            connection.error_message = execution.safe_error_message

            await self.session.commit()

            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="integration.operation_failed",
                payload={
                    "execution_id": str(execution.id),
                    "connection_id": str(connection_id),
                    "operation": operation,
                    "error": execution.safe_error_message,
                },
                correlation_id=execution.correlation_id,
                idempotency_key=idempotency_key,
            )

            return OperationExecutionResult(
                execution_id=execution.id,
                connection_id=connection_id,
                operation=operation,
                status="FAILED",
                error_code=execution.error_code,
                safe_error_message=execution.safe_error_message,
                started_at=execution.started_at,
                completed_at=execution.completed_at,
            )

    async def get_connection_by_provider(
        self,
        tenant_id: uuid.UUID,
        provider_key: str,
        actor_permissions: set[str] | list[str] | None = None,
        allow_internal: bool = False,
    ) -> IntegrationConnection | None:
        """Retrieves active connection for tenant and provider key securely."""
        self._check_permission(actor_permissions, VIEW_INTEGRATIONS, allow_internal=allow_internal)
        stmt = (
            select(IntegrationConnection)
            .options(selectinload(IntegrationConnection.integration))
            .join(Integration, IntegrationConnection.integration_id == Integration.id)
            .where(
                and_(
                    IntegrationConnection.tenant_id == tenant_id,
                    IntegrationConnection.status.in_(["ACTIVE", "CONNECTED"]),
                    Integration.provider_key == provider_key.lower().strip(),
                )
            )
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def get_webhook_secret(self, tenant_id: uuid.UUID, provider: str) -> str | None:
        """Resolves active webhook secret for tenant and provider safely."""
        stmt = (
            select(WebhookConfig)
            .join(IntegrationConnection, WebhookConfig.connection_id == IntegrationConnection.id)
            .join(Integration, IntegrationConnection.integration_id == Integration.id)
            .where(
                and_(
                    WebhookConfig.tenant_id == tenant_id,
                    WebhookConfig.is_active == True,
                    Integration.provider_key == provider.lower().strip(),
                )
            )
        )
        cfg = (await self.session.execute(stmt)).scalars().first()
        if cfg and cfg.encrypted_secret:
            return self.vault.decrypt_credentials(cfg.encrypted_secret).get("secret")

        conn_stmt = (
            select(IntegrationConnection)
            .join(Integration, IntegrationConnection.integration_id == Integration.id)
            .where(
                and_(
                    IntegrationConnection.tenant_id == tenant_id,
                    IntegrationConnection.status.in_(["ACTIVE", "CONNECTED"]),
                    Integration.provider_key == provider.lower().strip(),
                )
            )
        )
        conn = (await self.session.execute(conn_stmt)).scalars().first()
        if conn:
            cred_stmt = select(IntegrationCredential).where(
                and_(
                    IntegrationCredential.tenant_id == tenant_id,
                    IntegrationCredential.connection_id == conn.id,
                    IntegrationCredential.revoked_at == None,
                )
            )
            cred = (await self.session.execute(cred_stmt)).scalar_one_or_none()
            if cred:
                creds = self.vault.decrypt_credentials(cred.encrypted_secret)
                return creds.get("webhook_secret") or creds.get("secret") or creds.get("api_key")

        return None

    async def _get_connection(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> IntegrationConnection:
        stmt = (
            select(IntegrationConnection)
            .options(selectinload(IntegrationConnection.integration))
            .where(
                and_(
                    IntegrationConnection.tenant_id == tenant_id,
                    IntegrationConnection.id == connection_id,
                )
            )
        )
        conn = (await self.session.execute(stmt)).scalar_one_or_none()
        if not conn:
            raise ConnectionNotFoundError(str(connection_id))
        return conn

    def _validate_transition(self, current_status: str, target_status: str) -> None:
        allowed = VALID_TRANSITIONS.get(current_status, set())
        if target_status not in allowed and current_status != target_status:
            raise InvalidStateTransitionError(current_status, target_status)

    def _handle_integrity_error(self, exc: IntegrityError, external_account_id: str | None) -> None:
        orig = getattr(exc, "orig", None)

        # 1. PostgreSQL check via DBAPI driver diagnostic info
        diag = getattr(orig, "diag", None)
        if diag is not None:
            cname = getattr(diag, "constraint_name", None)
            if cname == "uq_active_provider_external_account":
                raise PermanentIntegrationError(
                    f"External account '{external_account_id}' is already connected to another tenant.",
                    error_code="ACCOUNT_ALREADY_CONNECTED",
                )
            raise PermanentIntegrationError("Integration database constraint error.", error_code="DATABASE_INTEGRITY_ERROR")

        # 2. SQLite / fallback check strictly targeting the uq_active_provider_external_account index name or columns
        exc_str = str(exc)
        if "uq_active_provider_external_account" in exc_str or "integration_connections.provider_key, integration_connections.external_account_id" in exc_str:
            raise PermanentIntegrationError(
                f"External account '{external_account_id}' is already connected to another tenant.",
                error_code="ACCOUNT_ALREADY_CONNECTED",
            )

        raise PermanentIntegrationError("Integration database constraint error.", error_code="DATABASE_INTEGRITY_ERROR")
