"""store ordered actual inspection periods without flattening legacy visits

Revision ID: 20260912_0010
Revises: 20260907_0009
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260912_0010"
down_revision = "20260907_0009"
branch_labels = None
depends_on = None


def _uuid() -> sa.UUID:
    return sa.UUID(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "inspection_period_segment",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("inspection_outcome_id", _uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("ended_on", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["inspection_outcome_id"], ["inspection_outcome.id"]),
        sa.UniqueConstraint("inspection_outcome_id", "ordinal"),
        sa.CheckConstraint("started_on <= ended_on", name="inspection_period_segment_date_order"),
    )
    op.create_index("ix_inspection_period_segment_inspection_outcome_id", "inspection_period_segment", ["inspection_outcome_id"])


def downgrade() -> None:
    op.drop_index("ix_inspection_period_segment_inspection_outcome_id", table_name="inspection_period_segment")
    op.drop_table("inspection_period_segment")
