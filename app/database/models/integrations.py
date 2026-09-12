import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import String, Text, Boolean, Integer, ForeignKey, UniqueConstraint, Index, DateTime, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel


class Integration(BaseModel):
    """Catalog or custom integration definitions."""

    __tablename__ = "integrations"
    __table_args__ = (
        UniqueConstraint("integration_key", "tenant_id", name="uq_integrations_key_tenant"),
        Index("ix_integrations_provider", "provider_key"),
        Index("ix_integrations_tenant", "tenant_id"),
        Index(
            "uq_catalog_integrations_provider",
            "provider_key",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
            sqlite_where=text("tenant_id IS NULL"),
        ),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    integration_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="general", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="AVAILABLE", nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    configuration: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    connections = relationship("IntegrationConnection", back_populates="integration", cascade="all, delete-orphan")


class IntegrationConnection(BaseModel):
    """Tenant-scoped connection instance to an integration provider."""

    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_integration_connections_tenant_id"),
        UniqueConstraint("tenant_id", "integration_id", "external_account_id", name="uq_integration_connections_account"),
        Index("ix_integration_connections_tenant_status", "tenant_id", "status"),
        Index(
            "uq_active_provider_external_account",
            "provider_key",
            "external_account_id",
            unique=True,
            postgresql_where=text("status IN ('ACTIVE', 'CONNECTED', 'CONNECTING') AND external_account_id IS NOT NULL"),
            sqlite_where=text("status IN ('ACTIVE', 'CONNECTED', 'CONNECTING') AND external_account_id IS NOT NULL"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_key: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", index=True
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50), default="DISCONNECTED", nullable=False, index=True
    )  # DISCONNECTED, CONNECTING, CONNECTED, ACTIVE, ERROR, RECONNECTING, EXPIRED, REVOKED, DISABLED

    external_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    integration = relationship("Integration", back_populates="connections")
    credentials = relationship("IntegrationCredential", back_populates="connection", cascade="all, delete-orphan")
    executions = relationship("IntegrationExecution", back_populates="connection", cascade="all, delete-orphan")
    webhooks = relationship("WebhookConfig", back_populates="connection", cascade="all, delete-orphan")


class IntegrationCredential(BaseModel):
    """Encrypted storage for tenant integration credentials."""

    __tablename__ = "integration_credentials"
    __table_args__ = (
        Index("ix_integration_credentials_tenant_conn", "tenant_id", "connection_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integration_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    credential_type: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    connection = relationship("IntegrationConnection", back_populates="credentials")


class IntegrationExecution(BaseModel):
    """Audit log and status tracking for integration operations."""

    __tablename__ = "integration_executions"
    __table_args__ = (
        Index("ix_integration_executions_tenant_status", "tenant_id", "status"),
        Index("ix_integration_executions_idempotency", "tenant_id", "idempotency_key"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integration_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="PENDING", nullable=False, index=True
    )  # PENDING, RUNNING, COMPLETED, FAILED, RETRYING

    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    safe_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    connection = relationship("IntegrationConnection", back_populates="executions")


class WebhookConfig(BaseModel):
    """Inbound and outbound webhook configuration for tenant integrations."""

    __tablename__ = "webhook_configs"
    __table_args__ = (
        Index("ix_webhook_configs_tenant_type", "tenant_id", "webhook_type"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integration_connections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    webhook_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_types: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    connection = relationship("IntegrationConnection", back_populates="webhooks")
