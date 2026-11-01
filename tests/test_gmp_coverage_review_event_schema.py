"""Issue #6 additive reviewed-coverage event schema, without runtime grants."""
from pathlib import Path

from backend.app.db.models import Base, GmpCoverageReviewEvent


def test_review_event_orm_requires_provenance_and_version_scoped_case_identity():
    table = GmpCoverageReviewEvent.__table__
    assert table is Base.metadata.tables["gmp_coverage_review_event"]
    for name in ("certificate_version_id", "site_id", "reviewer_user_id", "recorded_by_user_id"):
        assert not table.c[name].nullable
        assert table.c[name].foreign_keys
    assert table.c.case_id.nullable
    assert table.c.case_id.foreign_keys
    for name in (
        "source_snapshot_sha256", "source_document_sha256", "source_page_reference",
        "rationale", "decision_kind", "decision_status", "reviewed_at",
    ):
        assert not table.c[name].nullable


def test_schema_is_additive_and_database_append_only_for_postgres():
    migration = Path("migrations/versions/20261101_0027_gmp_coverage_review_events.py").read_text()
    assert 'down_revision = "20261025_0026"' in migration
    assert "BEFORE UPDATE OR DELETE" in migration
    assert "GMP_COVERAGE_REVIEW_APPEND_ONLY" in migration
    assert "GMP_COVERAGE_0027_DOWNGRADE_REQUIRES_EMPTY_TABLE" in migration
    assert "op.create_table(" in migration
    assert "UPDATE certificate" not in migration
    assert "DELETE FROM case" not in migration
