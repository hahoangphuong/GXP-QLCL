"""Add decision-owned, append-only issued roster evidence tables.

Revision ID: 20261025_0026
Revises: 20261025_0025

Schema only. Never backfill decisions, confirm approvals, or overwrite teams.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_0026"
down_revision = "20261025_0025"
branch_labels = None
depends_on = None


def _uuid():
    return sa.UUID(as_uuid=False)


def _times():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def upgrade():
    op.create_table(
        "qdkt_issued_roster",
        sa.Column("id", _uuid(), primary_key=True),
        *_times(),
        sa.Column("inspection_decision_id", _uuid(), sa.ForeignKey("inspection_decision.id"),
                  nullable=False, unique=True),
        sa.Column("roster_source", sa.String(20), nullable=False),
        sa.Column("source_draft_snapshot_id", _uuid(), sa.ForeignKey("qdkt_draft_roster_snapshot.id")),
        sa.Column("confirmed_by_user_id", _uuid(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("roster_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint("roster_source IN ('DRAFT_UNCHANGED', 'DRAFT_EDITED', 'USER_ENTERED')",
                           name="qdkt_issued_roster_source_known"),
        sa.CheckConstraint(
            "(roster_source = 'USER_ENTERED' AND source_draft_snapshot_id IS NULL) "
            "OR (roster_source IN ('DRAFT_UNCHANGED', 'DRAFT_EDITED') AND source_draft_snapshot_id IS NOT NULL)",
            name="qdkt_issued_roster_draft_link_shape",
        ),
        sa.CheckConstraint("length(roster_sha256) = 64", name="qdkt_issued_roster_digest_length"),
    )
    op.create_table(
        "qdkt_issued_roster_member",
        sa.Column("id", _uuid(), primary_key=True),
        *_times(),
        sa.Column("issued_roster_id", _uuid(), sa.ForeignKey("qdkt_issued_roster.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source_member_id", sa.String(64)),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("role_code", sa.String(16), nullable=False),
        sa.Column("job_title", sa.String(255), nullable=False),
        sa.UniqueConstraint("issued_roster_id", "position", name="uq_qdkt_issued_member_position"),
        sa.CheckConstraint("position >= 1", name="qdkt_issued_member_position_positive"),
        sa.CheckConstraint("role_code IN ('LEADER', 'SECRETARY', 'MEMBER')", name="qdkt_issued_member_role_known"),
        sa.CheckConstraint("length(trim(display_name)) > 0", name="qdkt_issued_member_name_nonblank"),
        sa.CheckConstraint("length(trim(job_title)) > 0", name="qdkt_issued_member_title_nonblank"),
    )
    op.create_index("ix_qdkt_issued_roster_member_issued_roster_id",
                    "qdkt_issued_roster_member", ["issued_roster_id"])
    if op.get_bind().dialect.name == "postgresql":
        for table in ("qdkt_issued_roster", "qdkt_issued_roster_member"):
            op.execute(sa.text(f"""
                CREATE TRIGGER trg_{table}_append_only
                BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION qdkt_snapshot_reject_mutation()
            """))


def downgrade():
    connection = op.get_bind()
    for table in ("qdkt_issued_roster_member", "qdkt_issued_roster"):
        if connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError("QDKT_0026_DOWNGRADE_REQUIRES_EMPTY_TABLES")
    if connection.dialect.name == "postgresql":
        for table in ("qdkt_issued_roster_member", "qdkt_issued_roster"):
            op.execute(sa.text(f"DROP TRIGGER trg_{table}_append_only ON {table}"))
    op.drop_index("ix_qdkt_issued_roster_member_issued_roster_id", table_name="qdkt_issued_roster_member")
    op.drop_table("qdkt_issued_roster_member")
    op.drop_table("qdkt_issued_roster")
