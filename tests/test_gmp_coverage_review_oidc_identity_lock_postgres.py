"""OIDC subject/email binding is transaction-stable before GMP intake starts.

Uses only the disposable PostgreSQL gxp_qlcl_test. The mocked downstream intake
runs a second connection while the OIDC lookup transaction is still open,
demonstrating the wrapper's own row lock (not the lower service's lock).
"""
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.auth import AuthenticatedUser
from backend.app.db.models import AppUser
from backend.app.services import gmp_coverage_review_auth_boundary as boundary
from backend.app.services.gmp_coverage_review_intake import UnresolvedReviewInput

URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not URL.startswith("postgresql") or make_url(URL).database != "gxp_qlcl_test",
    reason="Only disposable PostgreSQL gxp_qlcl_test may run this test",
)


def test_oidc_subject_and_email_updates_wait_at_boundary(monkeypatch):
    engine = create_engine(URL, future=True)
    user_id = None
    subject = f"synthetic-subject-{uuid4().hex}"
    email = f"{uuid4().hex}@example.test"
    try:
        with Session(engine) as setup:
            user = AppUser(username=subject, external_subject=subject,
                           external_email=email, is_active=True)
            setup.add(user)
            setup.commit()
            user_id = user.id

        with engine.connect() as writer, engine.connect() as concurrent:
            transaction = writer.begin()
            try:
                def check_locked(_session, *, evidence, authenticated_user_id):
                    assert authenticated_user_id == user_id
                    for replacement in (
                        {"external_subject": f"changed-{subject}"},
                        {"external_email": "changed@example.test"},
                        {"is_active": False},
                    ):
                        tx = concurrent.begin()
                        try:
                            concurrent.execute(text("SET LOCAL lock_timeout = '250ms'"))
                            with pytest.raises(DBAPIError, match="lock timeout"):
                                concurrent.execute(
                                    update(AppUser).where(AppUser.id == user_id)
                                    .values(**replacement)
                                )
                        finally:
                            tx.rollback()
                    return "synthetic-event"

                monkeypatch.setattr(boundary, "append_unresolved_review_event", check_locked)
                with Session(bind=writer) as session:
                    result = boundary.append_unresolved_from_authenticated_context(
                        session,
                        authenticated=AuthenticatedUser(
                            username=subject, auth_mode="google_oidc",
                            subject=subject, email=email,
                        ),
                        evidence=UnresolvedReviewInput(
                            certificate_version_id="not-used",
                            site_id="not-used", case_id=None,
                            source_snapshot_sha256="a" * 64,
                            source_document_sha256="b" * 64,
                            source_page_reference="synthetic", rationale="synthetic",
                        ),
                    )
                    assert result == "synthetic-event"
            finally:
                transaction.rollback()
    finally:
        if user_id is not None:
            with engine.begin() as cleanup:
                cleanup.execute(delete(AppUser).where(AppUser.id == user_id))
        engine.dispose()
