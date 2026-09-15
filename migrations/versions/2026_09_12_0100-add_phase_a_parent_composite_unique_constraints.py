"""add_phase_a_parent_composite_unique_constraints

Revision ID: add_phase_a_parent_comp_uniq
Revises: add_platform_owner_col
Create Date: 2026-09-12 01:00:00.000000+00:00

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'add_phase_a_parent_comp_uniq'
down_revision: Union[str, None] = 'add_platform_owner_col'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        tables = [
            ("workflow_configurations", "uq_workflow_configurations_tenant_id"),
            ("workflow_executions", "uq_workflow_executions_tenant_id"),
            ("customers", "uq_customers_tenant_id"),
            ("conversations", "uq_conversations_tenant_id"),
            ("orders", "uq_orders_tenant_id"),
            ("products", "uq_products_tenant_id"),
            ("integration_connections", "uq_integration_connections_tenant_id"),
            ("subscriptions", "uq_subscriptions_tenant_id"),
            ("invoices", "uq_invoices_tenant_id"),
        ]
        for tbl, cname in tables:
            with op.batch_alter_table(tbl) as batch_op:
                batch_op.create_unique_constraint(cname, ["tenant_id", "id"])
    else:
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
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        tables = [
            ("invoices", "uq_invoices_tenant_id"),
            ("subscriptions", "uq_subscriptions_tenant_id"),
            ("integration_connections", "uq_integration_connections_tenant_id"),
            ("products", "uq_products_tenant_id"),
            ("orders", "uq_orders_tenant_id"),
            ("conversations", "uq_conversations_tenant_id"),
            ("customers", "uq_customers_tenant_id"),
            ("workflow_executions", "uq_workflow_executions_tenant_id"),
            ("workflow_configurations", "uq_workflow_configurations_tenant_id"),
        ]
        for tbl, cname in tables:
            with op.batch_alter_table(tbl) as batch_op:
                batch_op.drop_constraint(cname, type_="unique")
    else:
        op.drop_constraint("uq_invoices_tenant_id", "invoices", type_="unique")
        op.drop_constraint("uq_subscriptions_tenant_id", "subscriptions", type_="unique")
        op.drop_constraint("uq_integration_connections_tenant_id", "integration_connections", type_="unique")
        op.drop_constraint("uq_products_tenant_id", "products", type_="unique")
        op.drop_constraint("uq_orders_tenant_id", "orders", type_="unique")
        op.drop_constraint("uq_conversations_tenant_id", "conversations", type_="unique")
        op.drop_constraint("uq_customers_tenant_id", "customers", type_="unique")
        op.drop_constraint("uq_workflow_executions_tenant_id", "workflow_executions", type_="unique")
        op.drop_constraint("uq_workflow_configurations_tenant_id", "workflow_configurations", type_="unique")
