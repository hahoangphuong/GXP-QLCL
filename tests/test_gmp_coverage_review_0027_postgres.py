"""Disposable PostgreSQL proof for GMP 0027 evidence event immutability.

No rehearsal/production connection allowed; all rows rolled back.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, insert, select, update, delete
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from backend.app.db.models import (
    AppUser, Certificate, CertificateVersion, Company, GmpCoverageReviewEvent, Site,
)

URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not URL.startswith("postgresql") or make_url(URL).database != "gxp_qlcl_test",
    reason="Only disposable PostgreSQL gxp_qlcl_test may run this test",
)


def test_postgres_0027_rejects_update_delete_and_rolls_back_all_rows():
    engine = create_engine(URL, future=True)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                company, site, cert, version, reviewer, recorder, event = [
                    str(uuid4()) for _ in range(7)
                ]
                conn.execute(insert(Company.__table__).values(id=company, legal_name="Synthetic Company"))
                conn.execute(insert(Site.__table__).values(
                    id=site, company_id=company, site_name="Synthetic Site"
                ))
                conn.execute(insert(Certificate.__table__).values(
                    id=cert, site_id=site, certificate_type="GMP"
                ))
                conn.execute(insert(CertificateVersion.__table__).values(
                    id=version, certificate_id=cert, version_no=1
                ))
                conn.execute(insert(AppUser.__table__), [
                    {"id": reviewer, "username": f"synthetic-reviewer-{reviewer}"},
                    {"id": recorder, "username": f"synthetic-recorder-{recorder}"},
                ])
                conn.execute(insert(GmpCoverageReviewEvent.__table__).values(
                    id=event, certificate_version_id=version, site_id=site,
                    decision_kind="SITE_COVERAGE", decision_status="UNRESOLVED",
                    source_snapshot_sha256="a" * 64, source_document_sha256="b" * 64,
                    source_page_reference="synthetic p1", rationale="synthetic only",
                    reviewer_user_id=reviewer, recorded_by_user_id=recorder,
                    reviewed_at="2026-11-01T09:00:00+07:00",
                ))
                assert conn.execute(
                    select(GmpCoverageReviewEvent.id).where(GmpCoverageReviewEvent.id == event)
                ).scalar_one() == event
                for statement in (
                    update(GmpCoverageReviewEvent.__table__).where(
                        GmpCoverageReviewEvent.id == event
                    ).values(rationale="tampered"),
                    delete(GmpCoverageReviewEvent.__table__).where(
                        GmpCoverageReviewEvent.id == event
                    ),
                ):
                    nested = conn.begin_nested()
                    with pytest.raises(DBAPIError, match="GMP_COVERAGE_REVIEW_APPEND_ONLY"):
                        conn.execute(statement)
                    nested.rollback()
                assert conn.execute(
                    select(GmpCoverageReviewEvent.rationale).where(
                        GmpCoverageReviewEvent.id == event
                    )
                ).scalar_one() == "synthetic only"
            finally:
                tx.rollback()
    finally:
        engine.dispose()
