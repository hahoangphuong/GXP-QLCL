from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState, ChangeRequestState
from backend.app.db.models.phase1 import (
    Case, Certificate, CertificateVersion, ChangeRequest, Company, Site,
)
from backend.app.main import create_app
from backend.app.services.catalog import CatalogReadService


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Công ty thử nghiệm")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Cơ sở Thử")
        db.add(site)
        db.flush()
        # Two current GCN on the same Site; one with historical version and
        # a third replaced GCN. The page must not join across versions/scopes.
        cert_a = Certificate(site_id=site.id, certificate_type="GMP", latest_flag=True)
        cert_b = Certificate(site_id=site.id, certificate_type="GMP", latest_flag=True)
        old_cert = Certificate(site_id=site.id, certificate_type="GMP", latest_flag=False)
        db.add_all([cert_a, cert_b, old_cert])
        db.flush()
        today = date.today()
        db.add_all([
            CertificateVersion(certificate_id=cert_a.id, version_no=1, certificate_number="GCN-OLD",
                expiry_date=today + timedelta(days=2), is_latest_version=False),
            CertificateVersion(certificate_id=cert_a.id, version_no=2, certificate_number="GCN-A",
                expiry_date=today + timedelta(days=20), lifecycle_state="GRANTED", is_latest_version=True),
            CertificateVersion(certificate_id=cert_b.id, version_no=1, certificate_number="GCN-B",
                expiry_date=today + timedelta(days=80), is_latest_version=True),
            CertificateVersion(certificate_id=old_cert.id, version_no=1, certificate_number="GCN-REPLACED",
                expiry_date=today + timedelta(days=10), is_latest_version=True),
        ])
        db.add_all([
            ChangeRequest(site_id=site.id, state=ChangeRequestState.RECEIVED, scope_label="Đổi tên"),
            ChangeRequest(site_id=site.id, state=ChangeRequestState.UNDER_REVIEW, scope_label="Đổi địa chỉ"),
            ChangeRequest(site_id=site.id, state=ChangeRequestState.ACCEPTED, scope_label="Đã duyệt"),
        ])
        db.commit()
        yield db
    engine.dispose()


def cert_report(session, **changes):
    args = dict(gxp_type=None, q=None, expiry_days=90, export=False, offset=0, limit=100)
    return CatalogReadService().get_certificate_report(session, **(args | changes))


def change_report(session, **changes):
    args = dict(state=None, q=None, export=False, offset=0, limit=100)
    return CatalogReadService().get_change_request_report(session, **(args | changes))


def test_certificate_report_is_per_canonical_current_certificate_not_version(session):
    rows = cert_report(session)
    assert rows["total_count"] == 2
    assert {x["certificate_number"] for x in rows["items"]} == {"GCN-A", "GCN-B"}
    assert len({x["certificate_id"] for x in rows["items"]}) == 2
    assert all(x["site_id"] == rows["items"][0]["site_id"] for x in rows["items"])
    assert len(cert_report(session, expiry_days=30)["items"]) == 1
    assert len(cert_report(session, expiry_days=60)["items"]) == 1
    assert len(cert_report(session, expiry_days=90)["items"]) == 2
    assert cert_report(session, q="GCN-OLD")["total_count"] == 0
    assert cert_report(session, q="GCN-REPLACED")["total_count"] == 0
    assert cert_report(session, q="Công ty", number="GCN-A")["total_count"] == 1
    assert cert_report(session, q="Công ty", number="GCN-OLD")["total_count"] == 0


def test_certificate_report_filters_gsp_gdp_as_canonical_read_only_types(session):
    site_id = cert_report(session)["items"][0]["site_id"]
    gsp = Certificate(site_id=site_id, certificate_type="GSP", latest_flag=True)
    gdp = Certificate(site_id=site_id, certificate_type="GDP", latest_flag=True)
    superseded_gsp = Certificate(site_id=site_id, certificate_type="GSP", latest_flag=False)
    session.add_all([gsp, gdp, superseded_gsp])
    session.flush()
    session.add_all([
        CertificateVersion(certificate_id=gsp.id, version_no=1,
            certificate_number="GSP-CURRENT", is_latest_version=True),
        CertificateVersion(certificate_id=gdp.id, version_no=1,
            certificate_number="GDP-CURRENT", is_latest_version=True),
        CertificateVersion(certificate_id=superseded_gsp.id, version_no=1,
            certificate_number="GSP-SUPERSEDED", is_latest_version=True),
    ])
    session.flush()
    for gxp, expected_id in (("GSP", gsp.id), ("GDP", gdp.id)):
        for export in (False, True):
            result = cert_report(session, gxp_type=gxp, expiry_days=None, export=export)
            assert result["total_count"] == 1
            assert [item["certificate_id"] for item in result["items"]] == [expected_id]
            assert result["items"][0]["gxp_type"] == gxp
            assert result["items"][0]["site_id"] == site_id
        assert cert_report(session, gxp_type=gxp, expiry_days=30)["total_count"] == 0
    assert cert_report(session, gxp_type="GMP", expiry_days=None)["total_count"] == 2
    with pytest.raises(HTTPException) as invalid:
        cert_report(session, gxp_type="UNKNOWN")
    assert invalid.value.status_code == 422


def test_certificate_report_paging_export_and_validation(session):
    a = cert_report(session, offset=0, limit=1)
    b = cert_report(session, offset=1, limit=1)
    whole = cert_report(session, export=True)
    assert a["total_count"] == b["total_count"] == whole["total_count"] == 2
    assert {x["certificate_id"] for x in a["items"] + b["items"]} == {x["certificate_id"] for x in whole["items"]}
    # An offset past the end must still report the full matching count.
    beyond = cert_report(session, offset=500, limit=1)
    assert beyond["total_count"] == 2
    assert beyond["items"] == []
    assert beyond["offset"] == 500
    assert beyond["limit"] == 1
    assert cert_report(session, gxp_type="GLP")["total_count"] == 0
    for bad in (7, 31):
        with pytest.raises(HTTPException) as exc:
            cert_report(session, expiry_days=bad)
        assert exc.value.status_code == 422
    with pytest.raises(HTTPException):
        cert_report(session, export=True, offset=1)


def test_certificate_report_rejects_multiple_latest_versions_even_outside_window(session):
    row = cert_report(session)["items"][0]
    session.add(CertificateVersion(certificate_id=row["certificate_id"], version_no=3,
        certificate_number="OTHER", expiry_date=date.today() + timedelta(days=500), is_latest_version=True))
    session.flush()
    with pytest.raises(HTTPException) as conflict:
        cert_report(session)
    assert conflict.value.status_code == 409
    service = CatalogReadService()
    with pytest.raises(HTTPException) as detail_conflict:
        service.get_gxp_certificate_detail(session, certificate_id=row["certificate_id"])
    assert detail_conflict.value.status_code == 409
    with pytest.raises(HTTPException) as list_conflict:
        service.list_site_gxp_certificates(session, site_id=row["site_id"], gxp_type="GMP", line_code=None)
    assert list_conflict.value.status_code == 409


def test_certificate_without_current_version_is_not_reported_as_current(session):
    row = cert_report(session)["items"][0]
    version = session.get(CertificateVersion, row["certificate_version_id"])
    version.is_latest_version = False
    session.flush()
    assert row["certificate_id"] not in {item["certificate_id"] for item in cert_report(session, expiry_days=None)["items"]}
    with pytest.raises(HTTPException) as missing:
        CatalogReadService().get_gxp_certificate_detail(session, certificate_id=row["certificate_id"])
    assert missing.value.status_code == 404


def test_certificate_status_uses_existing_current_certificate_policy(session):
    row = cert_report(session)["items"][0]
    version = session.get(CertificateVersion, row["certificate_version_id"])
    version.expiry_date = date.today() - timedelta(days=1)
    session.flush()
    all_current = cert_report(session, expiry_days=None)["items"]
    assert next(item for item in all_current if item["certificate_id"] == row["certificate_id"])["status"] == "expired"


@pytest.mark.parametrize("link", ["missing", "wrong_site", "wrong_gxp"])
def test_certificate_report_rejects_invalid_case_link(session, link):
    row = cert_report(session)["items"][0]
    cert = session.get(Certificate, row["certificate_id"])
    if link == "missing":
        cert.case_id = "missing-case"
    else:
        site = session.get(Site, cert.site_id)
        other = Site(company_id=site.company_id, site_name="Other")
        session.add(other); session.flush()
        case = Case(site_id=other.id if link == "wrong_site" else site.id,
                    gxp_type="GLP" if link == "wrong_gxp" else "GMP", state=CaseState.DRAFT)
        session.add(case); session.flush(); cert.case_id = case.id
    session.flush()
    with pytest.raises(HTTPException) as exc:
        cert_report(session)
    assert exc.value.status_code == 409


def test_change_report_is_per_request_site_owned_no_inferred_gxp(session):
    page = change_report(session)
    assert page["total_count"] == 2
    assert len({x["change_request_id"] for x in page["items"]}) == 2
    assert all("gxp_type" not in x for x in page["items"])
    assert {x["state"] for x in page["items"]} == {"received", "under_review"}
    assert change_report(session, q="Đổi tên")["total_count"] == 1
    assert change_report(session, state="under_review")["total_count"] == 1
    beyond = change_report(session, offset=500, limit=1)
    assert beyond["total_count"] == 2
    assert beyond["items"] == []
    assert beyond["offset"] == 500
    assert beyond["limit"] == 1
    with pytest.raises(HTTPException) as exc:
        change_report(session, state="accepted")
    assert exc.value.status_code == 422
    assert {x["change_request_id"] for x in change_report(session, export=True)["items"]} == {
        x["change_request_id"] for x in page["items"]
    }


def test_report_endpoints_require_existing_read_role(session):
    app = create_app("sqlite:///:memory:")
    for route_path, arguments in (
        ("/reports/certificates", dict(gxp_type=None, q=None, expiry_days=90, export=False, offset=0, limit=100)),
        ("/reports/change-requests", dict(state=None, q=None, export=False, offset=0, limit=100)),
    ):
        endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", "") == route_path)
        allowed = endpoint(**arguments, session=session, user=build_authenticated_user("reader", "reader"))
        assert allowed.total_count == 2
        with pytest.raises(HTTPException) as forbidden:
            endpoint(**arguments, session=session, user=build_authenticated_user("viewer", "viewer"))
        assert forbidden.value.status_code == 403


def test_site_scoped_search_returns_only_canonical_contexts_for_that_site(session):
    site_id = session.scalar(__import__("sqlalchemy").select(Site.id).limit(1))
    company_id = session.scalar(__import__("sqlalchemy").select(Company.id).limit(1))
    other = Site(company_id=company_id, site_name="Cơ sở Khác")
    session.add(other)
    session.flush()
    second = Certificate(site_id=other.id, certificate_type="GLP", latest_flag=True)
    session.add(second)
    session.flush()
    session.add(CertificateVersion(
        certificate_id=second.id, version_no=1, certificate_number="GLP-OTHER",
        is_latest_version=True,
    ))
    session.commit()

    service = CatalogReadService()
    scoped = service.search_facilities(session, site_id=site_id)
    other_scoped = service.search_facilities(session, site_id=other.id)
    unknown = service.search_facilities(session, site_id="missing-site")
    assert scoped["total_count"] >= 1
    assert {row["site_id"] for row in scoped["items"]} == {site_id}
    assert {row["site_id"] for row in other_scoped["items"]} == {other.id}
    assert unknown["total_count"] == 0

    ids = [row["result_key"] for row in scoped["items"]]
    assert len(ids) == len(set(ids))
    current_cr = session.scalar(
        __import__("sqlalchemy").select(ChangeRequest.id).where(ChangeRequest.site_id == site_id).limit(1)
    )
    assert current_cr
    context = scoped["items"][0]
    workspace = service.get_facility_workspace(
        session, site_id=site_id, gxp_type=context["gxp_type"],
        production_line_id=context["production_line_id"], line_code=context["line_code"],
    )
    assert any(
        row["id"] == current_cr and row["source_type"] == "change_request"
        for row in workspace["history"]
    )
    assert {row["site_id"] for row in service.search_facilities(session)["items"]} == {site_id, other.id}


def test_site_filter_retains_pagination_and_gxp_combination(session):
    site_id = session.scalar(__import__("sqlalchemy").select(Site.id).limit(1))
    service = CatalogReadService()
    first = service.search_facilities(session, site_id=site_id, gxp_type="GMP", offset=0, limit=1)
    later = service.search_facilities(session, site_id=site_id, gxp_type="GMP", offset=1, limit=1)
    assert first["total_count"] == 1
    assert len(first["items"]) == 1
    assert later["items"] == []
    assert service.search_facilities(session, site_id=site_id, gxp_type="GLP")["total_count"] == 0


def test_certificate_report_uses_committed_row_values_without_flushing_drafts(session):
    """Search/report filter and result cannot disagree due to dirty cached ORM rows."""
    from sqlalchemy import event, select

    certificate = session.scalar(
        select(Certificate).join(CertificateVersion).where(
            CertificateVersion.certificate_number == "GCN-A"
        )
    )
    version = session.scalar(select(CertificateVersion).where(
        CertificateVersion.certificate_id == certificate.id,
        CertificateVersion.is_latest_version.is_(True),
    ))
    site = session.get(Site, certificate.site_id)
    company = session.get(Company, site.company_id)
    certificate.latest_flag = False
    certificate.certificate_type = "GLP"
    version.certificate_number = "UNSAVED-OPERATOR-NUMBER"
    version.expiry_date = date.today() - timedelta(days=10)
    site.site_name = "UNSAVED-OPERATOR-SITE"
    company.legal_name = "UNSAVED-OPERATOR-COMPANY"
    pending = Company(legal_name="Unrelated pending Company")
    session.add(pending)
    observed_flushes = []

    def forbid_flush(*_args):
        observed_flushes.append(True)
        raise AssertionError("Read-only certificate report autoflushed operator drafts")

    event.listen(session, "before_flush", forbid_flush)
    try:
        report = cert_report(session, q="GCN-A", number="GCN-A", expiry_days=30)
    finally:
        event.remove(session, "before_flush", forbid_flush)
    assert not observed_flushes
    assert report["total_count"] == 1
    assert len(report["items"]) == 1
    item = report["items"][0]
    assert item["certificate_id"] == certificate.id
    assert item["certificate_version_id"] == version.id
    assert item["certificate_number"] == "GCN-A"
    assert item["gxp_type"] == "GMP"
    assert item["status"] == "active"
    assert item["facility_name"] == "Cơ sở Thử"
    assert item["company_name"] == "Công ty thử nghiệm"
    assert item["expiry_date"] == date.today() + timedelta(days=20)
    assert certificate in session.dirty
    assert version in session.dirty
    assert site in session.dirty
    assert company in session.dirty
    assert pending in session.new
    session.rollback()


def test_certificate_report_export_reads_committed_latest_version_not_dirty_cache(session):
    from sqlalchemy import event, select

    version = session.scalar(select(CertificateVersion).where(
        CertificateVersion.certificate_number == "GCN-B",
    ))
    version.certificate_number = "LOCAL-UNSAVED-NUMBER"
    pending = Company(legal_name="Pending while exporting")
    session.add(pending)
    flushed = []
    def on_flush(*_):
        flushed.append(True)

    event.listen(session, "before_flush", on_flush)
    try:
        report = cert_report(session, export=True, expiry_days=None, number="GCN-B")
    finally:
        event.remove(session, "before_flush", on_flush)
        session.rollback()
    assert not flushed
    assert report["total_count"] == 1
    assert report["items"][0]["certificate_number"] == "GCN-B"
    assert report["items"][0]["certificate_version_id"] == version.id

def test_change_report_uses_committed_rows_without_flushing_operator_drafts(session):
    from sqlalchemy import event, inspect, select

    original = change_report(session)
    target = session.get(ChangeRequest, original["items"][0]["change_request_id"])
    site = session.get(Site, target.site_id)
    company = session.get(Company, site.company_id)
    committed = next(item for item in original["items"] if item["change_request_id"] == target.id)

    target.scope_label = "DRAFT-NOT-COMMITTED"
    target.state = ChangeRequestState.ACCEPTED
    site.site_name = "DRAFT-SITE-NOT-COMMITTED"
    company.legal_name = "DRAFT-COMPANY-NOT-COMMITTED"
    pending_company = Company(legal_name="PENDING-COMPANY")
    session.add(pending_company)
    flush_calls = []

    def prohibit_flush(_session, _context, _instances):
        flush_calls.append(True)
        raise AssertionError("A read-only Change Request report flushed an operator draft")

    event.listen(session, "before_flush", prohibit_flush)
    try:
        for export in (False, True):
            result = change_report(session, export=export)
            assert result["total_count"] == 2
            item = next(x for x in result["items"] if x["change_request_id"] == target.id)
            assert item["state"] == committed["state"]
            assert item["scope_label"] == committed["scope_label"]
            assert item["facility_name"] == committed["facility_name"]
            assert item["company_name"] == committed["company_name"]
            assert change_report(session, q="DRAFT-NOT-COMMITTED", export=export)["total_count"] == 0
            assert change_report(session, q=committed["scope_label"], export=export)["total_count"] == 1
        assert not flush_calls
        assert target in session.dirty
        assert site in session.dirty
        assert company in session.dirty
        assert inspect(pending_company).pending
        assert target.scope_label == "DRAFT-NOT-COMMITTED"
        assert site.site_name == "DRAFT-SITE-NOT-COMMITTED"
    finally:
        event.remove(session, "before_flush", prohibit_flush)
        session.rollback()


def test_dashboard_queue_reads_committed_case_site_company_and_line_without_flush(session):
    from sqlalchemy import event, inspect, select
    from backend.app.db.models.phase1 import ProductionLine

    site = session.scalar(select(Site).limit(1))
    company = session.get(Company, site.company_id)
    line = ProductionLine(site_id=site.id, code="PERSISTED-LINE", effective_from=date(2026, 1, 1))
    session.add(line)
    session.flush()
    linked_case = Case(
        site_id=site.id, production_line_id=line.id, gxp_type="GMP",
        state=CaseState.DRAFT, opened_year=2026, legacy_inspection_code="PERSISTED-CASE",
    )
    session.add(linked_case)
    session.commit()
    service = CatalogReadService()
    baseline = service.get_dashboard_summary(session, queue_limit=10)
    expected = next(row for row in baseline["queue"] if row["case_id"] == linked_case.id)

    linked_case.state = CaseState.CLOSED
    linked_case.gxp_type = "GLP"
    linked_case.scope_code = "DRAFT-SCOPE"
    site.site_name = "DRAFT-SITE"
    company.legal_name = "DRAFT-COMPANY"
    line.code = "DRAFT-LINE"
    pending_company = Company(legal_name="PENDING-COMPANY")
    session.add(pending_company)
    flush_calls = []

    def prohibit_flush(_session, _context, _instances):
        flush_calls.append(True)
        raise AssertionError("Dashboard read flushed operator drafts")

    event.listen(session, "before_flush", prohibit_flush)
    try:
        result = service.get_dashboard_summary(session, queue_limit=10)
        displayed = next(row for row in result["queue"] if row["case_id"] == linked_case.id)
        assert displayed == expected
        assert result["total_cases"] == baseline["total_cases"]
        assert result["total_facilities"] == baseline["total_facilities"]
        assert result["active_cases"] == baseline["active_cases"]
        assert not flush_calls
        assert linked_case in session.dirty
        assert site in session.dirty
        assert company in session.dirty
        assert line in session.dirty
        assert inspect(pending_company).pending
        assert linked_case.state == CaseState.CLOSED
        assert line.code == "DRAFT-LINE"
    finally:
        event.remove(session, "before_flush", prohibit_flush)
        session.rollback()


def test_dashboard_rejects_persisted_reparented_canonical_line_despite_cached_owner(session):
    from sqlalchemy import select, update
    from backend.app.db.models.phase1 import ProductionLine

    site = session.scalar(select(Site).limit(1))
    second_site = Site(company_id=site.company_id, site_name="Other site")
    session.add(second_site)
    line = ProductionLine(site_id=site.id, code="LINE-OWNER", effective_from=date(2026, 1, 1))
    session.add(line)
    session.flush()
    linked_case = Case(
        site_id=site.id, production_line_id=line.id, gxp_type="GMP",
        state=CaseState.DRAFT, opened_year=2026,
    )
    session.add(linked_case)
    session.commit()
    assert any(
        row["case_id"] == linked_case.id
        for row in CatalogReadService().get_dashboard_summary(session, queue_limit=10)["queue"]
    )

    assert line.site_id == site.id  # Materialize the old owner into the identity map.
    # SQL DML bypasses the cached ProductionLine and changes persisted values
    # visible within this transaction while its ORM identity remains stale.
    session.execute(
        update(ProductionLine)
        .where(ProductionLine.id == line.id)
        .values(site_id=second_site.id)
        .execution_options(synchronize_session=False)
    )
    assert line.site_id == site.id
    with pytest.raises(HTTPException) as exc:
        CatalogReadService().get_dashboard_summary(session, queue_limit=10)
    assert exc.value.status_code == 409
    assert "ProductionLine" in str(exc.value.detail)
    session.rollback()


def test_facility_search_projects_committed_rows_without_flushing_operator_drafts(session):
    """Facility search must be a persisted read, not a flush or ORM draft view."""
    from sqlalchemy import event, inspect, select

    service = CatalogReadService()
    site = session.scalar(select(Site).limit(1))
    company = session.get(Company, site.company_id)
    version = session.scalar(
        select(CertificateVersion).where(
            CertificateVersion.certificate_number == "GCN-A"
        )
    )
    request = session.scalar(select(ChangeRequest).where(
        ChangeRequest.scope_label == "Đổi tên"
    ))
    baseline = service.search_facilities(session, site_id=site.id)
    assert baseline["total_count"] == 1
    assert baseline["items"][0]["current_certificate_number"] in ("GCN-A", "GCN-B")
    old_site, old_company = site.site_name, company.legal_name

    site.site_name = "UNSAVED-SEARCH-SITE"
    company.legal_name = "UNSAVED-SEARCH-COMPANY"
    version.certificate_number = "UNSAVED-SEARCH-CERTIFICATE"
    request.state = ChangeRequestState.ACCEPTED
    pending = Company(legal_name="UNSAVED-SEARCH-PENDING")
    session.add(pending)
    flush_calls = []

    def forbid_flush(*_):
        flush_calls.append(True)
        raise AssertionError("Facility search flushed operator draft")

    event.listen(session, "before_flush", forbid_flush)
    try:
        for q in (None, old_site):
            result = service.search_facilities(session, site_id=site.id, q=q)
            assert result["total_count"] == baseline["total_count"]
            assert result["items"] == baseline["items"]
        assert service.search_facilities(
            session, site_id=site.id, q="UNSAVED-SEARCH"
        )["total_count"] == 0
        assert service.search_facilities(
            session, site_id=site.id, change_request_states=["received"]
        )["total_count"] == baseline["total_count"]
        assert not flush_calls
        assert site.site_name == "UNSAVED-SEARCH-SITE"
        assert company.legal_name == "UNSAVED-SEARCH-COMPANY"
        assert version.certificate_number == "UNSAVED-SEARCH-CERTIFICATE"
        assert request.state == ChangeRequestState.ACCEPTED
        assert inspect(pending).pending
        assert site in session.dirty
        assert company in session.dirty
        assert version in session.dirty
    finally:
        event.remove(session, "before_flush", forbid_flush)
        session.rollback()


def test_facility_workspace_reads_committed_history_without_flushing_operator_drafts(session):
    """A workspace GET must not flush or replace Case, CR, Site or GCN drafts."""
    from sqlalchemy import event, inspect, select

    service = CatalogReadService()
    site = session.scalar(select(Site).limit(1))
    company = session.get(Company, site.company_id)
    case = Case(
        site_id=site.id, gxp_type="GMP", state=CaseState.PLANNED,
        legacy_inspection_code="WORKSPACE-PERSISTED-CASE",
    )
    session.add(case)
    session.commit()
    baseline = service.get_facility_workspace(
        session, site_id=site.id, gxp_type="GMP",
        line_code=None, production_line_id=None,
    )
    assert baseline["summary"]["facility_name"] == "Cơ sở Thử"
    assert baseline["summary"]["company_name"] == "Công ty thử nghiệm"
    assert any(
        x["id"] == case.id and x["state"] == "planned"
        for x in baseline["history"]
    )

    version = session.scalar(
        select(CertificateVersion).where(
            CertificateVersion.certificate_number == "GCN-A"
        )
    )
    request = session.scalar(select(ChangeRequest).where(
        ChangeRequest.scope_label == "Đổi tên"
    ))
    site.site_name = "UNSAVED-WORKSPACE-SITE"
    company.legal_name = "UNSAVED-WORKSPACE-COMPANY"
    case.state = CaseState.CLOSED
    case.legacy_inspection_code = "UNSAVED-WORKSPACE-CASE"
    request.scope_label = "UNSAVED-WORKSPACE-CHANGE"
    version.certificate_number = "UNSAVED-WORKSPACE-GCN"
    pending = Company(legal_name="UNSAVED-WORKSPACE-PENDING")
    session.add(pending)
    flushes = []

    def fail_flush(*_):
        flushes.append(True)
        raise AssertionError("Facility workspace autoflushed an operator draft")

    event.listen(session, "before_flush", fail_flush)
    try:
        result = service.get_facility_workspace(
            session, site_id=site.id, gxp_type="GMP",
            line_code=None, production_line_id=None,
        )
        assert result == baseline
        assert not flushes
        assert site.site_name == "UNSAVED-WORKSPACE-SITE"
        assert company.legal_name == "UNSAVED-WORKSPACE-COMPANY"
        assert case.state == CaseState.CLOSED
        assert request.scope_label == "UNSAVED-WORKSPACE-CHANGE"
        assert version.certificate_number == "UNSAVED-WORKSPACE-GCN"
        assert inspect(pending).pending
        assert {case, site, company, request, version}.issubset(session.dirty)
    finally:
        event.remove(session, "before_flush", fail_flush)
        session.rollback()


@pytest.mark.parametrize("surface", ["search", "workspace"])
def test_facility_read_fails_closed_on_ambiguous_latest_certificate_version(session, surface):
    """A GCN with two latest Versions must not be silently selected."""
    row = cert_report(session, q="GCN-A")["items"][0]
    session.add(CertificateVersion(
        certificate_id=row["certificate_id"], version_no=3,
        certificate_number="GCN-A-SECOND-LATEST",
        expiry_date=date.today() + timedelta(days=365),
        is_latest_version=True,
    ))
    session.commit()
    service = CatalogReadService()
    with pytest.raises(HTTPException) as exc:
        if surface == "search":
            service.search_facilities(
                session, site_id=row["site_id"], gxp_type="GMP",
            )
        else:
            service.get_facility_workspace(
                session, site_id=row["site_id"], gxp_type="GMP",
                line_code=None, production_line_id=None,
            )
    assert exc.value.status_code == 409
    assert "latest" in str(exc.value.detail).lower()
