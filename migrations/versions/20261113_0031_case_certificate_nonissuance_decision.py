"""Persist explicit Case no-certificate decision without changing Case lifecycle.

Revision ID: 20261113_0031
Revises: 20261113_0030
No data backfill; a missing Certificate never implies non-issuance.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261113_0031"
down_revision = "20261113_0030"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "case_certificate_nonissuance_decision",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("case_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("decided_on", sa.Date(), nullable=False),
        sa.Column("decision_reference", sa.String(255), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("recorded_by_user_id", sa.UUID(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["case.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["app_user.id"]),
        sa.UniqueConstraint("case_id", name="uq_case_certificate_nonissuance_decision_case_id"),
        sa.CheckConstraint("TRIM(decision_reference) <> ''", name="ck_case_certificate_nonissuance_decision_case_nonissuance_reference_nonblank"),
        sa.CheckConstraint("TRIM(explanation) <> ''", name="ck_case_certificate_nonissuance_decision_case_nonissuance_explanation_nonblank"),
    )
    op.create_index("ix_case_certificate_nonissuance_decision_case_id", "case_certificate_nonissuance_decision", ["case_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("""
            CREATE FUNCTION case_certificate_nonissuance_append_only() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'CASE_CERTIFICATE_NONISSUANCE_IMMUTABLE' USING ERRCODE = '23514';
            END; $$
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_case_certificate_nonissuance_append_only
            BEFORE UPDATE OR DELETE ON case_certificate_nonissuance_decision
            FOR EACH ROW EXECUTE FUNCTION case_certificate_nonissuance_append_only()
        """))


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("DROP TRIGGER trg_case_certificate_nonissuance_append_only ON case_certificate_nonissuance_decision"))
        op.execute(sa.text("DROP FUNCTION case_certificate_nonissuance_append_only()"))
    op.drop_index("ix_case_certificate_nonissuance_decision_case_id", table_name="case_certificate_nonissuance_decision")
    op.drop_table("case_certificate_nonissuance_decision")
