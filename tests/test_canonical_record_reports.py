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


def test_certificate_report_paging_export_and_validation(session):
    a = cert_report(session, offset=0, limit=1)
    b = cert_report(session, offset=1, limit=1)
    whole = cert_report(session, export=True)
    assert a["total_count"] == b["total_count"] == whole["total_count"] == 2
    assert {x["certificate_id"] for x in a["items"] + b["items"]} == {x["certificate_id"] for x in whole["items"]}
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


def test_certificate_without_current_version_is_not_reported_as_current(session):
    row = cert_report(session)["items"][0]
    version = session.get(CertificateVersion, row["certificate_version_id"])
    version.is_latest_version = False
    session.flush()
    assert row["certificate_id"] not in {item["certificate_id"] for item in cert_report(session, expiry_days=None)["items"]}


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
