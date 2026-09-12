import importlib.util
import pathlib
from sqlalchemy import UniqueConstraint, ForeignKeyConstraint

from app.database.models.workflow import WorkflowConfiguration, WorkflowExecution
from app.database.models.customer import Customer
from app.database.models.conversation import Conversation
from app.database.models.order import Order
from app.database.models.product import Product
from app.database.models.integrations import IntegrationConnection
from app.database.models.billing import Subscription, Invoice

EXPECTED_CONSTRAINTS = {
    WorkflowConfiguration: "uq_workflow_configurations_tenant_id",
    WorkflowExecution: "uq_workflow_executions_tenant_id",
    Customer: "uq_customers_tenant_id",
    Conversation: "uq_conversations_tenant_id",
    Order: "uq_orders_tenant_id",
    Product: "uq_products_tenant_id",
    IntegrationConnection: "uq_integration_connections_tenant_id",
    Subscription: "uq_subscriptions_tenant_id",
    Invoice: "uq_invoices_tenant_id",
}


def test_phase_a_model_unique_constraints_declaration():
    """Verify all 9 parent models declare exact UniqueConstraint('tenant_id', 'id')."""
    for model_cls, expected_name in EXPECTED_CONSTRAINTS.items():
        found = False
        table = model_cls.__table__
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint) and constraint.name == expected_name:
                col_names = [col.name if hasattr(col, 'name') else str(col) for col in constraint.columns]
                assert col_names == ["tenant_id", "id"], f"Model {model_cls.__name__} constraint {expected_name} column order mismatch: {col_names}"
                found = True
                break
        assert found, f"Model {model_cls.__name__} missing expected UniqueConstraint '{expected_name}'"


def test_phase_a_no_composite_foreign_keys_introduced():
    """Verify no composite ForeignKeyConstraints exist on any models."""
    models = [
        WorkflowConfiguration,
        WorkflowExecution,
        Customer,
        Conversation,
        Order,
        Product,
        IntegrationConnection,
        Subscription,
        Invoice,
    ]
    for model_cls in models:
        table = model_cls.__table__
        for constraint in table.constraints:
            if isinstance(constraint, ForeignKeyConstraint):
                assert len(constraint.columns) <= 1, (
                    f"Composite ForeignKeyConstraint found on model {model_cls.__name__}: {constraint}"
                )


def test_phase_a_migration_metadata_and_operations():
    """Verify Phase A Alembic migration revisions and constraint names."""
    migration_path = pathlib.Path(
        "migrations/versions/2026_09_12_0100-add_phase_a_parent_composite_unique_constraints.py"
    )
    assert migration_path.exists(), "Phase A migration file missing"

    spec = importlib.util.spec_from_file_location("phase_a_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "add_phase_a_parent_composite_unique"
    assert module.down_revision == "add_platform_owner_col"

    # Inspect source code of upgrade and downgrade to verify exact 9 constraints
    source = migration_path.read_text()
    for expected_name in EXPECTED_CONSTRAINTS.values():
        assert expected_name in source, f"Migration file missing reference to constraint {expected_name}"

    assert source.count("create_unique_constraint") == 9
    assert source.count("drop_constraint") == 9
    assert "create_foreign_key" not in source
    assert "ForeignKeyConstraint" not in source
