"""Add canonical ChangeRequest artifact ownership links.

Revision ID: 20261005_0020
Revises: 20261005_0019
Create Date: 2026-10-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261005_0020"
down_revision = "20261005_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "change_request_affected_artifact",
        sa.Column("change_request_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("certificate_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("business_eligibility_certificate_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(certificate_id IS NOT NULL AND business_eligibility_certificate_id IS NULL) OR "
            "(certificate_id IS NULL AND business_eligibility_certificate_id IS NOT NULL)",
            name=op.f("ck_change_request_affected_artifact_one_target"),
        ),
        sa.ForeignKeyConstraint(
            ["change_request_id"],
            ["change_request.id"],
            name="fk_cr_affected_change",
        ),
        sa.ForeignKeyConstraint(
            ["certificate_id"],
            ["certificate.id"],
            name="fk_cr_affected_cert",
        ),
        sa.ForeignKeyConstraint(
            ["business_eligibility_certificate_id"],
            ["business_eligibility_certificate.id"],
            name="fk_cr_affected_dkkd",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_request_affected_artifact")),
        sa.UniqueConstraint(
            "change_request_id",
            "certificate_id",
            name="uq_cr_affected_change_cert",
        ),
        sa.UniqueConstraint(
            "change_request_id",
            "business_eligibility_certificate_id",
            name="uq_cr_affected_change_dkkd",
        ),
    )
    op.create_index(
        "ix_cr_affected_change",
        "change_request_affected_artifact",
        ["change_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_cr_affected_cert",
        "change_request_affected_artifact",
        ["certificate_id"],
        unique=False,
    )
    op.create_index(
        "ix_cr_affected_dkkd",
        "change_request_affected_artifact",
        ["business_eligibility_certificate_id"],
        unique=False,
    )

    op.create_table(
        "change_request_issued_artifact",
        sa.Column("change_request_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("source_affected_artifact_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("certificate_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("business_eligibility_certificate_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(certificate_id IS NOT NULL AND business_eligibility_certificate_id IS NULL) OR "
            "(certificate_id IS NULL AND business_eligibility_certificate_id IS NOT NULL)",
            name=op.f("ck_change_request_issued_artifact_one_target"),
        ),
        sa.ForeignKeyConstraint(
            ["change_request_id"],
            ["change_request.id"],
            name="fk_cr_issued_change",
        ),
        sa.ForeignKeyConstraint(
            ["source_affected_artifact_id"],
            ["change_request_affected_artifact.id"],
            name="fk_cr_issued_source",
        ),
        sa.ForeignKeyConstraint(
            ["certificate_id"],
            ["certificate.id"],
            name="fk_cr_issued_cert",
        ),
        sa.ForeignKeyConstraint(
            ["business_eligibility_certificate_id"],
            ["business_eligibility_certificate.id"],
            name="fk_cr_issued_dkkd",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_request_issued_artifact")),
        sa.UniqueConstraint(
            "change_request_id",
            "certificate_id",
            name="uq_cr_issued_change_cert",
        ),
        sa.UniqueConstraint(
            "change_request_id",
            "business_eligibility_certificate_id",
            name="uq_cr_issued_change_dkkd",
        ),
    )
    op.create_index(
        "ix_cr_issued_change",
        "change_request_issued_artifact",
        ["change_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_cr_issued_source",
        "change_request_issued_artifact",
        ["source_affected_artifact_id"],
        unique=False,
    )
    op.create_index(
        "ix_cr_issued_cert",
        "change_request_issued_artifact",
        ["certificate_id"],
        unique=False,
    )
    op.create_index(
        "ix_cr_issued_dkkd",
        "change_request_issued_artifact",
        ["business_eligibility_certificate_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cr_issued_dkkd",
        table_name="change_request_issued_artifact",
    )
    op.drop_index(
        "ix_cr_issued_cert",
        table_name="change_request_issued_artifact",
    )
    op.drop_index(
        "ix_cr_issued_source",
        table_name="change_request_issued_artifact",
    )
    op.drop_index(
        "ix_cr_issued_change",
        table_name="change_request_issued_artifact",
    )
    op.drop_table("change_request_issued_artifact")

    op.drop_index(
        "ix_cr_affected_dkkd",
        table_name="change_request_affected_artifact",
    )
    op.drop_index(
        "ix_cr_affected_cert",
        table_name="change_request_affected_artifact",
    )
    op.drop_index(
        "ix_cr_affected_change",
        table_name="change_request_affected_artifact",
    )
    op.drop_table("change_request_affected_artifact")
