"""Fail closed when GMP evidence intake shares an ORM Session with pending writes.

The intake service must not flush unrelated pending changes before its own
authorization checks or along with an evidence event.
"""
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.models import Base, AppUser, Company, GmpCoverageReviewEvent
from backend.app.services.gmp_coverage_review_intake import (
    UnresolvedReviewInput, append_unresolved_review_event,
)


@pytest.mark.parametrize("pending_kind", ("new", "dirty", "deleted"))
def test_intake_refuses_pending_unrelated_orm_mutations(pending_kind):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            actor = AppUser(username=f"synthetic-{pending_kind}", is_active=True)
            company = Company(legal_name="Untouched company")
            session.add_all((actor, company))
            session.commit()
            actor_id, company_id = actor.id, company.id

        with Session(engine) as session:
            if pending_kind == "new":
                session.add(Company(legal_name="Pending insertion"))
                assert session.new
            elif pending_kind == "dirty":
                loaded = session.get(Company, company_id)
                loaded.legal_name = "Pending overwrite"
                assert session.dirty
            else:
                loaded = session.get(Company, company_id)
                session.delete(loaded)
                assert session.deleted

            with pytest.raises(ValueError, match="clean Session"):
                append_unresolved_review_event(
                    session,
                    authenticated_user_id=actor_id,
                    evidence=UnresolvedReviewInput(
                        certificate_version_id=str(uuid4()),
                        site_id=str(uuid4()),
                        case_id=None,
                        source_snapshot_sha256="a" * 64,
                        source_document_sha256="b" * 64,
                        source_page_reference="Synthetic p1",
                        rationale="Unreviewed source",
                    ),
                )
            # The rejected call neither flushes nor commits caller state.
            assert session.new or session.dirty or session.deleted
            session.rollback()

        with Session(engine) as session:
            assert session.get(Company, company_id).legal_name == "Untouched company"
            assert session.scalars(select(GmpCoverageReviewEvent)).all() == []
    finally:
        engine.dispose()
