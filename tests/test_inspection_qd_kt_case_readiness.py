"""Read-only QĐKT readiness proves sources without unlocking Word generation."""
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Company, Site, InspectionPlan, InspectionDecision, InspectionTeam
from backend.app.document.inspection_qd_kt_case_readiness import inspect_qdkt_case_readiness


def test_case_readiness_is_blocked_even_with_valid_decision_and_site(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'qdkt-readiness.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Synthetic")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Test",
                    site_address="Registered address", province_name="Đà Nẵng")
        session.add(site)
        session.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
        session.add(case)
        session.flush()
        plan = InspectionPlan(case_id=case.id)
        session.add(plan)
        session.flush()
        decision = InspectionDecision(
            inspection_plan_id=plan.id, ordinal=1, reference="123/QD",
            decision_on=date(2026, 10, 22), legacy_raw="123/QD 22/10/2026",
        )
        session.add(decision)
        session.flush()
        result = inspect_qdkt_case_readiness(session, case_id=case.id)
        assert result.decision_source_id == decision.id
        assert result.registered_site_id == site.id
        assert result.ready_to_render is False
        assert "LEGACY_PROVINCE_MAPPING_UNPROVEN" not in result.blockers
        assert "CASE_INSPECTION_TEAM_NOT_UNIQUE" in result.blockers
        assert "BLANK_ISSUANCE_DATE_BOOKMARK_UNVERIFIED" in result.blockers
        assert "QDKT_TYPED_RENDER_CONTRACT_MISSING" in result.blockers
        assert len(session.new) == 0 and len(session.dirty) == 0
        session.rollback()
    engine.dispose()


def test_case_readiness_missing_sources_returns_blockers_not_render_permission(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'qdkt-missing.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result = inspect_qdkt_case_readiness(session, case_id="nonexistent")
        assert result.ready_to_render is False
        assert result.decision_source_id is None
        assert result.registered_site_id is None
        assert "CASE_NOT_FOUND" in result.blockers
        assert "CASE_REGISTERED_SITE_NOT_FOUND" in result.blockers
        assert len(result.blockers) == len(set(result.blockers))
    engine.dispose()


def test_legacy_province_mismatch_is_reported_without_authorizing_render(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'unknown-province.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Synthetic")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Test",
                    site_address="Registered location", province_name="Unmapped new province")
        session.add(site)
        session.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
        session.add(case)
        session.flush()
        result = inspect_qdkt_case_readiness(session, case_id=case.id)
        assert "LEGACY_PROVINCE_MAPPING_UNPROVEN" in result.blockers
        assert "MANUFACTURING_CLASSIFICATION_SOURCE_UNPROVEN" in result.blockers
        assert result.ready_to_render is False
        assert result.registered_site_id == site.id
        session.rollback()
    engine.dispose()


def test_readiness_reports_empty_team_without_confusing_it_with_word_mapping(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'team-empty.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Synthetic")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Test",
                    site_address="Registered address", province_name="Đà Nẵng")
        session.add(site)
        session.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
        session.add(case)
        session.flush()
        session.add(InspectionTeam(case_id=case.id))
        session.flush()
        result = inspect_qdkt_case_readiness(session, case_id=case.id)
        assert "INSPECTION_TEAM_EMPTY" in result.blockers
        assert "CASE_INSPECTION_TEAM_NOT_UNIQUE" not in result.blockers
        assert "INSPECTION_TEAM_BOOKMARK_CONTRACT_UNRESOLVED" in result.blockers
        assert result.ready_to_render is False
        assert len(session.new) == 0 and len(session.dirty) == 0
        session.rollback()
    engine.dispose()



def test_readiness_exposes_all_14_specific_unresolved_bookmark_owners(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'bookmark-owner.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result = inspect_qdkt_case_readiness(session, case_id="nonexistent")
        blocked = {x.removeprefix("QDKT_BOOKMARK_OWNER_BLOCKED_") for x in result.blockers
                   if x.startswith("QDKT_BOOKMARK_OWNER_BLOCKED_")}
        partial = {x.removeprefix("QDKT_BOOKMARK_OWNER_PARTIAL_") for x in result.blockers
                   if x.startswith("QDKT_BOOKMARK_OWNER_PARTIAL_")}
        assert blocked == {
            "FULLDATE", "DIADIEM", "DIADIEMX", "DIACHICOSO",
            "QDKT", "NGAYQDKT", "VKNX", "VKN",
        }
        assert partial == {"TENCOSO", "HSDK", "NGAYNOPHSDK", "TT3X", "TT3DEL", "TTX"}
        assert result.ready_to_render is False
        assert "QDKT_BOOKMARK_PROVENANCE_UNVERIFIED" not in result.blockers
        assert len(session.new) == 0 and len(session.dirty) == 0
    engine.dispose()


def test_readiness_stays_closed_when_provenance_inventory_is_corrupt(tmp_path, monkeypatch):
    import backend.app.document.inspection_qd_kt_case_readiness as readiness
    from backend.app.document.inspection_qd_kt_provenance_gate import QdKtProvenanceGateBlocked
    def fail_inventory():
        raise QdKtProvenanceGateBlocked("QDKT_OWNER_STATUS_REQUIRES_REVIEW")
    monkeypatch.setattr(readiness, "inspect_qdkt_source_provenance", fail_inventory)
    engine = create_engine(f"sqlite:///{(tmp_path / 'bad-inventory.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result = inspect_qdkt_case_readiness(session, case_id="nonexistent")
        assert "QDKT_BOOKMARK_PROVENANCE_UNVERIFIED" in result.blockers
        assert not any(x.startswith("QDKT_BOOKMARK_OWNER_BLOCKED_") for x in result.blockers)
        assert result.ready_to_render is False
    engine.dispose()
