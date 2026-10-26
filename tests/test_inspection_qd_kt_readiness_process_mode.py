"""Separate draft preflight from approved-reference preflight without enabling rendering."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Company, Site
from backend.app.document.inspection_qd_kt_case_readiness import inspect_qdkt_case_readiness


def test_draft_readiness_does_not_require_issued_decision(tmp_path, monkeypatch):
    import backend.app.document.inspection_qd_kt_case_readiness as module
    engine = create_engine(f"sqlite:///{(tmp_path / 'draft.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Synthetic")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Synthetic",
                    site_address="Registered address", province_name="Đà Nẵng")
        session.add(site)
        session.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
        session.add(case)
        session.flush()

        def forbidden(*args, **kwargs):
            raise AssertionError("DRAFT_QUERIED_ISSUED_DECISION")

        monkeypatch.setattr(module, "read_latest_qdkt_reference_for_case", forbidden)
        result = inspect_qdkt_case_readiness(
            session, case_id=case.id, purpose="DRAFT_QDKT")
        assert result.decision_source_id is None
        assert result.registered_site_id == site.id
        assert result.ready_to_render is False
        assert "QDKT_TYPED_RENDER_CONTRACT_MISSING" in result.blockers
        assert any(b.startswith("QDKT_BOOKMARK_OWNER_") for b in result.blockers)
        assert len(session.new) == len(session.dirty) == 0
        session.rollback()
    engine.dispose()


def test_default_approved_reference_still_requires_issued_decision(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'reference.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result = inspect_qdkt_case_readiness(session, case_id="absent")
        assert "CASE_NOT_FOUND" in result.blockers
        assert result.decision_source_id is None
        assert result.ready_to_render is False
    engine.dispose()


def test_unknown_readiness_purpose_rejected_before_any_db_access():
    with pytest.raises(ValueError, match="QDKT_READINESS_PURPOSE_INVALID"):
        inspect_qdkt_case_readiness(None, case_id="case", purpose="AUTO_ISSUE")
