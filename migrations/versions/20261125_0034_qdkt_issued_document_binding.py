"""Append-only exact PDF DocumentVersion link per issued QĐKT source.

Schema only. No backfill, no claim of signature validation or legal issuance.
"""
from alembic import op
import sqlalchemy as sa
from backend.app.db.base import UUID_TEXT_SAFE

revision = "20261125_0034"
down_revision = "20261124_0033"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "qdkt_issued_document_binding",
        sa.Column("id", UUID_TEXT_SAFE, primary_key=True),
        sa.Column("inspection_decision_id", UUID_TEXT_SAFE,
                  sa.ForeignKey("inspection_decision.id"), nullable=False),
        sa.Column("document_version_id", UUID_TEXT_SAFE,
                  sa.ForeignKey("document_version.id"), nullable=False),
        sa.Column("recorded_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("linked_by_user_id", UUID_TEXT_SAFE,
                  sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("inspection_decision_id", name="uq_qdkt_issued_document_decision"),
        sa.UniqueConstraint("document_version_id", name="uq_qdkt_issued_document_version"),
        sa.CheckConstraint("length(recorded_checksum_sha256) = 64",
                           name="qdkt_issued_document_checksum_length"),
        sa.CheckConstraint("length(trim(reason)) > 0",
                           name="qdkt_issued_document_reason_nonblank"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("""
            CREATE TRIGGER trg_qdkt_issued_document_binding_append_only
            BEFORE UPDATE OR DELETE ON qdkt_issued_document_binding
            FOR EACH ROW EXECUTE FUNCTION qdkt_snapshot_reject_mutation()
        """))


def downgrade():
    conn = op.get_bind()
    if conn.execute(sa.text("SELECT 1 FROM qdkt_issued_document_binding LIMIT 1")).first():
        raise RuntimeError("QDKT_0034_DOWNGRADE_REQUIRES_EMPTY_BINDINGS")
    if conn.dialect.name == "postgresql":
        op.execute(sa.text(
            "DROP TRIGGER trg_qdkt_issued_document_binding_append_only "
            "ON qdkt_issued_document_binding"
        ))
    op.drop_table("qdkt_issued_document_binding")
