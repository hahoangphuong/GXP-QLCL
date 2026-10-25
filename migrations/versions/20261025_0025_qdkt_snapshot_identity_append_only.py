"""Pin QĐKT draft identity and prevent mutation of persisted roster evidence.

Revision ID: 20261025_0025
Revises: 20261025_0024

Reject upgrade if 0024 has data without a durable draft_id. This migration
never invents a draft identifier or rewrites historical rows.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_0025"
down_revision = "20261025_0024"
branch_labels = None
depends_on = None

SNAPSHOT = "qdkt_draft_roster_snapshot"
MEMBER = "qdkt_draft_roster_member"
TRIGGER_FUNCTION = "qdkt_snapshot_reject_mutation"


def upgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM qdkt_draft_roster_snapshot LIMIT 1")).first():
        raise RuntimeError("QDKT_0025_REQUIRES_EMPTY_UNLINKED_SNAPSHOTS")
    op.add_column(SNAPSHOT, sa.Column("draft_id", sa.String(128), nullable=False))
    op.create_unique_constraint("uq_qdkt_snapshot_case_draft_identity", SNAPSHOT, ["case_id", "draft_id"])
    op.create_check_constraint("qdkt_draft_identity_not_blank", SNAPSHOT, "length(trim(draft_id)) > 0")
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
            CREATE FUNCTION qdkt_snapshot_reject_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'QDKT_SNAPSHOT_APPEND_ONLY';
            END;
            $$
        """))
        for table in (SNAPSHOT, MEMBER):
            op.execute(sa.text(f"""
                CREATE TRIGGER trg_{table}_append_only
                BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION qdkt_snapshot_reject_mutation()
            """))


def downgrade():
    bind = op.get_bind()
    for table in (MEMBER, SNAPSHOT):
        if bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError("QDKT_0025_DOWNGRADE_REQUIRES_EMPTY_TABLES")
    if bind.dialect.name == "postgresql":
        for table in (MEMBER, SNAPSHOT):
            op.execute(sa.text(f"DROP TRIGGER trg_{table}_append_only ON {table}"))
        op.execute(sa.text("DROP FUNCTION qdkt_snapshot_reject_mutation()"))
    op.drop_constraint("ck_qdkt_draft_roster_snapshot_qdkt_draft_identity_not_blank", SNAPSHOT, type_="check")
    op.drop_constraint("uq_qdkt_snapshot_case_draft_identity", SNAPSHOT, type_="unique")
    op.drop_column(SNAPSHOT, "draft_id")
