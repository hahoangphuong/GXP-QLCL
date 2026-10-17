"""Add empty, source-only DDK GxP provenance tables.

Revision ID: 20261012_0023
Revises: 20261008_0022
Create Date: 2026-10-12

No source backfill, Certificate link, identity mapping, data rewrites,
or application/API behavior changes. Reviewed source import is a separate gate.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261012_0023"
down_revision = "20261008_0022"
branch_labels = None
depends_on = None


GROUP = "business_eligibility_gxp_source_group"
REFERENCE = "business_eligibility_gxp_reference_evidence"


def _timestamps():
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
    )


def upgrade() -> None:
    op.create_table(
        GROUP,
        sa.Column("source_workbook_sha256", sa.String(64), nullable=False),
        sa.Column("source_sheet_name", sa.String(32), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("legacy_dkkd_id", sa.Integer(), nullable=True),
        sa.Column("source_group", sa.String(3), nullable=False),
        sa.Column("id_cc_excel_column", sa.Integer(), nullable=False),
        sa.Column("certificate_scope_excel_column", sa.Integer(), nullable=False),
        sa.Column("applicable_standard_excel_column", sa.Integer(), nullable=False),
        sa.Column("business_activity_excel_column", sa.Integer(), nullable=False),
        sa.Column("id_cc_raw", sa.Text(), nullable=False),
        sa.Column("certificate_scope_raw", sa.Text(), nullable=False),
        sa.Column("applicable_standard_raw", sa.Text(), nullable=False),
        sa.Column("business_activity_raw", sa.Text(), nullable=False),
        sa.Column("source_values_sha256", sa.String(64), nullable=False),
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_eligibility_gxp_source_group")),
        sa.UniqueConstraint(
            "source_workbook_sha256", "source_sheet_name", "source_row_number",
            "source_group", name="uq_begxp_group_workbook_row_role",
        ),
        sa.CheckConstraint(
            "source_sheet_name = 'db.dkkd'",
            name=op.f("ck_business_eligibility_gxp_source_group_begxp_group_source_sheet"),
        ),
        sa.CheckConstraint(
            "source_group IN ('GMP', 'GLP', 'GSP', 'GDP')",
            name=op.f("ck_business_eligibility_gxp_source_group_begxp_group_role"),
        ),
        sa.CheckConstraint(
            "source_row_number > 0 AND id_cc_excel_column > 0",
            name=op.f("ck_business_eligibility_gxp_source_group_begxp_group_positive_source_position"),
        ),
        sa.CheckConstraint(
            "certificate_scope_excel_column = id_cc_excel_column + 1 "
            "AND applicable_standard_excel_column = id_cc_excel_column + 2 "
            "AND business_activity_excel_column = id_cc_excel_column + 3",
            name=op.f("ck_business_eligibility_gxp_source_group_begxp_group_contiguous_source_columns"),
        ),
        sa.CheckConstraint(
            "length(source_workbook_sha256) = 64 AND length(source_values_sha256) = 64",
            name=op.f("ck_business_eligibility_gxp_source_group_begxp_group_sha256_length"),
        ),
    )
    op.create_index("ix_begxp_group_source_workbook", GROUP, ["source_workbook_sha256"])

    op.create_table(
        REFERENCE,
        sa.Column("source_group_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("token_index", sa.Integer(), nullable=False),
        sa.Column("raw_token", sa.Text(), nullable=False),
        sa.Column("parsed_legacy_certificate_id", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_eligibility_gxp_reference_evidence")),
        sa.ForeignKeyConstraint(
            ["source_group_id"], [f"{GROUP}.id"],
            name="fk_begxp_reference_group",
        ),
        sa.UniqueConstraint(
            "source_group_id", "token_index", name="uq_begxp_reference_group_token",
        ),
        sa.CheckConstraint(
            "token_index > 0",
            name=op.f("ck_business_eligibility_gxp_reference_evidence_begxp_reference_positive_index"),
        ),
        sa.CheckConstraint(
            "parsed_legacy_certificate_id IS NULL OR parsed_legacy_certificate_id > 0",
            name=op.f("ck_business_eligibility_gxp_reference_evidence_begxp_reference_positive_legacy_id"),
        ),
    )
    op.create_index(
        "ix_business_eligibility_gxp_reference_evidence_source_group_id",
        REFERENCE, ["source_group_id"],
    )


def downgrade() -> None:
    # Never silently destroy source evidence during rollback. Fresh empty
    # migrations remain fully reversible in CI/disposable databases.
    connection = op.get_bind()
    for table in (REFERENCE, GROUP):
        count = connection.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        if count:
            raise RuntimeError(
                f"Cannot downgrade DDK source provenance: {table} contains {count} evidence rows"
            )

    op.drop_index(
        "ix_business_eligibility_gxp_reference_evidence_source_group_id",
        table_name=REFERENCE,
    )
    op.drop_table(REFERENCE)
    op.drop_index("ix_begxp_group_source_workbook", table_name=GROUP)
    op.drop_table(GROUP)
