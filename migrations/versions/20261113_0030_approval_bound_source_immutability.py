"""Protect canonical PCT/CT document-to-submission identity after association.

Revision ID: 20261113_0030
Revises: 20261113_0029

This migration does not backfill, reinterpret, issue or modify documents. It
blocks future mutations that would invalidate an already-persisted association.
PostgreSQL source-owner constraint; SQLite synthetic fixtures remain unchanged.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261113_0030"
down_revision = "20261113_0029"
branch_labels = None
depends_on = None

LINK = "inspection_approval_document_link"

DOCUMENT_GUARD = """
CREATE FUNCTION approval_bound_document_source_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (
        OLD.case_id IS DISTINCT FROM NEW.case_id
        OR OLD.family_code IS DISTINCT FROM NEW.family_code
        OR OLD.capa_cycle_id IS DISTINCT FROM NEW.capa_cycle_id
        OR OLD.certificate_id IS DISTINCT FROM NEW.certificate_id
        OR OLD.business_eligibility_certificate_id IS DISTINCT FROM NEW.business_eligibility_certificate_id
        OR OLD.change_request_id IS DISTINCT FROM NEW.change_request_id
    ) AND EXISTS (
        SELECT 1 FROM inspection_approval_document_link
        WHERE document_id = OLD.id
    ) THEN
        RAISE EXCEPTION 'APPROVAL_BOUND_DOCUMENT_SOURCE_IMMUTABLE'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$
"""

SUBMISSION_GUARD = """
CREATE FUNCTION approval_bound_submission_identity_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (
        OLD.case_id IS DISTINCT FROM NEW.case_id
        OR OLD.stage IS DISTINCT FROM NEW.stage
        OR OLD.round_no IS DISTINCT FROM NEW.round_no
    ) AND EXISTS (
        SELECT 1 FROM inspection_approval_document_link
        WHERE approval_submission_id = OLD.id
    ) THEN
        RAISE EXCEPTION 'APPROVAL_BOUND_SUBMISSION_IDENTITY_IMMUTABLE'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$
"""

LINK_GUARD = """
CREATE FUNCTION approval_document_link_append_only_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'APPROVAL_DOCUMENT_LINK_APPEND_ONLY'
        USING ERRCODE = '23514';
END;
$$
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # Never silently grandfather inconsistent binding evidence into the new
    # guarded scheme. An operator must reconcile it explicitly; do not guess
    # source Case, stage or parent based on a filename/date/round.
    existing_invalid = bind.execute(sa.text("""
        SELECT l.id
        FROM inspection_approval_document_link AS l
        LEFT JOIN inspection_approval_submission AS s
            ON s.id = l.approval_submission_id
        LEFT JOIN document AS d ON d.id = l.document_id
        WHERE s.id IS NULL OR d.id IS NULL
            OR s.stage NOT IN ('PCT', 'CT')
            OR d.case_id IS DISTINCT FROM s.case_id
            OR d.family_code IS DISTINCT FROM
                CASE WHEN s.stage = 'PCT' THEN 'INSPECTION_PT_PCT'
                     WHEN s.stage = 'CT' THEN 'INSPECTION_PT_CT'
                     ELSE NULL END
            OR d.capa_cycle_id IS NOT NULL
            OR d.certificate_id IS NOT NULL
            OR d.business_eligibility_certificate_id IS NOT NULL
            OR d.change_request_id IS NOT NULL
        LIMIT 1
    """)).first()
    if existing_invalid is not None:
        raise RuntimeError("APPROVAL_BOUND_SOURCE_INVALID_PREEXISTING_LINKS")
    for command in (DOCUMENT_GUARD, SUBMISSION_GUARD, LINK_GUARD):
        op.execute(sa.text(command))
    op.execute(sa.text("""
        CREATE TRIGGER trg_approval_bound_document_source
        BEFORE UPDATE OF case_id, family_code, capa_cycle_id, certificate_id,
            business_eligibility_certificate_id, change_request_id
        ON document
        FOR EACH ROW EXECUTE FUNCTION approval_bound_document_source_guard()
    """))
    op.execute(sa.text("""
        CREATE TRIGGER trg_approval_bound_submission_identity
        BEFORE UPDATE OF case_id, stage, round_no
        ON inspection_approval_submission
        FOR EACH ROW EXECUTE FUNCTION approval_bound_submission_identity_guard()
    """))
    op.execute(sa.text(f"""
        CREATE TRIGGER trg_approval_document_link_append_only
        BEFORE UPDATE OR DELETE ON {LINK}
        FOR EACH ROW EXECUTE FUNCTION approval_document_link_append_only_guard()
    """))


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(
        f"DROP TRIGGER trg_approval_document_link_append_only ON {LINK}"
    ))
    op.execute(sa.text(
        "DROP TRIGGER trg_approval_bound_submission_identity ON inspection_approval_submission"
    ))
    op.execute(sa.text("DROP TRIGGER trg_approval_bound_document_source ON document"))
    op.execute(sa.text("DROP FUNCTION approval_document_link_append_only_guard()"))
    op.execute(sa.text("DROP FUNCTION approval_bound_submission_identity_guard()"))
    op.execute(sa.text("DROP FUNCTION approval_bound_document_source_guard()"))
