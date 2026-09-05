"""create_phase_4_0_tables

Revision ID: e4b78f912c34
Revises: b71a9f341202
Create Date: 2026-09-05 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e4b78f912c34"
down_revision: Union[str, None] = "b71a9f341202"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create business_memories table
    op.create_table(
        "business_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_platform_wide", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("memory_type", sa.String(length=50), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False, server_default="system"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="ACTIVE"),
        sa.Column("importance", sa.String(length=50), nullable=False, server_default="NORMAL"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_business_memories_tenant_id", "business_memories", ["tenant_id"], unique=False)
    op.create_index("ix_business_memories_memory_type", "business_memories", ["memory_type"], unique=False)
    op.create_index("ix_business_memories_key", "business_memories", ["key"], unique=False)
    op.create_index("ix_business_memories_status", "business_memories", ["status"], unique=False)
    op.create_index("ix_business_memories_tenant_key", "business_memories", ["tenant_id", "key"], unique=False)
    op.create_index("ix_business_memories_type_status", "business_memories", ["memory_type", "status"], unique=False)

    # 2. Create client_memories table
    op.create_table(
        "client_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memory_type", sa.String(length=50), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False, server_default="system"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="ACTIVE"),
        sa.Column("importance", sa.String(length=50), nullable=False, server_default="NORMAL"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_client_memories_tenant_key"),
    )
    op.create_index("ix_client_memories_tenant_id", "client_memories", ["tenant_id"], unique=False)
    op.create_index("ix_client_memories_memory_type", "client_memories", ["memory_type"], unique=False)
    op.create_index("ix_client_memories_status", "client_memories", ["status"], unique=False)
    op.create_index("ix_client_memories_tenant_status", "client_memories", ["tenant_id", "status"], unique=False)
    op.create_index("ix_client_memories_tenant_type", "client_memories", ["tenant_id", "memory_type"], unique=False)

    # 3. Create memory_change_proposals table
    op.create_table(
        "memory_change_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("memory_scope", sa.String(length=50), nullable=False),
        sa.Column("proposed_key", sa.String(length=255), nullable=False),
        sa.Column("proposed_type", sa.String(length=50), nullable=False),
        sa.Column("proposed_content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_agent", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_change_proposals_tenant_id", "memory_change_proposals", ["tenant_id"], unique=False)
    op.create_index("ix_memory_change_proposals_status", "memory_change_proposals", ["status"], unique=False)
    op.create_index("ix_memory_change_proposals_approval_id", "memory_change_proposals", ["approval_id"], unique=False)
    op.create_index("ix_memory_change_proposals_tenant_status", "memory_change_proposals", ["tenant_id", "status"], unique=False)

    # 4. Create owner_ai_executions table
    op.create_table(
        "owner_ai_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="CREATED"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agents_called", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("tasks_created", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("events_used", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("recommendations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("approvals", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_owner_ai_executions_tenant_id", "owner_ai_executions", ["tenant_id"], unique=False)
    op.create_index("ix_owner_ai_executions_status", "owner_ai_executions", ["status"], unique=False)
    op.create_index("ix_owner_ai_executions_correlation_id", "owner_ai_executions", ["correlation_id"], unique=False)
    op.create_index("ix_owner_ai_executions_tenant_status", "owner_ai_executions", ["tenant_id", "status"], unique=False)

    # 5. Create recommendations table
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("reasoning_summary", sa.Text(), nullable=False),
        sa.Column("expected_benefit", sa.Text(), nullable=False),
        sa.Column("risk", sa.String(length=50), nullable=False, server_default="LOW"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("suggested_action", sa.Text(), nullable=False),
        sa.Column("required_approval", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", sa.String(length=50), nullable=False, server_default="NORMAL"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PROPOSED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_id"], ["owner_ai_executions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recommendations_tenant_id", "recommendations", ["tenant_id"], unique=False)
    op.create_index("ix_recommendations_execution_id", "recommendations", ["execution_id"], unique=False)
    op.create_index("ix_recommendations_approval_id", "recommendations", ["approval_id"], unique=False)
    op.create_index("ix_recommendations_status", "recommendations", ["status"], unique=False)
    op.create_index("ix_recommendations_tenant_status", "recommendations", ["tenant_id", "status"], unique=False)
    op.create_index("ix_recommendations_tenant_priority", "recommendations", ["tenant_id", "priority"], unique=False)


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("owner_ai_executions")
    op.drop_table("memory_change_proposals")
    op.drop_table("client_memories")
    op.drop_table("business_memories")
