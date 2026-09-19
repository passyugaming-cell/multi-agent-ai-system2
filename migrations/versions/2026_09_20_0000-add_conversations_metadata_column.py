"""add_conversations_metadata_column

Revision ID: add_conv_metadata
Revises: align_gap006_conv_idx
Create Date: 2026-09-20 00:00:00.000000+00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'add_conv_metadata'
down_revision: Union[str, None] = 'align_gap006_conv_idx'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("conversations"):
        existing_cols = [c["name"] for c in inspector.get_columns("conversations")]
        if "metadata" not in existing_cols:
            op.add_column("conversations", sa.Column("metadata", JSONB, nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("conversations"):
        existing_cols = [c["name"] for c in inspector.get_columns("conversations")]
        if "metadata" in existing_cols:
            op.drop_column("conversations", "metadata")
