"""Facility GxP Certificate list: committed row projection, not ORM drafts."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    Case, Certificate, CertificateVersion, Company, ProductionLine, Site,
)
from backend.app.services.catalog import CatalogReadService


def _seed(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'site-list.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Certificate list Company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Certificate list Site")
        other = Site(company_id=company.id, site_name="Other Site")
        db.add_all([site, other])
        db.flush()
        line = ProductionLine(site_id=site.id, code="LINE-PERSISTED", effective_from=date(2023, 1, 1))
        db.add(line)
        db.flush()
        linked = Case(site_id=site.id, gxp_type="GMP", scope_code="CASE-PERSISTED", state=CaseState.CERTIFIED)
        db.add(linked)
        db.flush()
        cert = Certificate(
            site_id=site.id, case_id=linked.id, certificate_type="GMP",
            production_line_id=line.id, line_code="OLD-TEXT", latest_flag=True,
        )
        wide = Certificate(site_id=site.id, certificate_type="GMP", latest_flag=True)
        db.add_all([cert, wide])
        db.flush()
        version = CertificateVersion(
            certificate_id=cert.id, version_no=1, is_latest_version=True,
            certificate_number="PERSISTED-CERT", issue_date=date(2025, 1, 1),
        )
        wide_version = CertificateVersion(
            certificate_id=wide.id, version_no=1, is_latest_version=True,
            certificate_number="WIDE-CERT",
        )
        db.add_all([version, wide_version])
        db.commit()
        return engine, site.id, other.id, line.id, linked.id, cert.id, wide.id, version.id


def test_site_certificate_list_uses_committed_rows_and_never_flushes_drafts(tmp_path):
    engine, site_id, _, line_id, case_id, cert_id, wide_id, version_id = _seed(tmp_path)
    try:
        with Session(engine, autoflush=True, expire_on_commit=False) as reader:
            root = reader.get(Certificate, cert_id)
            version = reader.get(CertificateVersion, version_id)
            case = reader.get(Case, case_id)
            line = reader.get(ProductionLine, line_id)
            root.latest_flag = False
            version.certificate_number = "UNSAVED-VERSION"
            version.issue_date = date(2026, 11, 19)
            case.scope_code = "UNSAVED-CASE-CODE"
            line.code = "UNSAVED-LINE"
            draft = Company(legal_name="Pending unrelated Company")
            reader.add(draft)
            flushes = []

            def reject_flush(*_args):
                flushes.append(True)
                raise AssertionError("Certificate list GET must not autoflush operator drafts")

            event.listen(reader, "before_flush", reject_flush)
            try:
                data = CatalogReadService().list_site_gxp_certificates(
                    reader, site_id=site_id, gxp_type="GMP",
                    line_code="LINE-PERSISTED", production_line_id=line_id,
                )
            finally:
                event.remove(reader, "before_flush", reject_flush)

            assert flushes == []
            assert len(data["items"]) == 2
            canonical = next(item for item in data["items"] if item["certificate_id"] == cert_id)
            facility = next(item for item in data["items"] if item["certificate_id"] == wide_id)
            assert canonical["certificate_number"] == "PERSISTED-CERT"
            assert canonical["latest_flag"] is True
            assert canonical["issue_date"] == date(2025, 1, 1)
            assert canonical["production_line_id"] == line_id
            assert canonical["production_line_code"] == "LINE-PERSISTED"
            assert canonical["line_code"] == "LINE-PERSISTED"
            assert canonical["context_match_kind"] == "exact_line"
            assert facility["context_match_kind"] == "facility_wide"
            assert root.latest_flag is False
            assert version.certificate_number == "UNSAVED-VERSION"
            assert line.code == "UNSAVED-LINE"
            assert case.scope_code == "UNSAVED-CASE-CODE"
            assert all(x in reader.dirty for x in (root, version, line, case))
            assert draft in reader.new
            reader.rollback()
        with Session(engine) as verify:
            assert verify.get(CertificateVersion, version_id).certificate_number == "PERSISTED-CERT"
    finally:
        engine.dispose()


def test_site_certificate_list_rejects_committed_line_owner_reparent_despite_cached_line(tmp_path):
    engine, site_id, other_id, line_id, _case_id, cert_id, _, _ = _seed(tmp_path)
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as reader:
            cached_line = reader.get(ProductionLine, line_id)
            cached_cert = reader.get(Certificate, cert_id)
            with Session(engine) as writer:
                writer.execute(
                    update(ProductionLine).where(ProductionLine.id == line_id)
                    .values(site_id=other_id)
                )
                writer.commit()
            with pytest.raises(HTTPException) as denied:
                CatalogReadService().list_site_gxp_certificates(
                    reader, site_id=site_id, gxp_type="GMP", line_code=None,
                )
            assert denied.value.status_code == 409
            assert "Canonical ProductionLine" in str(denied.value.detail)
            assert cached_line.site_id == site_id
            assert cached_cert.site_id == site_id
    finally:
        engine.dispose()
