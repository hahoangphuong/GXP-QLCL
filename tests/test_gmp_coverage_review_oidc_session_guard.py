"""OIDC boundary must reject dirty ORM state before its first SELECT/autoflush."""
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from backend.app.auth import AuthenticatedUser
from backend.app.db.models import Base, AppUser, Company, GmpCoverageReviewEvent
from backend.app.services.gmp_coverage_review_auth_boundary import (
    append_unresolved_from_authenticated_context,
)
from backend.app.services.gmp_coverage_review_intake import UnresolvedReviewInput


@pytest.mark.parametrize("kind", ["new", "dirty", "deleted"])
def test_oidc_boundary_does_not_autoflush_unrelated_orm_state(kind):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as setup:
            user = AppUser(username="synthetic-oidc", external_subject="subject-oidc",
                           external_email="oidc@example.test", is_active=True)
            company = Company(legal_name="Unchanged")
            setup.add_all([user, company])
            setup.commit()
            company_id = company.id

        with Session(engine) as session:
            if kind == "new":
                session.add(Company(legal_name="Forbidden pending insert"))
            elif kind == "dirty":
                row = session.get(Company, company_id)
                row.legal_name = "Forbidden pending change"
            else:
                row = session.get(Company, company_id)
                session.delete(row)

            statements = []
            def capture(_connection, _cursor, statement, _params, _context, _many):
                statements.append(statement)
            event.listen(engine, "before_cursor_execute", capture)
            try:
                with pytest.raises(ValueError, match="clean Session"):
                    append_unresolved_from_authenticated_context(
                        session,
                        authenticated=AuthenticatedUser(
                            username="synthetic-oidc", auth_mode="google_oidc",
                            subject="subject-oidc", email="oidc@example.test",
                        ),
                        evidence=UnresolvedReviewInput(
                            certificate_version_id="unused",
                            site_id="unused", case_id=None,
                            source_snapshot_sha256="a" * 64,
                            source_document_sha256="b" * 64,
                            source_page_reference="synthetic p1",
                            rationale="not authorized",
                        ),
                    )
                assert statements == [], "OIDC boundary queried/flushed before rejecting dirty Session"
            finally:
                event.remove(engine, "before_cursor_execute", capture)
                session.rollback()

        with Session(engine) as verify:
            assert verify.get(Company, company_id).legal_name == "Unchanged"
            assert verify.scalars(select(GmpCoverageReviewEvent)).all() == []
    finally:
        engine.dispose()
