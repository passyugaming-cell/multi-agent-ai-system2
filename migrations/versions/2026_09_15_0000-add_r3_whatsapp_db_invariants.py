"""add_r3_whatsapp_db_invariants

Revision ID: add_r3_wa_db_invariants
Revises: add_pay_ref_amt_uniq
Create Date: 2026-09-15 00:00:00.000000+00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_r3_wa_db_invariants'
down_revision: Union[str, None] = 'add_pay_ref_amt_uniq'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # 1. Messages status column & external_message_id unique index preflight & creation
    if inspector.has_table("messages"):
        cols = [c["name"] for c in inspector.get_columns("messages")]
        if "status" not in cols:
            op.add_column("messages", sa.Column("status", sa.String(length=50), server_default="CREATED", nullable=False))

        dup_msg_check = sa.text("""
            SELECT tenant_id, external_message_id, COUNT(*) as cnt
            FROM messages
            WHERE external_message_id IS NOT NULL AND external_message_id != ''
            GROUP BY tenant_id, external_message_id
            HAVING COUNT(*) > 1
        """)
        dups_msg = conn.execute(dup_msg_check).fetchall()
        if dups_msg:
            dup_desc = ", ".join([f"(tenant={r[0]}, external_id={r[1]}, count={r[2]})" for r in dups_msg])
            raise Exception(f"Migration blocked: Duplicate messages found for external_message_id: {dup_desc}")

        op.create_index(
            "uq_messages_tenant_external_id",
            "messages",
            ["tenant_id", "external_message_id"],
            unique=True,
            postgresql_where=sa.text("external_message_id IS NOT NULL AND external_message_id != ''"),
            sqlite_where=sa.text("external_message_id IS NOT NULL AND external_message_id != ''"),
        )

    # 2. Customers phone unique index preflight & creation
    if inspector.has_table("customers"):
        dup_cust_check = sa.text("""
            SELECT tenant_id, phone, COUNT(*) as cnt
            FROM customers
            WHERE phone IS NOT NULL AND phone != ''
            GROUP BY tenant_id, phone
            HAVING COUNT(*) > 1
        """)
        dups_cust = conn.execute(dup_cust_check).fetchall()
        if dups_cust:
            dup_desc = ", ".join([f"(tenant={r[0]}, phone={r[1]}, count={r[2]})" for r in dups_cust])
            raise Exception(f"Migration blocked: Duplicate customers found for phone: {dup_desc}")

        op.create_index(
            "uq_customers_tenant_phone",
            "customers",
            ["tenant_id", "phone"],
            unique=True,
            postgresql_where=sa.text("phone IS NOT NULL AND phone != ''"),
            sqlite_where=sa.text("phone IS NOT NULL AND phone != ''"),
        )

    # 3. Conversations active channel unique index preflight & creation
    if inspector.has_table("conversations"):
        dup_conv_check = sa.text("""
            SELECT tenant_id, customer_id, channel, COUNT(*) as cnt
            FROM conversations
            WHERE status IN ('OPEN', 'WAITING_HUMAN', 'HUMAN_ACTIVE')
            GROUP BY tenant_id, customer_id, channel
            HAVING COUNT(*) > 1
        """)
        dups_conv = conn.execute(dup_conv_check).fetchall()
        if dups_conv:
            dup_desc = ", ".join([f"(tenant={r[0]}, customer={r[1]}, channel={r[2]}, count={r[3]})" for r in dups_conv])
            raise Exception(f"Migration blocked: Duplicate active conversations found: {dup_desc}")

        op.create_index(
            "uq_active_conversations_tenant_customer_channel",
            "conversations",
            ["tenant_id", "customer_id", "channel"],
            unique=True,
            postgresql_where=sa.text("status IN ('OPEN', 'WAITING_HUMAN', 'HUMAN_ACTIVE')"),
            sqlite_where=sa.text("status IN ('OPEN', 'WAITING_HUMAN', 'HUMAN_ACTIVE')"),
        )

    # 4. Integration executions idempotency_key unique index preflight & creation
    if inspector.has_table("integration_executions"):
        dup_exec_check = sa.text("""
            SELECT tenant_id, idempotency_key, COUNT(*) as cnt
            FROM integration_executions
            WHERE idempotency_key IS NOT NULL AND idempotency_key != ''
            GROUP BY tenant_id, idempotency_key
            HAVING COUNT(*) > 1
        """)
        dups_exec = conn.execute(dup_exec_check).fetchall()
        if dups_exec:
            dup_desc = ", ".join([f"(tenant={r[0]}, idempotency_key={r[1]}, count={r[2]})" for r in dups_exec])
            raise Exception(f"Migration blocked: Duplicate integration executions found: {dup_desc}")

        op.create_index(
            "uq_integration_executions_tenant_idempotency",
            "integration_executions",
            ["tenant_id", "idempotency_key"],
            unique=True,
            postgresql_where=sa.text("idempotency_key IS NOT NULL AND idempotency_key != ''"),
            sqlite_where=sa.text("idempotency_key IS NOT NULL AND idempotency_key != ''"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("integration_executions"):
        op.drop_index("uq_integration_executions_tenant_idempotency", table_name="integration_executions")

    if inspector.has_table("conversations"):
        op.drop_index("uq_active_conversations_tenant_customer_channel", table_name="conversations")

    if inspector.has_table("customers"):
        op.drop_index("uq_customers_tenant_phone", table_name="customers")

    if inspector.has_table("messages"):
        op.drop_index("uq_messages_tenant_external_id", table_name="messages")
        cols = [c["name"] for c in inspector.get_columns("messages")]
        if "status" in cols:
            op.drop_column("messages", "status")
