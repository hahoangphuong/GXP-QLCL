"""restore TimestampMixin server defaults for repeatable inspection semantics

Revision ID: 20260913_0014
Revises: 20260913_0013
"""
from alembic import op
import sqlalchemy as sa


revision = "20260913_0014"
down_revision = "20260913_0013"
branch_labels = None
depends_on = None


_TIMESTAMP_COLUMNS = (
    ("inspection_decision", "created_at"),
    ("inspection_decision", "updated_at"),
    ("inspection_minutes_record", "created_at"),
    ("inspection_minutes_record", "updated_at"),
)


def upgrade() -> None:
    for table_name, column_name in _TIMESTAMP_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        )


def downgrade() -> None:
    for table_name, column_name in _TIMESTAMP_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=None,
        )
