"""Registered Site is the only address source for draft QĐKT."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Company, Site
from backend.app.document.inspection_qd_kt_registered_site import (
    QdKtRegisteredSiteBlocked, require_registered_site_address,
    read_qdkt_registered_site,
)


@pytest.mark.parametrize("value,reason", [
    (None, "REGISTERED_SITE_ADDRESS_MISSING"),
    ("", "REGISTERED_SITE_ADDRESS_MISSING"),
    ("  ", "REGISTERED_SITE_ADDRESS_MISSING"),
    (" Street, Hanoi ", "REGISTERED_SITE_ADDRESS_UNNORMALIZED"),
])
def test_missing_or_unapproved_address_cannot_be_guessed(value, reason):
    with pytest.raises(QdKtRegisteredSiteBlocked, match=reason):
        require_registered_site_address(
            case_id="case", site_id="site", address=value, province_name="Ha Noi",
        )


def test_qdkt_case_uses_only_its_registered_site_address(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'registered-site.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Synthetic company")
        session.add(company)
        session.flush()
        first = Site(company_id=company.id, site_name="Site North",
                     site_address="Registered address North", province_name="Ha Noi")
        second = Site(company_id=company.id, site_name="Site South",
                      site_address="Registered address South", province_name="Da Nang")
        session.add_all([first, second])
        session.flush()
        case_a = Case(site_id=first.id, gxp_type="GMP", state=CaseState.DRAFT)
        case_b = Case(site_id=second.id, gxp_type="GMP", state=CaseState.DRAFT)
        session.add_all([case_a, case_b])
        session.flush()
        assert read_qdkt_registered_site(session, case_id=case_a.id).registered_address == "Registered address North"
        assert read_qdkt_registered_site(session, case_id=case_b.id).registered_address == "Registered address South"
        with pytest.raises(QdKtRegisteredSiteBlocked, match="CASE_REGISTERED_SITE_NOT_FOUND"):
            read_qdkt_registered_site(session, case_id="missing")
        assert len(session.dirty) == 0
        assert len(session.new) == 0
        session.rollback()
    engine.dispose()


def test_pending_unflushed_site_address_edit_not_persisted_by_reader(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'pending-site.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Synthetic")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Name",
                    site_address="Original registered")
        session.add(site)
        session.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
        session.add(case)
        session.flush()
        site.site_address = "Pending non-persisted edit"
        assert read_qdkt_registered_site(session, case_id=case.id).registered_address == "Original registered"
        assert site in session.dirty
        session.rollback()
    engine.dispose()
