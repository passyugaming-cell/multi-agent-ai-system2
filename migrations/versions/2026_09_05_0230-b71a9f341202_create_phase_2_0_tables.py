"""create_phase_2_0_tables

Revision ID: b71a9f341202
Revises: a0e47a600bbf
Create Date: 2026-09-05 02:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b71a9f341202"
down_revision: Union[str, None] = "a0e47a600bbf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update workflow_configurations with phase 2.0 fields
    op.add_column("workflow_configurations", sa.Column("trigger_type", sa.String(length=100), nullable=True))
    op.add_column("workflow_configurations", sa.Column("trigger_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("workflow_configurations", sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("workflow_configurations", sa.Column("actions", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("workflow_configurations", sa.Column("max_execution_time", sa.Integer(), server_default="300", nullable=False))
    op.add_column("workflow_configurations", sa.Column("max_steps", sa.Integer(), server_default="50", nullable=False))
    op.add_column("workflow_configurations", sa.Column("max_retries", sa.Integer(), server_default="3", nullable=False))

    op.create_index("ix_workflow_configurations_trigger_type", "workflow_configurations", ["trigger_type"], unique=False)
    op.create_index("ix_workflow_configurations_tenant_active", "workflow_configurations", ["tenant_id", "is_active"], unique=False)

    # 2. Create workflow_executions table
    op.create_table(
        "workflow_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflow_configurations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "workflow_id", "event_id", name="uq_workflow_executions_idempotency"),
    )
    op.create_index("ix_workflow_executions_tenant_id", "workflow_executions", ["tenant_id"], unique=False)
    op.create_index("ix_workflow_executions_workflow_id", "workflow_executions", ["workflow_id"], unique=False)
    op.create_index("ix_workflow_executions_event_id", "workflow_executions", ["event_id"], unique=False)
    op.create_index("ix_workflow_executions_correlation_id", "workflow_executions", ["correlation_id"], unique=False)
    op.create_index("ix_workflow_executions_status", "workflow_executions", ["status"], unique=False)
    op.create_index("ix_workflow_executions_tenant_status", "workflow_executions", ["tenant_id", "status"], unique=False)
    op.create_index("ix_workflow_executions_next_retry", "workflow_executions", ["next_retry_at"], unique=False)

    # 3. Create workflow_execution_history table
    op.create_table(
        "workflow_execution_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=True),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("actor_or_source", sa.String(length=255), nullable=False, server_default="workflow_engine"),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_execution_id"], ["workflow_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_execution_history_tenant_id", "workflow_execution_history", ["tenant_id"], unique=False)
    op.create_index("ix_workflow_execution_history_workflow_execution_id", "workflow_execution_history", ["workflow_execution_id"], unique=False)
    op.create_index("ix_workflow_execution_history_tenant_exec", "workflow_execution_history", ["tenant_id", "workflow_execution_id"], unique=False)

    # 4. Create tasks table
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("task_type", sa.String(length=100), nullable=False, server_default="general"),
        sa.Column("priority", sa.String(length=50), nullable=False, server_default="NORMAL"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="CREATED"),
        sa.Column("source", sa.String(length=100), nullable=False, server_default="manual"),
        sa.Column("assigned_to", sa.String(length=255), nullable=True),
        sa.Column("assigned_agent", sa.String(length=255), nullable=True),
        sa.Column("workflow_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_execution_id"], ["workflow_executions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_tenant_id", "tasks", ["tenant_id"], unique=False)
    op.create_index("ix_tasks_status", "tasks", ["status"], unique=False)
    op.create_index("ix_tasks_workflow_execution_id", "tasks", ["workflow_execution_id"], unique=False)
    op.create_index("ix_tasks_tenant_status", "tasks", ["tenant_id", "status"], unique=False)
    op.create_index("ix_tasks_tenant_assigned", "tasks", ["tenant_id", "assigned_to"], unique=False)

    # 5. Create approvals table
    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("action_type", sa.String(length=100), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(length=50), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=255), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_execution_id"], ["workflow_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approvals_tenant_id", "approvals", ["tenant_id"], unique=False)
    op.create_index("ix_approvals_workflow_execution_id", "approvals", ["workflow_execution_id"], unique=False)
    op.create_index("ix_approvals_task_id", "approvals", ["task_id"], unique=False)
    op.create_index("ix_approvals_status", "approvals", ["status"], unique=False)
    op.create_index("ix_approvals_tenant_status", "approvals", ["tenant_id", "status"], unique=False)

    # 6. Create event_records table
    op.create_table(
        "event_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("causation_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "event_id", name="uq_event_records_tenant_event_id"),
    )
    op.create_index("ix_event_records_tenant_id", "event_records", ["tenant_id"], unique=False)
    op.create_index("ix_event_records_event_id", "event_records", ["event_id"], unique=False)
    op.create_index("ix_event_records_event_type", "event_records", ["event_type"], unique=False)
    op.create_index("ix_event_records_correlation_id", "event_records", ["correlation_id"], unique=False)
    op.create_index("ix_event_records_idempotency_key", "event_records", ["idempotency_key"], unique=False)
    op.create_index("ix_event_records_tenant_type", "event_records", ["tenant_id", "event_type"], unique=False)


def downgrade() -> None:
    op.drop_table("event_records")
    op.drop_table("approvals")
    op.drop_table("tasks")
    op.drop_table("workflow_execution_history")
    op.drop_table("workflow_executions")

    op.drop_index("ix_workflow_configurations_tenant_active", table_name="workflow_configurations")
    op.drop_index("ix_workflow_configurations_trigger_type", table_name="workflow_configurations")
    op.drop_column("workflow_configurations", "max_retries")
    op.drop_column("workflow_configurations", "max_steps")
    op.drop_column("workflow_configurations", "max_execution_time")
    op.drop_column("workflow_configurations", "actions")
    op.drop_column("workflow_configurations", "conditions")
    op.drop_column("workflow_configurations", "trigger_config")
    op.drop_column("workflow_configurations", "trigger_type")
