"""workspace certificate and facility detail fields

Revision ID: 20260829_0006
Revises: 20260828_0005
Create Date: 2026-08-29 09:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260829_0006"
down_revision = "20260828_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site", sa.Column("facility_leader_name", sa.Text(), nullable=True))
    op.add_column("site", sa.Column("current_status_text", sa.Text(), nullable=True))

    op.add_column("business_eligibility_certificate", sa.Column("replaces_legacy_dkkd_id", sa.Integer(), nullable=True))
    op.add_column("business_eligibility_certificate", sa.Column("replaced_by_legacy_dkkd_id", sa.Integer(), nullable=True))

    op.add_column("business_eligibility_version", sa.Column("quality_assurance_person_name", sa.Text(), nullable=True))
    op.add_column("business_eligibility_version", sa.Column("professional_qualification_text", sa.Text(), nullable=True))
    op.add_column("business_eligibility_version", sa.Column("professional_license_number", sa.Text(), nullable=True))
    op.add_column("business_eligibility_version", sa.Column("professional_license_issued_on", sa.Date(), nullable=True))
    op.add_column("business_eligibility_version", sa.Column("professional_license_issuer", sa.Text(), nullable=True))
    op.add_column("business_eligibility_version", sa.Column("responsible_license_issued_on", sa.Date(), nullable=True))
    op.add_column("business_eligibility_version", sa.Column("responsible_license_issuer", sa.Text(), nullable=True))
    op.add_column("business_eligibility_version", sa.Column("decision_reference", sa.Text(), nullable=True))
    op.add_column("business_eligibility_version", sa.Column("issuance_sequence_text", sa.Text(), nullable=True))
    op.add_column("business_eligibility_version", sa.Column("issuance_history_text", sa.Text(), nullable=True))
    op.add_column("business_eligibility_version", sa.Column("business_activity_text", sa.Text(), nullable=True))
    op.add_column("business_eligibility_version", sa.Column("current_status_text", sa.Text(), nullable=True))
    op.add_column("business_eligibility_version", sa.Column("handled_by_name", sa.Text(), nullable=True))
    op.add_column("business_eligibility_version", sa.Column("application_dossier_reference", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("business_eligibility_version", "application_dossier_reference")
    op.drop_column("business_eligibility_version", "handled_by_name")
    op.drop_column("business_eligibility_version", "current_status_text")
    op.drop_column("business_eligibility_version", "business_activity_text")
    op.drop_column("business_eligibility_version", "issuance_history_text")
    op.drop_column("business_eligibility_version", "issuance_sequence_text")
    op.drop_column("business_eligibility_version", "decision_reference")
    op.drop_column("business_eligibility_version", "responsible_license_issuer")
    op.drop_column("business_eligibility_version", "responsible_license_issued_on")
    op.drop_column("business_eligibility_version", "professional_license_issuer")
    op.drop_column("business_eligibility_version", "professional_license_issued_on")
    op.drop_column("business_eligibility_version", "professional_license_number")
    op.drop_column("business_eligibility_version", "professional_qualification_text")
    op.drop_column("business_eligibility_version", "quality_assurance_person_name")

    op.drop_column("business_eligibility_certificate", "replaced_by_legacy_dkkd_id")
    op.drop_column("business_eligibility_certificate", "replaces_legacy_dkkd_id")

    op.drop_column("site", "current_status_text")
    op.drop_column("site", "facility_leader_name")
