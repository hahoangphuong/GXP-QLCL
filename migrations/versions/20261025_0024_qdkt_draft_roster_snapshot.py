"""Add empty, version-owned QĐKT draft roster snapshot tables.

Revision ID: 20261025_0024
Revises: 20261012_0023

No legacy backfill, document generation or approval event is performed.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_0024"
down_revision = "20261012_0023"
branch_labels = None
depends_on = None


def _uuid():
    return sa.UUID(as_uuid=False)


def _timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )


def upgrade():
    op.create_table(
        "qdkt_draft_roster_snapshot",
        sa.Column("id", _uuid(), primary_key=True),
        *_timestamps(),
        sa.Column("case_id", _uuid(), sa.ForeignKey("case.id"), nullable=False),
        sa.Column("document_version_id", _uuid(), sa.ForeignKey("document_version.id"),
                  nullable=False, unique=True),
        sa.Column("source_team_id", _uuid(), sa.ForeignKey("inspection_team.id"),
                  nullable=False),
        sa.Column("source_team_revision", sa.Integer(), nullable=False),
        sa.Column("roster_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint("source_team_revision >= 1", name="qdkt_draft_team_revision_positive"),
        sa.CheckConstraint("length(roster_sha256) = 64", name="qdkt_draft_roster_hash_length"),
    )
    op.create_index("ix_qdkt_draft_roster_snapshot_case_id",
                    "qdkt_draft_roster_snapshot", ["case_id"])
    op.create_table(
        "qdkt_draft_roster_member",
        sa.Column("id", _uuid(), primary_key=True),
        *_timestamps(),
        sa.Column("snapshot_id", _uuid(), sa.ForeignKey("qdkt_draft_roster_snapshot.id"),
                  nullable=False),
        sa.Column("source_team_member_id", _uuid(),
                  sa.ForeignKey("inspection_team_member.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("role_code", sa.String(16), nullable=False),
        sa.Column("job_title", sa.String(255), nullable=False),
        sa.UniqueConstraint("snapshot_id", "position", name="uq_qdkt_draft_member_snapshot_position"),
        sa.UniqueConstraint("snapshot_id", "source_team_member_id", name="uq_qdkt_draft_member_snapshot_source"),
        sa.CheckConstraint("position >= 1", name="qdkt_draft_member_position_positive"),
        sa.CheckConstraint("role_code IN ('LEADER', 'SECRETARY', 'MEMBER')",
                           name="qdkt_draft_member_role_known"),
        sa.CheckConstraint("length(trim(display_name)) > 0",
                           name="qdkt_draft_member_name_not_blank"),
        sa.CheckConstraint("length(trim(job_title)) > 0",
                           name="qdkt_draft_member_job_not_blank"),
    )
    op.create_index("ix_qdkt_draft_roster_member_snapshot_id",
                    "qdkt_draft_roster_member", ["snapshot_id"])


def downgrade():
    # Do not silently destroy recorded source history on a populated database.
    conn = op.get_bind()
    for table in ("qdkt_draft_roster_member", "qdkt_draft_roster_snapshot"):
        if conn.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError("QDKT_SNAPSHOT_DOWNGRADE_REQUIRES_EXPLICIT_DATA_REVIEW")
    op.drop_index("ix_qdkt_draft_roster_member_snapshot_id",
                  table_name="qdkt_draft_roster_member")
    op.drop_table("qdkt_draft_roster_member")
    op.drop_index("ix_qdkt_draft_roster_snapshot_case_id",
                  table_name="qdkt_draft_roster_snapshot")
    op.drop_table("qdkt_draft_roster_snapshot")
