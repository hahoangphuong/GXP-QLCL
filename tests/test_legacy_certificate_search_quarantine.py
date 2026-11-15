"""Quarantined legacy Case links are read-only annotations, never a new truth.

The only admitted exclusions are three exact db.cc/db.ktra/db.cso source pairs.
Unknown, modified or new Certificate→Case corruption must remain HTTP 409.
"""
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    Case, Certificate, CertificateVersion, Company, Site, AuditEvent,
)
from backend.app.services.catalog import CatalogReadService
from backend.app.services.workflow import CaseWorkflowService


def _source_fixture(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'legacy-search-quarantine.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Historical source Company")
        db.add(company)
        db.flush()
        sites = {}
        for legacy_id in (46, 73, 72, 298, 90):
            site = Site(
                company_id=company.id,
                legacy_site_id=legacy_id,
                site_name=f"Historical Site {legacy_id}",
            )
            db.add(site)
            db.flush()
            sites[legacy_id] = site

        origin_378 = Case(
            site_id=sites[72].id, legacy_inspection_id=378,
            gxp_type="GMP", state=CaseState.CERTIFIED,
        )
        origin_1023 = Case(
            site_id=sites[298].id, legacy_inspection_id=1023,
            gxp_type="GMP", state=CaseState.CERTIFIED,
        )
        good_case = Case(
            site_id=sites[90].id, legacy_inspection_id=8000,
            gxp_type="GMP", state=CaseState.CERTIFIED,
        )
        db.add_all([origin_378, origin_1023, good_case])
        db.flush()
        identities = []
        for legacy_cert, site_id, owner in (
            (376, 73, origin_378),
            (1037, 46, origin_1023),
            (1180, 46, origin_1023),
            (9000, 90, good_case),
        ):
            cert = Certificate(
                legacy_certificate_id=legacy_cert,
                site_id=sites[site_id].id,
                case_id=owner.id,
                certificate_type="GMP",
                issuance_basis="inspection_case",
                latest_flag=True,
            )
            db.add(cert)
            db.flush()
            db.add(CertificateVersion(
                certificate_id=cert.id,
                version_no=1,
                certificate_number=f"GMP-{legacy_cert}",
                issue_date=date(2024, 1, 1),
                is_latest_version=True,
            ))
            identities.append((legacy_cert, cert.id))
        db.commit()
        return engine, {k: v for k, v in identities}, {k: site.id for k, site in sites.items()}


def _search(service, db, *, gxp_type="GMP", q=None, offset=0, limit=50):
    return service.search_facilities(
        db, gxp_type=gxp_type, q=q, offset=offset, limit=limit,
    )


def test_exact_three_witnessed_historical_source_pairs_are_quarantined_from_reads(tmp_path):
    engine, certs, sites = _source_fixture(tmp_path)
    catalog = CatalogReadService()
    with Session(engine) as db:
        before_cert = db.scalar(select(func.count()).select_from(Certificate))
        before_audit = db.scalar(select(func.count()).select_from(AuditEvent))
        for typ in ("GMP", "GLP", None):
            page = _search(catalog, db, gxp_type=typ, offset=0, limit=1)
            assert page["quarantined_historical_certificate_legacy_ids"] == [376, 1037, 1180]
            assert page["total_count"] >= 1 if typ != "GLP" else True
            assert all(
                item["current_certificate_number"] not in
                {"GMP-376", "GMP-1037", "GMP-1180"}
                for item in page["items"]
            )
        # A real source-owned good GMP certificate remains discoverable.
        good = _search(catalog, db, q="Historical Site 90")
        assert any(item["current_certificate_number"] == "GMP-9000" for item in good["items"])
        # The whole-site workspace and selector also cannot advertise a
        # cross-Site certificate's wrong Case as current or selectable.
        workspace = catalog.get_facility_workspace(
            db, site_id=sites[46], gxp_type="GMP", line_code=None,
        )
        assert workspace["summary"]["quarantined_historical_certificate_legacy_ids"] == [1037, 1180]
        assert workspace["summary"]["current_certificate_number"] is None
        listed = catalog.list_site_gxp_certificates(
            db, site_id=sites[46], gxp_type="GMP", line_code=None,
        )
        assert listed["quarantined_historical_certificate_legacy_ids"] == [1037, 1180]
        assert listed["items"] == []
        # Source-owned certificate detail, history, and all business validators
        # retain strict fail-closed behavior, irrespective of quarantine.
        for legacy_id in (376, 1037, 1180):
            with pytest.raises(HTTPException, match="invalid linked Case") as exc:
                catalog.get_gxp_certificate_detail(db, certificate_id=certs[legacy_id])
            assert exc.value.status_code == 409
            with pytest.raises(HTTPException, match="invalid linked Case"):
                catalog.get_gxp_certificate_version_history(db, certificate_id=certs[legacy_id])
            with pytest.raises(HTTPException, match="invalid linked Case"):
                CaseWorkflowService._validate_certificate_linked_case(
                    db, db.get(Certificate, certs[legacy_id]),
                )
        assert db.scalar(select(func.count()).select_from(Certificate)) == before_cert
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == before_audit


@pytest.mark.parametrize("variant", [
    "unknown_legacy_id",
    "changed_legacy_case",
    "wrong_gxp",
    "wrong_issuance_basis",
])
def test_quarantine_refuses_any_unauthorized_or_drifted_link(tmp_path, variant):
    engine, certs, sites = _source_fixture(tmp_path)
    with Session(engine) as db:
        cert = db.get(Certificate, certs[376])
        if variant == "unknown_legacy_id":
            cert.legacy_certificate_id = 9376
        elif variant == "changed_legacy_case":
            cert.case_id = db.scalar(
                select(Case.id).where(Case.legacy_inspection_id == 1023)
            )
        elif variant == "wrong_gxp":
            cert.certificate_type = "GLP"
        elif variant == "wrong_issuance_basis":
            cert.issuance_basis = "administrative_no_inspection"
        db.commit()
        with pytest.raises(HTTPException, match="invalid linked Case") as err:
            _search(CatalogReadService(), db, gxp_type="GLP", limit=1)
        assert err.value.status_code == 409


def test_unrelated_unknown_historical_link_still_blocks_global_search(tmp_path):
    engine, _, sites = _source_fixture(tmp_path)
    with Session(engine) as db:
        other = Case(
            site_id=sites[298], gxp_type="GMP", state=CaseState.CERTIFIED
        )
        db.add(other)
        db.flush()
        db.add(Certificate(
            legacy_certificate_id=1999,
            site_id=sites[73],
            case_id=other.id,
            certificate_type="GMP",
            issuance_basis="inspection_case",
            latest_flag=False,
        ))
        db.commit()
        with pytest.raises(HTTPException, match="invalid linked Case"):
            _search(CatalogReadService(), db, gxp_type="GLP", offset=0, limit=1)
