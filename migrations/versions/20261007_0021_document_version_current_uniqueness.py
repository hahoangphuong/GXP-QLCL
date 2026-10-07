"""Enforce one current document version per variant in PostgreSQL.

Revision ID: 20261007_0021
Revises: 20261005_0020
Create Date: 2026-10-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261007_0021"
down_revision = "20261005_0020"
branch_labels = None
depends_on = None


_INDEX_NAME = "ux_document_version_current_per_variant"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    duplicate_variant_id = bind.execute(
        sa.text(
            """
            SELECT document_variant_id::text
            FROM document_version
            WHERE is_current IS TRUE
            GROUP BY document_variant_id
            HAVING COUNT(*) > 1
            ORDER BY document_variant_id::text
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if duplicate_variant_id is not None:
        raise RuntimeError(
            "Cannot enforce single-current document-version lineage: "
            "multiple current versions already exist for "
            f"document_variant_id={duplicate_variant_id!r}. "
            "Resolve the persisted lineage explicitly before retrying migration."
        )

    op.create_index(
        _INDEX_NAME,
        "document_version",
        ["document_variant_id"],
        unique=True,
        postgresql_where=sa.text("is_current IS TRUE"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index(_INDEX_NAME, table_name="document_version")
