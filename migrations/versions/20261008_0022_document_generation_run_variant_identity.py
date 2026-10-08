"""Persist generation-run variant lineage before output allocation.

Revision ID: 20261008_0022
Revises: 20261007_0021
Create Date: 2026-10-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261008_0022"
down_revision = "20261007_0021"
branch_labels = None
depends_on = None


_INDEX_NAME = "ix_document_generation_run_document_variant_id"
_FK_NAME = "fk_document_generation_run_document_variant_id_document_variant"


def upgrade() -> None:
    op.add_column(
        "document_generation_run",
        sa.Column("document_variant_id", sa.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        _FK_NAME,
        "document_generation_run",
        "document_variant",
        ["document_variant_id"],
        ["id"],
    )
    op.create_index(
        _INDEX_NAME,
        "document_generation_run",
        ["document_variant_id"],
        unique=False,
    )

    if op.get_bind().dialect.name != "postgresql":
        return

    # A persisted output version proves which variant the run actually used.
    op.execute(
        """
        UPDATE document_generation_run AS run
        SET document_variant_id = version.document_variant_id
        FROM document_version AS version
        JOIN document_variant AS variant
          ON variant.id = version.document_variant_id
        WHERE run.output_document_version_id = version.id
          AND variant.document_id = run.document_id
        """
    )
    # For pre-allocation historical runs, lineage is provable only when the
    # logical document has one variant. Ambiguous rows intentionally remain
    # NULL and fail closed on idempotent reuse.
    op.execute(
        """
        UPDATE document_generation_run AS run
        SET document_variant_id = candidate.id
        FROM document_variant AS candidate
        WHERE run.document_variant_id IS NULL
          AND run.output_document_version_id IS NULL
          AND candidate.document_id = run.document_id
          AND NOT EXISTS (
              SELECT 1
              FROM document_variant AS other
              WHERE other.document_id = candidate.document_id
                AND other.id <> candidate.id
          )
        """
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="document_generation_run")
    op.drop_constraint(_FK_NAME, "document_generation_run", type_="foreignkey")
    op.drop_column("document_generation_run", "document_variant_id")
