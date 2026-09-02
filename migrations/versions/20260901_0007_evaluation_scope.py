"""canonical evaluation scope persistence

Revision ID: 20260901_0007
Revises: 20260829_0006
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260901_0007"
down_revision = "20260829_0006"
branch_labels = None
depends_on = None


def _uuid() -> sa.UUID:
    return sa.UUID(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "evaluation_scope_taxonomy_version",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("taxonomy_content_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("source_workbook_sha256", sa.String(64)),
        sa.Column("schema_version", sa.String(128), nullable=False),
    )
    op.create_table(
        "evaluation_scope_taxonomy_node",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("taxonomy_version_id", _uuid(), nullable=False),
        sa.Column("parent_node_id", _uuid()),
        sa.Column("gxp_type", sa.String(32), nullable=False),
        sa.Column("source_name", sa.String(64), nullable=False),
        sa.Column("node_key", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("hint", sa.Text()),
        sa.Column("main_topic", sa.String(32)),
        sa.Column("short_render", sa.Text()),
        sa.Column("no_expand", sa.String(32)),
        sa.Column("source_order", sa.Integer(), nullable=False),
        sa.Column("source_excel_row", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["taxonomy_version_id"], ["evaluation_scope_taxonomy_version.id"]),
        sa.ForeignKeyConstraint(
            ["parent_node_id", "taxonomy_version_id", "gxp_type"],
            [
                "evaluation_scope_taxonomy_node.id",
                "evaluation_scope_taxonomy_node.taxonomy_version_id",
                "evaluation_scope_taxonomy_node.gxp_type",
            ],
        ),
        sa.UniqueConstraint("taxonomy_version_id", "gxp_type", "node_key"),
        sa.UniqueConstraint("id", "taxonomy_version_id", "gxp_type"),
    )
    op.create_index("ix_evaluation_scope_taxonomy_node_taxonomy_version_id", "evaluation_scope_taxonomy_node", ["taxonomy_version_id"])
    op.create_index("ix_evaluation_scope_taxonomy_node_parent_node_id", "evaluation_scope_taxonomy_node", ["parent_node_id"])
    op.create_table(
        "case_evaluation_scope",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("case_id", _uuid(), nullable=False, unique=True),
        sa.Column("taxonomy_version_id", _uuid()),
        sa.Column("source_classification", sa.String(64), nullable=False),
        sa.Column("raw_legacy_value", sa.Text(), nullable=False),
        sa.Column("rendered_prose", sa.Text()),
        sa.Column("limitation_text", sa.Text()),
        sa.ForeignKeyConstraint(["case_id"], ["case.id"]),
        sa.ForeignKeyConstraint(["taxonomy_version_id"], ["evaluation_scope_taxonomy_version.id"]),
    )
    op.create_index("ix_case_evaluation_scope_taxonomy_version_id", "case_evaluation_scope", ["taxonomy_version_id"])
    op.create_table(
        "case_evaluation_scope_block",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("case_evaluation_scope_id", _uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column("raw_block_value", sa.Text()),
        sa.ForeignKeyConstraint(["case_evaluation_scope_id"], ["case_evaluation_scope.id"]),
        sa.UniqueConstraint("case_evaluation_scope_id", "ordinal"),
    )
    op.create_index("ix_case_evaluation_scope_block_case_evaluation_scope_id", "case_evaluation_scope_block", ["case_evaluation_scope_id"])
    op.create_table(
        "case_evaluation_scope_selection",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("block_id", _uuid(), nullable=False),
        sa.Column("taxonomy_node_id", _uuid(), nullable=False),
        sa.Column("source_order", sa.Integer(), nullable=False),
        sa.Column("custom_description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("node_key_snapshot", sa.String(64), nullable=False),
        sa.Column("taxonomy_description_snapshot", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["block_id"], ["case_evaluation_scope_block.id"]),
        sa.ForeignKeyConstraint(["taxonomy_node_id"], ["evaluation_scope_taxonomy_node.id"]),
        sa.UniqueConstraint("block_id", "source_order"),
    )
    op.create_index("ix_case_evaluation_scope_selection_block_id", "case_evaluation_scope_selection", ["block_id"])
    op.create_index("ix_case_evaluation_scope_selection_taxonomy_node_id", "case_evaluation_scope_selection", ["taxonomy_node_id"])
    op.create_table(
        "case_evaluation_scope_unkeyed_entry",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("block_id", _uuid(), nullable=False),
        sa.Column("source_order", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["block_id"], ["case_evaluation_scope_block.id"]),
        sa.UniqueConstraint("block_id", "source_order"),
    )
    op.create_index("ix_case_evaluation_scope_unkeyed_entry_block_id", "case_evaluation_scope_unkeyed_entry", ["block_id"])


def downgrade() -> None:
    op.drop_index("ix_case_evaluation_scope_unkeyed_entry_block_id", table_name="case_evaluation_scope_unkeyed_entry")
    op.drop_table("case_evaluation_scope_unkeyed_entry")
    op.drop_index("ix_case_evaluation_scope_selection_taxonomy_node_id", table_name="case_evaluation_scope_selection")
    op.drop_index("ix_case_evaluation_scope_selection_block_id", table_name="case_evaluation_scope_selection")
    op.drop_table("case_evaluation_scope_selection")
    op.drop_index("ix_case_evaluation_scope_block_case_evaluation_scope_id", table_name="case_evaluation_scope_block")
    op.drop_table("case_evaluation_scope_block")
    op.drop_index("ix_case_evaluation_scope_taxonomy_version_id", table_name="case_evaluation_scope")
    op.drop_table("case_evaluation_scope")
    op.drop_index("ix_evaluation_scope_taxonomy_node_parent_node_id", table_name="evaluation_scope_taxonomy_node")
    op.drop_index("ix_evaluation_scope_taxonomy_node_taxonomy_version_id", table_name="evaluation_scope_taxonomy_node")
    op.drop_table("evaluation_scope_taxonomy_node")
    op.drop_table("evaluation_scope_taxonomy_version")
