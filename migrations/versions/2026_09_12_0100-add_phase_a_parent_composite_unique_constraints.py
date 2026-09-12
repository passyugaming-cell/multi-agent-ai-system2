"""add_phase_a_parent_composite_unique_constraints

Revision ID: phase_a_parent_composite_unique
Revises: add_platform_owner_col
Create Date: 2026-09-12 01:00:00.000000+00:00

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'phase_a_parent_composite_unique'
down_revision: Union[str, None] = 'add_platform_owner_col'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_workflow_configurations_tenant_id", "workflow_configurations", ["tenant_id", "id"])
    op.create_unique_constraint("uq_workflow_executions_tenant_id", "workflow_executions", ["tenant_id", "id"])
    op.create_unique_constraint("uq_customers_tenant_id", "customers", ["tenant_id", "id"])
    op.create_unique_constraint("uq_conversations_tenant_id", "conversations", ["tenant_id", "id"])
    op.create_unique_constraint("uq_orders_tenant_id", "orders", ["tenant_id", "id"])
    op.create_unique_constraint("uq_products_tenant_id", "products", ["tenant_id", "id"])
    op.create_unique_constraint("uq_integration_connections_tenant_id", "integration_connections", ["tenant_id", "id"])
    op.create_unique_constraint("uq_subscriptions_tenant_id", "subscriptions", ["tenant_id", "id"])
    op.create_unique_constraint("uq_invoices_tenant_id", "invoices", ["tenant_id", "id"])


def downgrade() -> None:
    op.drop_constraint("uq_invoices_tenant_id", "invoices", type_="unique")
    op.drop_constraint("uq_subscriptions_tenant_id", "subscriptions", type_="unique")
    op.drop_constraint("uq_integration_connections_tenant_id", "integration_connections", type_="unique")
    op.drop_constraint("uq_products_tenant_id", "products", type_="unique")
    op.drop_constraint("uq_orders_tenant_id", "orders", type_="unique")
    op.drop_constraint("uq_conversations_tenant_id", "conversations", type_="unique")
    op.drop_constraint("uq_customers_tenant_id", "customers", type_="unique")
    op.drop_constraint("uq_workflow_executions_tenant_id", "workflow_executions", type_="unique")
    op.drop_constraint("uq_workflow_configurations_tenant_id", "workflow_configurations", type_="unique")
