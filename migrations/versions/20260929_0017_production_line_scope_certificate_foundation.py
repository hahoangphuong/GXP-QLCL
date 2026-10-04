"""add B6G production-line, regulatory-scope, and certificate foundations

Revision ID: 20260929_0017
Revises: 20260915_0016
"""
from alembic import op
import sqlalchemy as sa


revision = "20260929_0017"
down_revision = "20260915_0016"
branch_labels = None
depends_on = None


def _uuid() -> sa.UUID:
    return sa.UUID(as_uuid=False)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "production_line",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("site_id", _uuid(), sa.ForeignKey("site.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        *_timestamps(),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from < effective_to",
            name="production_line_effective_interval",
        ),
    )
    op.create_index("ix_production_line_site_code", "production_line", ["site_id", "code"])

    op.create_table(
        "production_line_transformation",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("site_id", _uuid(), sa.ForeignKey("site.id"), nullable=False),
        sa.Column("transformation_type", sa.String(16), nullable=False),
        sa.Column("effective_on", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", _uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        *_timestamps(),
        sa.CheckConstraint(
            "transformation_type IN ('MERGE', 'SPLIT')",
            name="production_line_transformation_type_known",
        ),
        sa.CheckConstraint("TRIM(reason) <> ''", name="production_line_transformation_reason_nonblank"),
    )
    op.create_index("ix_production_line_transformation_site_id", "production_line_transformation", ["site_id"])
    op.create_index(
        "ix_production_line_transformation_created_by_user_id",
        "production_line_transformation",
        ["created_by_user_id"],
    )
    op.create_index("ix_production_line_transformation_effective_on", "production_line_transformation", ["effective_on"])
    op.create_table(
        "production_line_transformation_member",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "transformation_id",
            _uuid(),
            sa.ForeignKey("production_line_transformation.id"),
            nullable=False,
        ),
        sa.Column("production_line_id", _uuid(), sa.ForeignKey("production_line.id"), nullable=False),
        sa.Column("member_role", sa.String(8), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "transformation_id",
            "production_line_id",
            name="uq_production_line_transformation_member_line",
        ),
        sa.UniqueConstraint(
            "transformation_id",
            "member_role",
            "ordinal",
            name="uq_production_line_transformation_member_role_ordinal",
        ),
        sa.CheckConstraint(
            "member_role IN ('INPUT', 'OUTPUT')",
            name="production_line_transformation_member_role_known",
        ),
        sa.CheckConstraint("ordinal >= 1", name="production_line_transformation_member_ordinal_positive"),
    )
    op.create_index(
        "ix_production_line_transformation_member_line",
        "production_line_transformation_member",
        ["production_line_id"],
    )

    op.add_column("case", sa.Column("production_line_id", _uuid(), sa.ForeignKey("production_line.id")))
    op.create_index("ix_case_production_line_id", "case", ["production_line_id"])

    op.create_table(
        "case_scope_phase",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("case_id", _uuid(), sa.ForeignKey("case.id"), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        *_timestamps(),
        sa.UniqueConstraint("case_id", "phase"),
        sa.CheckConstraint(
            "phase IN ('REQUESTED', 'ASSESSED', 'INSPECTED', 'CONCLUDED')",
            name="case_scope_phase_phase_known",
        ),
    )
    op.create_table(
        "case_scope_revision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("case_scope_phase_id", _uuid(), sa.ForeignKey("case_scope_phase.id"), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("is_current_established", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("supersedes_revision_id", _uuid()),
        sa.Column("created_by_user_id", _uuid(), sa.ForeignKey("app_user.id")),
        sa.Column("established_at", sa.DateTime(timezone=True)),
        sa.Column("established_by_user_id", _uuid(), sa.ForeignKey("app_user.id")),
        sa.Column("correction_reason", sa.Text()),
        sa.Column("taxonomy_version_id", _uuid(), sa.ForeignKey("evaluation_scope_taxonomy_version.id")),
        sa.Column("source_classification", sa.String(64)),
        sa.Column("raw_legacy_value", sa.Text()),
        sa.Column("rendered_prose", sa.Text()),
        sa.Column("limitation_text", sa.Text()),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        *_timestamps(),
        sa.UniqueConstraint("case_scope_phase_id", "revision_no"),
        sa.UniqueConstraint("id", "case_scope_phase_id"),
        sa.ForeignKeyConstraint(
            ["supersedes_revision_id", "case_scope_phase_id"],
            ["case_scope_revision.id", "case_scope_revision.case_scope_phase_id"],
        ),
        sa.CheckConstraint("revision_no >= 1", name="case_scope_revision_number_positive"),
        sa.CheckConstraint("state IN ('DRAFT', 'ESTABLISHED')", name="case_scope_revision_state_known"),
        sa.CheckConstraint("state <> 'DRAFT' OR NOT is_current_established", name="case_scope_revision_draft_not_current"),
        sa.CheckConstraint(
            "state <> 'ESTABLISHED' OR established_at IS NOT NULL",
            name="case_scope_revision_established_requires_timestamp",
        ),
        sa.CheckConstraint(
            "supersedes_revision_id IS NULL OR supersedes_revision_id <> id",
            name="case_scope_revision_not_self_superseding",
        ),
        sa.CheckConstraint(
            "supersedes_revision_id IS NULL OR NULLIF(TRIM(correction_reason), '') IS NOT NULL",
            name="case_scope_revision_correction_reason_required",
        ),
    )
    op.create_index("ix_case_scope_revision_taxonomy_version_id", "case_scope_revision", ["taxonomy_version_id"])
    op.create_index("ix_case_scope_revision_created_by_user_id", "case_scope_revision", ["created_by_user_id"])
    op.create_index("ix_case_scope_revision_established_by_user_id", "case_scope_revision", ["established_by_user_id"])
    op.create_index(
        "uq_case_scope_revision_one_draft",
        "case_scope_revision",
        ["case_scope_phase_id"],
        unique=True,
        postgresql_where=sa.text("state = 'DRAFT'"),
    )
    op.create_index(
        "uq_case_scope_revision_one_current_established",
        "case_scope_revision",
        ["case_scope_phase_id"],
        unique=True,
        postgresql_where=sa.text("is_current_established"),
    )
    op.create_table(
        "case_scope_revision_block",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("case_scope_revision_id", _uuid(), sa.ForeignKey("case_scope_revision.id"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column("raw_block_value", sa.Text()),
        *_timestamps(),
        sa.UniqueConstraint("case_scope_revision_id", "ordinal"),
        sa.CheckConstraint("ordinal >= 1", name="case_scope_revision_block_ordinal_positive"),
    )
    op.create_index("ix_case_scope_revision_block_case_scope_revision_id", "case_scope_revision_block", ["case_scope_revision_id"])
    op.create_table(
        "case_scope_revision_selection",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("block_id", _uuid(), sa.ForeignKey("case_scope_revision_block.id"), nullable=False),
        sa.Column("taxonomy_node_id", _uuid(), sa.ForeignKey("evaluation_scope_taxonomy_node.id"), nullable=False),
        sa.Column("source_order", sa.Integer(), nullable=False),
        sa.Column("custom_description", sa.Text(), nullable=False, server_default=""),
        sa.Column("node_key_snapshot", sa.String(64), nullable=False),
        sa.Column("taxonomy_description_snapshot", sa.Text(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("block_id", "source_order"),
        sa.CheckConstraint("source_order >= 1", name="case_scope_revision_selection_order_positive"),
    )
    op.create_index("ix_case_scope_revision_selection_block_id", "case_scope_revision_selection", ["block_id"])
    op.create_index("ix_case_scope_revision_selection_taxonomy_node_id", "case_scope_revision_selection", ["taxonomy_node_id"])
    op.create_table(
        "case_scope_revision_unkeyed_entry",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("block_id", _uuid(), sa.ForeignKey("case_scope_revision_block.id"), nullable=False),
        sa.Column("source_order", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("block_id", "source_order"),
        sa.CheckConstraint("source_order >= 1", name="case_scope_revision_unkeyed_order_positive"),
    )
    op.create_index("ix_case_scope_revision_unkeyed_entry_block_id", "case_scope_revision_unkeyed_entry", ["block_id"])

    op.add_column("certificate", sa.Column("production_line_id", _uuid(), sa.ForeignKey("production_line.id")))
    op.create_index("ix_certificate_production_line_id", "certificate", ["production_line_id"])
    op.add_column("certificate_version", sa.Column("lifecycle_state", sa.String(16)))
    op.create_check_constraint(
        "certificate_version_lifecycle_state_known",
        "certificate_version",
        "lifecycle_state IS NULL OR lifecycle_state IN ('DRAFT', 'GRANTED')",
    )
    op.create_table(
        "certificate_relationship",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_certificate_id", _uuid(), sa.ForeignKey("certificate.id"), nullable=False),
        sa.Column("target_certificate_id", _uuid(), sa.ForeignKey("certificate.id"), nullable=False),
        sa.Column("relation_type", sa.String(32), nullable=False),
        sa.Column("effective_on", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("created_by_user_id", _uuid(), sa.ForeignKey("app_user.id")),
        *_timestamps(),
        sa.UniqueConstraint("source_certificate_id", "target_certificate_id", "relation_type"),
        sa.CheckConstraint("source_certificate_id <> target_certificate_id", name="certificate_relationship_not_self"),
        sa.CheckConstraint(
            "relation_type IN ('SUPERSEDED_BY', 'REPLACED_BY')",
            name="certificate_relationship_type_known",
        ),
    )
    op.create_index("ix_certificate_relationship_source_certificate_id", "certificate_relationship", ["source_certificate_id"])
    op.create_index("ix_certificate_relationship_target_certificate_id", "certificate_relationship", ["target_certificate_id"])
    op.create_index("ix_certificate_relationship_created_by_user_id", "certificate_relationship", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_certificate_relationship_created_by_user_id", table_name="certificate_relationship")
    op.drop_index("ix_certificate_relationship_target_certificate_id", table_name="certificate_relationship")
    op.drop_index("ix_certificate_relationship_source_certificate_id", table_name="certificate_relationship")
    op.drop_table("certificate_relationship")
    op.drop_constraint(
        op.f("ck_certificate_version_certificate_version_lifecycle_state_known"),
        "certificate_version",
        type_="check",
    )
    op.drop_column("certificate_version", "lifecycle_state")
    op.drop_index("ix_certificate_production_line_id", table_name="certificate")
    op.drop_column("certificate", "production_line_id")

    op.drop_index("ix_case_scope_revision_unkeyed_entry_block_id", table_name="case_scope_revision_unkeyed_entry")
    op.drop_table("case_scope_revision_unkeyed_entry")
    op.drop_index("ix_case_scope_revision_selection_taxonomy_node_id", table_name="case_scope_revision_selection")
    op.drop_index("ix_case_scope_revision_selection_block_id", table_name="case_scope_revision_selection")
    op.drop_table("case_scope_revision_selection")
    op.drop_index("ix_case_scope_revision_block_case_scope_revision_id", table_name="case_scope_revision_block")
    op.drop_table("case_scope_revision_block")
    op.drop_index("uq_case_scope_revision_one_current_established", table_name="case_scope_revision")
    op.drop_index("uq_case_scope_revision_one_draft", table_name="case_scope_revision")
    op.drop_index("ix_case_scope_revision_established_by_user_id", table_name="case_scope_revision")
    op.drop_index("ix_case_scope_revision_created_by_user_id", table_name="case_scope_revision")
    op.drop_index("ix_case_scope_revision_taxonomy_version_id", table_name="case_scope_revision")
    op.drop_table("case_scope_revision")
    op.drop_table("case_scope_phase")

    op.drop_index("ix_case_production_line_id", table_name="case")
    op.drop_column("case", "production_line_id")
    op.drop_index("ix_production_line_transformation_member_line", table_name="production_line_transformation_member")
    op.drop_table("production_line_transformation_member")
    op.drop_index("ix_production_line_transformation_effective_on", table_name="production_line_transformation")
    op.drop_index("ix_production_line_transformation_created_by_user_id", table_name="production_line_transformation")
    op.drop_index("ix_production_line_transformation_site_id", table_name="production_line_transformation")
    op.drop_table("production_line_transformation")
    op.drop_index("ix_production_line_site_code", table_name="production_line")
    op.drop_table("production_line")
