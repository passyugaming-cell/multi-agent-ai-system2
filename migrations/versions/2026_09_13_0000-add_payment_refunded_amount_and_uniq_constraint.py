"""add_payment_refunded_amount_and_provider_uniq_constraint

Revision ID: add_pay_ref_amt_uniq
Revises: add_phase_a_parent_comp_uniq
Create Date: 2026-09-13 00:00:00.000000+00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_pay_ref_amt_uniq'
down_revision: Union[str, None] = 'add_phase_a_parent_comp_uniq'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect_name = conn.dialect.name
    if dialect_name == "sqlite":
        with op.batch_alter_table("payments") as batch_op:
            batch_op.add_column(
                sa.Column("refunded_amount", sa.Numeric(precision=14, scale=2), server_default="0.00", nullable=False)
            )
            batch_op.create_unique_constraint(
                "uq_payments_tenant_provider_payment_id",
                ["tenant_id", "provider", "provider_payment_id"],
            )
    else:
        op.add_column(
            "payments",
            sa.Column("refunded_amount", sa.Numeric(precision=14, scale=2), server_default="0.00", nullable=False),
        )
        op.create_unique_constraint(
            "uq_payments_tenant_provider_payment_id",
            "payments",
            ["tenant_id", "provider", "provider_payment_id"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    dialect_name = conn.dialect.name
    if dialect_name == "sqlite":
        with op.batch_alter_table("payments") as batch_op:
            batch_op.drop_constraint("uq_payments_tenant_provider_payment_id", type_="unique")
            batch_op.drop_column("refunded_amount")
    else:
        op.drop_constraint("uq_payments_tenant_provider_payment_id", "payments", type_="unique")
        op.drop_column("payments", "refunded_amount")
