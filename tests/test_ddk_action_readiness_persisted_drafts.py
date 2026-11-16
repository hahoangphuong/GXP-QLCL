"""DDK action readiness reads committed owner/version/links without touching drafts.

Disposable SQLite regression; existing PostgreSQL cached-identity tests verify
a second committed writer changes the optimistic token and promotion reason.
"""
from __future__ import annotations

from datetime import date
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AuditEvent, BusinessEligibilityCertificate, BusinessEligibilityCertificateLink,
    BusinessEligibilityVersion, Certificate, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


def test_ddk_readiness_preserves_root_version_link_and_gxp_drafts(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'ddk-readiness.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as seed:
            company = Company(legal_name="Synthetic readiness")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Owner Site")
            foreign_site = Site(company_id=company.id, site_name="Foreign Site")
            seed.add_all([site, foreign_site])
            seed.flush()
            gxp = Certificate(
                site_id=site.id, certificate_type="GLP",
                issuance_basis="administrative_no_inspection", latest_flag=False,
            )
            ddk = BusinessEligibilityCertificate(
                site_id=site.id, company_id=company.id, latest_flag=False,
            )
            seed.add_all([gxp, ddk])
            seed.flush()
            version = BusinessEligibilityVersion(
                business_eligibility_certificate_id=ddk.id,
                version_no=1, certificate_number="SYNTHETIC-DDK",
                issued_on=date(2026, 5, 1),
            )
            seed.add(version)
            seed.flush()
            link = BusinessEligibilityCertificateLink(
                business_eligibility_version_id=version.id,
                certificate_id=gxp.id, link_role="source_certificate",
            )
            seed.add(link)
            seed.commit()
            ids = {
                "ddk": ddk.id, "version": version.id, "link": link.id,
                "gxp": gxp.id, "foreign_site": foreign_site.id,
                "token": ddk.row_version,
            }

        actor = build_authenticated_user(
            "synthetic-ddk-readiness", permissions={
                "certificate.edit", "certificate.approve",
            },
        )
        with Session(engine, autoflush=True, expire_on_commit=False) as session:
            cached_ddk = session.get(BusinessEligibilityCertificate, ids["ddk"])
            cached_version = session.get(BusinessEligibilityVersion, ids["version"])
            cached_link = session.get(BusinessEligibilityCertificateLink, ids["link"])
            cached_gxp = session.get(Certificate, ids["gxp"])
            cached_ddk.latest_flag = True
            cached_version.certificate_number = None
            cached_link.certificate_id = None
            cached_gxp.site_id = ids["foreign_site"]
            assert all(x in session.dirty for x in (
                cached_ddk, cached_version, cached_link, cached_gxp,
            ))
            commands = []

            def capture(_conn, _cursor, statement, _params, _ctx, _many):
                commands.append(statement.lstrip().split(None, 1)[0].upper())

            event.listen(engine, "before_cursor_execute", capture)
            try:
                actions = {
                    row["action_key"]: row
                    for row in CaseWorkflowService().get_business_eligibility_action_readiness(
                        session,
                        business_eligibility_certificate_id=ids["ddk"],
                        user=actor,
                    )
                }
            finally:
                event.remove(engine, "before_cursor_execute", capture)

            assert actions["edit_latest_version"]["expected_version"] == ids["token"]
            assert actions["promote_current"]["available"] is True
            assert actions["promote_current"]["reason_code"] is None
            assert commands and set(commands) == {"SELECT"}
            assert cached_ddk.latest_flag is True
            assert cached_version.certificate_number is None
            assert cached_link.certificate_id is None
            assert cached_gxp.site_id == ids["foreign_site"]
            assert all(x in session.dirty for x in (
                cached_ddk, cached_version, cached_link, cached_gxp,
            ))
            session.rollback()

        with Session(engine) as verify:
            assert verify.get(BusinessEligibilityCertificate, ids["ddk"]).latest_flag is False
            assert verify.get(BusinessEligibilityVersion, ids["version"]).certificate_number == "SYNTHETIC-DDK"
            assert verify.get(BusinessEligibilityCertificateLink, ids["link"]).certificate_id == ids["gxp"]
            assert verify.get(Certificate, ids["gxp"]).site_id != ids["foreign_site"]
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()


def test_ddk_readiness_uses_persisted_current_peer_and_issue_date(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'ddk-current-peer.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as seed:
            company = Company(legal_name="Synthetic current peer")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic Site")
            seed.add(site)
            seed.flush()
            candidate = BusinessEligibilityCertificate(
                site_id=site.id, company_id=company.id, latest_flag=False,
            )
            current = BusinessEligibilityCertificate(
                site_id=site.id, company_id=company.id, latest_flag=True,
            )
            seed.add_all([candidate, current])
            seed.flush()
            candidate_version = BusinessEligibilityVersion(
                business_eligibility_certificate_id=candidate.id,
                version_no=1, certificate_number="CANDIDATE",
                issued_on=date(2026, 1, 1),
            )
            current_version = BusinessEligibilityVersion(
                business_eligibility_certificate_id=current.id,
                version_no=1, certificate_number="CURRENT",
                issued_on=date(2026, 6, 1),
            )
            seed.add_all([candidate_version, current_version])
            seed.commit()
            ids = (candidate.id, current.id, current_version.id)

        actor = build_authenticated_user(
            "synthetic-peer-readiness", permissions={"certificate.approve", "certificate.edit"},
        )
        with Session(engine, autoflush=True, expire_on_commit=False) as reader:
            cached_peer = reader.get(BusinessEligibilityCertificate, ids[1])
            cached_version = reader.get(BusinessEligibilityVersion, ids[2])
            cached_peer.latest_flag = False
            cached_version.issued_on = date(2025, 1, 1)
            actions = {
                x["action_key"]: x
                for x in CaseWorkflowService().get_business_eligibility_action_readiness(
                    reader, business_eligibility_certificate_id=ids[0], user=actor,
                )
            }
            assert actions["promote_current"]["available"] is False
            assert actions["promote_current"]["reason_code"] == "candidate_issue_date_precedes_current"
            assert cached_peer.latest_flag is False
            assert cached_version.issued_on == date(2025, 1, 1)
            assert cached_peer in reader.dirty and cached_version in reader.dirty
            reader.rollback()
        with Session(engine) as verify:
            assert verify.get(BusinessEligibilityCertificate, ids[1]).latest_flag is True
            assert verify.get(BusinessEligibilityVersion, ids[2]).issued_on == date(2026, 6, 1)
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()
