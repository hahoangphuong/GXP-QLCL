"""Malformed identifiers must fail with controlled ValueError before any DB access."""
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.app.services.gmp_coverage_review_intake import (
    UnresolvedReviewInput, _uuid, append_unresolved_review_event,
)


@pytest.mark.parametrize("bad", [None, 123, 3.14, [], {}, b"abc", "", "not-a-uuid", str(UUID(int=0))])
def test_uuid_validator_rejects_invalid_identity_types(bad):
    with pytest.raises(ValueError):
        _uuid(bad)


def test_uuid_validator_normalizes_valid_version_four():
    value = str(uuid4())
    assert _uuid(value.upper()) == value


@pytest.mark.parametrize("invalid_actor", [None, 123, [], "not-a-uuid"])
def test_invalid_actor_identity_executes_no_sql(invalid_actor):
    engine = create_engine("sqlite:///:memory:", future=True)
    statements = []
    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", capture)
    try:
        with Session(engine) as session:
            with pytest.raises(ValueError):
                append_unresolved_review_event(
                    session,
                    authenticated_user_id=invalid_actor,
                    evidence=UnresolvedReviewInput(
                        certificate_version_id=str(uuid4()),
                        site_id=str(uuid4()), case_id=None,
                        source_snapshot_sha256="a" * 64,
                        source_document_sha256="b" * 64,
                        source_page_reference="synthetic page",
                        rationale="synthetic unresolved evidence",
                    ),
                )
        assert statements == []
    finally:
        event.remove(engine, "before_cursor_execute", capture)
        engine.dispose()


@pytest.mark.parametrize("field,bad", [
    ("certificate_version_id", None),
    ("certificate_version_id", "not-a-uuid"),
    ("site_id", 42),
    ("site_id", "not-a-uuid"),
    ("case_id", "not-a-uuid"),
    ("source_snapshot_sha256", "x" * 64),
    ("source_document_sha256", None),
    ("source_page_reference", 123),
    ("source_page_reference", "  "),
    ("rationale", []),
    ("rationale", "  "),
])
def test_malformed_evidence_rejected_before_any_sql(field, bad):
    """Invalid input must not take locks or query RBAC/record identities."""
    from dataclasses import replace

    engine = create_engine("sqlite:///:memory:", future=True)
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        valid = UnresolvedReviewInput(
            certificate_version_id=str(uuid4()), site_id=str(uuid4()),
            case_id=None, source_snapshot_sha256="a" * 64,
            source_document_sha256="b" * 64,
            source_page_reference="synthetic page",
            rationale="synthetic unresolved review",
        )
        with Session(engine) as session:
            with pytest.raises(ValueError):
                append_unresolved_review_event(
                    session, authenticated_user_id=str(uuid4()),
                    evidence=replace(valid, **{field: bad}),
                )
        assert statements == []
    finally:
        event.remove(engine, "before_cursor_execute", capture)
        engine.dispose()


@pytest.mark.parametrize("invalid_evidence", [None, 42, {}, [], "not an input"])
def test_non_evidence_object_rejected_before_any_sql(invalid_evidence):
    engine = create_engine("sqlite:///:memory:", future=True)
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with Session(engine) as session:
            with pytest.raises(ValueError, match="evidence input"):
                append_unresolved_review_event(
                    session, authenticated_user_id=str(uuid4()),
                    evidence=invalid_evidence,
                )
        assert statements == []
    finally:
        event.remove(engine, "before_cursor_execute", capture)
        engine.dispose()
