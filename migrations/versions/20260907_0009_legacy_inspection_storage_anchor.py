"""source-faithful inspection storage anchors

Revision ID: 20260907_0009
Revises: 20260905_0008
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260907_0009"
down_revision = "20260905_0008"
branch_labels = None
depends_on = None


def _uuid() -> sa.UUID:
    return sa.UUID(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "legacy_inspection_storage_anchor",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("case_id", _uuid(), nullable=False),
        sa.Column("source_sheet", sa.String(64), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("registration_submission_raw", sa.Text(), nullable=False),
        sa.Column("registration_submission_year", sa.Integer()),
        sa.Column("registration_submission_status", sa.String(16), nullable=False),
        sa.Column("inspection_date_raw", sa.Text(), nullable=False),
        sa.Column("inspection_year", sa.Integer()),
        sa.Column("inspection_year_status", sa.String(16), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("source_version", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["case.id"]),
        sa.UniqueConstraint("case_id"),
        sa.UniqueConstraint("source_sheet", "source_row"),
        sa.CheckConstraint(
            "registration_submission_status IN ('usable', 'unavailable', 'conflict')",
            name="storage_anchor_registration_status",
        ),
        sa.CheckConstraint(
            "inspection_year_status IN ('usable', 'unavailable', 'conflict')",
            name="storage_anchor_inspection_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("legacy_inspection_storage_anchor")
