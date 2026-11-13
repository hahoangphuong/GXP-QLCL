"""Add explicit approval submission to Case document links.

Revision ID: 20261113_0029
Revises: 20261108_0028
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261113_0029"
down_revision = "20261108_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inspection_approval_document_link",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("approval_submission_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("document_id", sa.UUID(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["approval_submission_id"], ["inspection_approval_submission.id"],
            name="fk_approval_doc_submission",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["document.id"], name="fk_approval_doc_document",
        ),
        sa.UniqueConstraint("document_id", name="uq_approval_doc_document"),
    )
    op.create_index(
        "ix_inspection_approval_document_link_approval_submission_id",
        "inspection_approval_document_link", ["approval_submission_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_inspection_approval_document_link_approval_submission_id", table_name="inspection_approval_document_link")
    op.drop_table("inspection_approval_document_link")
