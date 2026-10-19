"""PostgreSQL regression: one repaired historical FK cannot hide other invalid links.

Runs only in the GitHub Actions ephemeral PostgreSQL service. Fixture rows stay
inside one uncommitted outer transaction and are always rolled back. This is
NOT a rehearsal data-repair tool or a permission to relax legacy validation.
"""
from __future__ import annotations

from datetime import date
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    Case, Certificate, CertificateVersion, Company, Site,
)
from backend.app.services.catalog import CatalogReadService
from backend.app.services.workflow import CaseWorkflowService


def _ci_postgres_url() -> str | None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return None
    raw = os.environ.get("DATABASE_URL", "")
    try:
        uri = make_url(raw)
    except Exception:
        return None
    if (
        uri.get_backend_name() != "postgresql"
        or uri.database != "gxp_qlcl_test"
        or uri.username != "postgres"
        or uri.host not in {"127.0.0.1", "localhost", "::1"}
        or (uri.port or 5432) != 5432
        or bool(uri.query)
    ):
        return None
    return raw


@pytest.mark.skipif(
    _ci_postgres_url() is None,
    reason="historical 409 regression requires exact disposable GitHub CI PostgreSQL",
)
def test_repair_one_legacy_certificate_still_blocks_global_search_postgres():
    url = _ci_postgres_url()
    assert url is not None
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                assert conn.execute(text("SELECT current_database()")).scalar_one() == "gxp_qlcl_test"
                with Session(bind=conn, autoflush=False) as session:
                    wrong_co = Company(legal_name="Disposable unrelated company")
                    primary_co = Company(legal_name="Disposable correct issuer")
                    multisite_co = Company(legal_name="Disposable historic two-site issuer")
                    session.add_all([wrong_co, primary_co, multisite_co])
                    session.flush()

                    wrong_site = Site(company_id=wrong_co.id, site_name="Wrong original Case site")
                    correct_site = Site(company_id=primary_co.id, site_name="Correct certificate site")
                    grant_anchor = Site(company_id=multisite_co.id, site_name="Historic certificate anchor")
                    inspection_anchor = Site(company_id=multisite_co.id, site_name="Different historic Case anchor")
                    session.add_all([wrong_site, correct_site, grant_anchor, inspection_anchor])
                    session.flush()

                    unrelated_case = Case(
                        site_id=wrong_site.id, gxp_type="GMP", state=CaseState.CERTIFIED,
                    )
                    correct_case = Case(
                        site_id=correct_site.id, gxp_type="GMP", state=CaseState.CERTIFIED,
                    )
                    historic_case = Case(
                        site_id=inspection_anchor.id, gxp_type="GMP", state=CaseState.CERTIFIED,
                    )
                    session.add_all([unrelated_case, correct_case, historic_case])
                    session.flush()

                    first = Certificate(
                        case_id=unrelated_case.id, site_id=correct_site.id,
                        certificate_type="GMP", issuance_basis="inspection_case",
                        latest_flag=False,
                    )
                    old = Certificate(
                        case_id=historic_case.id, site_id=grant_anchor.id,
                        certificate_type="GMP", issuance_basis="inspection_case",
                        latest_flag=False,
                    )
                    replacement = Certificate(
                        case_id=historic_case.id, site_id=grant_anchor.id,
                        certificate_type="GMP", issuance_basis="inspection_case",
                        latest_flag=True,
                    )
                    administrative = Certificate(
                        case_id=None, site_id=correct_site.id,
                        certificate_type="GLP",
                        issuance_basis="administrative_no_inspection",
                        latest_flag=False,
                    )
                    session.add_all([first, old, replacement, administrative])
                    session.flush()
                    for cert, number, issued in (
                        (first, "DISPOSABLE-ORIGIN", date(2018, 3, 12)),
                        (old, "DISPOSABLE-OLD-SITE", date(2022, 4, 20)),
                        (replacement, "DISPOSABLE-NEW-SITE", date(2023, 5, 15)),
                        (administrative, "DISPOSABLE-ADMIN", date(2024, 1, 1)),
                    ):
                        session.add(CertificateVersion(
                            certificate_id=cert.id, version_no=1,
                            certificate_number=number,
                            issue_date=issued, is_latest_version=True,
                        ))
                    session.flush()

                    def expect_409() -> None:
                        for selection in ("GMP", "GLP", None):
                            with pytest.raises(HTTPException, match="invalid linked Case") as exc:
                                CatalogReadService().search_facilities(
                                    session, q=None, gxp_type=selection,
                                    province=None, case_states=None,
                                    change_request_states=None,
                                    certificate_state=None,
                                    certificate_expiring_within_days=None,
                                    offset=0, limit=1,
                                )
                            assert exc.value.status_code == 409

                    expect_409()
                    before = first.case_id

                    # Hypothetical GMP 376 Case rebind, fixture only.
                    first.case_id = correct_case.id
                    session.flush()
                    assert before == unrelated_case.id
                    assert first.case_id == correct_case.id

                    matching = set(session.scalars(
                        select(Certificate.id).where(
                            CaseWorkflowService._certificate_valid_linked_case_sql()
                        )
                    ))
                    assert first.id in matching
                    assert administrative.id in matching
                    assert old.id not in matching
                    assert replacement.id not in matching
                    assert CaseWorkflowService._validate_certificate_linked_case(
                        session, first,
                    ).id == correct_case.id
                    assert CaseWorkflowService._validate_certificate_linked_case(
                        session, administrative,
                    ) is None
                    for invalid in (old, replacement):
                        with pytest.raises(HTTPException, match="invalid linked Case") as exc:
                            CaseWorkflowService._validate_certificate_linked_case(
                                session, invalid,
                            )
                        assert exc.value.status_code == 409
                    expect_409()

            finally:
                tx.rollback()  # Outer transaction owns every fixture insert/update.
    finally:
        engine.dispose()
