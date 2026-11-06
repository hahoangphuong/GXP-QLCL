"""Canonical report queries against an isolated disposable PostgreSQL schema."""
import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import (
    Certificate, CertificateVersion, ChangeRequest, Company, Site,
)
from backend.app.services.catalog import CatalogReadService


def test_canonical_record_reports_disposable_postgres():
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "record_report_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            company = Company(legal_name="Công ty kiểm tra")
            db.add(company)
            db.flush()
            site = Site(company_id=company.id, site_name="Cơ sở kiểm tra")
            db.add(site)
            db.flush()
            current = Certificate(site_id=site.id, certificate_type="GMP", latest_flag=True)
            replaced = Certificate(site_id=site.id, certificate_type="GMP", latest_flag=False)
            db.add_all([current, replaced])
            db.flush()
            db.add_all([
                CertificateVersion(certificate_id=current.id, version_no=1,
                    is_latest_version=True, certificate_number="GCN-PG",
                    expiry_date=date.today() + timedelta(days=25)),
                CertificateVersion(certificate_id=replaced.id, version_no=1,
                    is_latest_version=True, certificate_number="GCN-REPLACED",
                    expiry_date=date.today() + timedelta(days=15)),
                ChangeRequest(site_id=site.id, state=ChangeRequestState.RECEIVED,
                    scope_label="Đổi tên"),
                ChangeRequest(site_id=site.id, state=ChangeRequestState.UNDER_REVIEW,
                    scope_label="Đổi địa chỉ"),
            ])
            db.commit()
            service = CatalogReadService()
            certificates = service.get_certificate_report(db, gxp_type="GMP", q=None,
                expiry_days=30, export=True, offset=0, limit=100)
            assert certificates["total_count"] == 1
            assert certificates["items"][0]["certificate_id"] == current.id
            assert certificates["items"][0]["certificate_number"] == "GCN-PG"
            # GSP/GDP are read-only Certificate types, not GMP editing aliases.
            gsp = Certificate(site_id=site.id, certificate_type="GSP", latest_flag=True)
            gdp = Certificate(site_id=site.id, certificate_type="GDP", latest_flag=True)
            db.add_all([gsp, gdp])
            db.flush()
            db.add_all([
                CertificateVersion(certificate_id=gsp.id, version_no=1,
                    is_latest_version=True, certificate_number="GSP-PG"),
                CertificateVersion(certificate_id=gdp.id, version_no=1,
                    is_latest_version=True, certificate_number="GDP-PG"),
            ])
            db.flush()
            for cert_type, expected_id in (("GSP", gsp.id), ("GDP", gdp.id)):
                page = service.get_certificate_report(db, gxp_type=cert_type, q=None,
                    expiry_days=None, export=True, offset=0, limit=100)
                assert page["total_count"] == 1
                assert page["items"][0]["certificate_id"] == expected_id
                assert page["items"][0]["gxp_type"] == cert_type
                assert page["items"][0]["site_id"] == site.id
            changes = service.get_change_request_report(db, state=None, q="kiểm tra",
                export=True, offset=0, limit=100)
            assert changes["total_count"] == 2
            assert len({x["change_request_id"] for x in changes["items"]}) == 2
            assert all("gxp_type" not in item for item in changes["items"])
            db.add(CertificateVersion(certificate_id=current.id, version_no=2,
                is_latest_version=True, certificate_number="GCN-CONFLICT",
                expiry_date=date.today() + timedelta(days=300)))
            db.flush()
            with pytest.raises(HTTPException) as conflict:
                service.get_certificate_report(db, gxp_type="GMP", q=None,
                    expiry_days=30, export=True, offset=0, limit=100)
            assert conflict.value.status_code == 409
            with pytest.raises(HTTPException) as detail_conflict:
                service.get_gxp_certificate_detail(db, certificate_id=current.id)
            assert detail_conflict.value.status_code == 409
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
