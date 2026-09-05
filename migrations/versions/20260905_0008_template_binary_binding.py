"""template-binding-owned binary locators

Revision ID: 20260905_0008
Revises: 20260901_0007
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260905_0008"
down_revision = "20260901_0007"
branch_labels = None
depends_on = None


def _uuid() -> sa.UUID:
    return sa.UUID(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "template_binary_binding",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("template_binding_id", _uuid(), nullable=False),
        sa.Column("storage_root", sa.String(32), nullable=False),
        sa.Column("storage_relative_path", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["template_binding_id"], ["template_binding.id"], ondelete="CASCADE"),
        sa.CheckConstraint("storage_root = 'template'", name="template_binary_binding_root_template"),
    )
    op.create_index(
        "ix_template_binary_binding_template_binding_id",
        "template_binary_binding",
        ["template_binding_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_template_binary_binding_template_binding_id",
        table_name="template_binary_binding",
    )
    op.drop_table("template_binary_binding")
