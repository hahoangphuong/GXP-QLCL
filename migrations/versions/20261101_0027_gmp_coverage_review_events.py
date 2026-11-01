"""Add source-bound, append-only GMP covered-Site review evidence.

Revision ID: 20261101_0027
Revises: 20261025_0026

Schema only. NO backfill, no accepted historical coverage, and no change to
Certificate/Case runtime link predicates.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261101_0027"
down_revision = "20261025_0026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gmp_coverage_review_event",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("certificate_version_id", sa.UUID(as_uuid=False),
                  sa.ForeignKey("certificate_version.id"), nullable=False),
        sa.Column("site_id", sa.UUID(as_uuid=False), sa.ForeignKey("site.id"), nullable=False),
        sa.Column("case_id", sa.UUID(as_uuid=False), sa.ForeignKey("case.id"), nullable=True),
        sa.Column("decision_kind", sa.String(16), nullable=False),
        sa.Column("decision_status", sa.String(16), nullable=False),
        sa.Column("source_snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("source_document_sha256", sa.String(64), nullable=False),
        sa.Column("source_page_reference", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("reviewer_user_id", sa.UUID(as_uuid=False),
                  sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("recorded_by_user_id", sa.UUID(as_uuid=False),
                  sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("decision_kind IN ('SITE_COVERAGE', 'CASE_LINK')",
                           name="gmp_coverage_review_kind"),
        sa.CheckConstraint("decision_status IN ('VERIFIED', 'REJECTED', 'UNRESOLVED')",
                           name="gmp_coverage_review_status"),
        sa.CheckConstraint(
            "(decision_kind = 'SITE_COVERAGE' AND case_id IS NULL) OR "
            "(decision_kind = 'CASE_LINK' AND case_id IS NOT NULL)",
            name="gmp_coverage_review_case_shape",
        ),
        sa.CheckConstraint("length(source_snapshot_sha256) = 64 AND "
                           "length(source_document_sha256) = 64",
                           name="gmp_coverage_review_digest_lengths"),
        sa.CheckConstraint("length(trim(source_page_reference)) > 0 AND "
                           "length(trim(rationale)) > 0",
                           name="gmp_coverage_review_source_nonblank"),
    )
    op.create_index("ix_gmp_coverage_review_version_site",
                    "gmp_coverage_review_event", ["certificate_version_id", "site_id"])
    op.create_index("ix_gmp_coverage_review_case",
                    "gmp_coverage_review_event", ["case_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("""
            CREATE FUNCTION gmp_coverage_review_reject_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'GMP_COVERAGE_REVIEW_APPEND_ONLY';
            END;
            $$
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_gmp_coverage_review_append_only
            BEFORE UPDATE OR DELETE ON gmp_coverage_review_event
            FOR EACH ROW EXECUTE FUNCTION gmp_coverage_review_reject_mutation()
        """))


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM gmp_coverage_review_event LIMIT 1")).first():
        raise RuntimeError("GMP_COVERAGE_0027_DOWNGRADE_REQUIRES_EMPTY_TABLE")
    if connection.dialect.name == "postgresql":
        op.execute(sa.text("DROP TRIGGER trg_gmp_coverage_review_append_only ON gmp_coverage_review_event"))
        op.execute(sa.text("DROP FUNCTION gmp_coverage_review_reject_mutation()"))
    op.drop_index("ix_gmp_coverage_review_case", table_name="gmp_coverage_review_event")
    op.drop_index("ix_gmp_coverage_review_version_site", table_name="gmp_coverage_review_event")
    op.drop_table("gmp_coverage_review_event")
