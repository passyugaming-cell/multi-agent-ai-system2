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
    inspector = sa.inspect(conn)
    if not inspector.has_table("payments"):
        return

    # Preflight check: Ensure no pre-existing duplicate (tenant_id, provider, provider_payment_id) rows exist
    dup_check = sa.text("""
        SELECT tenant_id, provider, provider_payment_id, COUNT(*) as cnt
        FROM payments
        WHERE provider_payment_id IS NOT NULL AND provider_payment_id != ''
        GROUP BY tenant_id, provider, provider_payment_id
        HAVING COUNT(*) > 1
    """)
    dups = conn.execute(dup_check).fetchall()
    if dups:
        dup_desc = ", ".join([f"(tenant={r[0]}, provider={r[1]}, provider_payment_id={r[2]}, count={r[3]})" for r in dups])
        raise Exception(
            f"Deployment blocked: Duplicate payment records found before migration. Resolve duplicates before applying uq_payments_tenant_provider_payment_id: {dup_desc}."
        )

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
    inspector = sa.inspect(conn)
    if not inspector.has_table("payments"):
        return

    dialect_name = conn.dialect.name
    if dialect_name == "sqlite":
        with op.batch_alter_table("payments") as batch_op:
            batch_op.drop_constraint("uq_payments_tenant_provider_payment_id", type_="unique")
            batch_op.drop_column("refunded_amount")
    else:
        op.drop_constraint("uq_payments_tenant_provider_payment_id", "payments", type_="unique")
        op.drop_column("payments", "refunded_amount")
