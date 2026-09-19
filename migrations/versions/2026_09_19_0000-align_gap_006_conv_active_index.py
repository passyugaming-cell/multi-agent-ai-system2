"""align_gap_006_conv_active_index

Revision ID: align_gap006_conv_idx
Revises: add_r3_wa_db_invariants
Create Date: 2026-09-19 00:00:00.000000+00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'align_gap006_conv_idx'
down_revision: Union[str, None] = 'add_r3_wa_db_invariants'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("conversations"):
        existing_indexes = [i["name"] for i in inspector.get_indexes("conversations")]
        if "uq_active_conversations_tenant_customer_channel" in existing_indexes:
            op.drop_index("uq_active_conversations_tenant_customer_channel", table_name="conversations")

        dup_conv_check = sa.text("""
            SELECT tenant_id, customer_id, channel, COUNT(*) as cnt
            FROM conversations
            WHERE status IN ('OPEN', 'PENDING', 'WAITING_HUMAN', 'HUMAN_HANDLING', 'HUMAN_ACTIVE')
            GROUP BY tenant_id, customer_id, channel
            HAVING COUNT(*) > 1
        """)
        dups_conv = conn.execute(dup_conv_check).fetchall()
        if dups_conv:
            dup_desc = ", ".join([f"(tenant={r[0]}, customer={r[1]}, channel={r[2]}, count={r[3]})" for r in dups_conv])
            raise Exception(f"Migration blocked: Duplicate active conversations found for aligned statuses: {dup_desc}")

        op.create_index(
            "uq_active_conversations_tenant_customer_channel",
            "conversations",
            ["tenant_id", "customer_id", "channel"],
            unique=True,
            postgresql_where=sa.text("status IN ('OPEN', 'PENDING', 'WAITING_HUMAN', 'HUMAN_HANDLING', 'HUMAN_ACTIVE')"),
            sqlite_where=sa.text("status IN ('OPEN', 'PENDING', 'WAITING_HUMAN', 'HUMAN_HANDLING', 'HUMAN_ACTIVE')"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("conversations"):
        existing_indexes = [i["name"] for i in inspector.get_indexes("conversations")]
        if "uq_active_conversations_tenant_customer_channel" in existing_indexes:
            op.drop_index("uq_active_conversations_tenant_customer_channel", table_name="conversations")

        op.create_index(
            "uq_active_conversations_tenant_customer_channel",
            "conversations",
            ["tenant_id", "customer_id", "channel"],
            unique=True,
            postgresql_where=sa.text("status IN ('OPEN', 'WAITING_HUMAN', 'HUMAN_ACTIVE')"),
            sqlite_where=sa.text("status IN ('OPEN', 'WAITING_HUMAN', 'HUMAN_ACTIVE')"),
        )
