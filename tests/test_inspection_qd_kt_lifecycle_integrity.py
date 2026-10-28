"""Adversarial lifecycle/ownership tests; persisted atoms are not legal issuance."""
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, update
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    Case, Company, Site, InspectionPlan, InspectionDecision, InspectionTeam, InspectionTeamMember,
)
from backend.app.document.inspection_qd_kt_decision_source import (
    QdKtDecisionSourceBlocked, require_latest_qdkt_reference, require_unique_qdkt_source,
    read_latest_qdkt_reference_for_case, read_unique_qdkt_source_for_case,
)
from backend.app.document.inspection_qd_kt_case_source_bundle import (
    QdKtCaseSourceBlocked, require_qdkt_case_source_bundle, read_qdkt_case_source_bundle,
    read_qdkt_preapproval_case_source, require_qdkt_preapproval_case_source,
)
from backend.app.document.inspection_qd_kt_case_readiness import inspect_qdkt_case_readiness
from backend.app.document.inspection_qd_kt_registered_site import read_qdkt_registered_site
from backend.app.document.inspection_qd_kt_team_source import read_qdkt_team_source
from test_inspection_qd_kt_latest_reference import D1, D2, D3


@pytest.mark.parametrize("field,value", [
    ("ordinal", True), ("ordinal", 1.0), ("ordinal", None),
    ("id", 7), ("id", []), ("id", " "),
    ("reference", 3), ("legacy_raw", 3), ("relation_type", []),
])
def test_malformed_decision_atoms_return_owner_blocker(field, value):
    with pytest.raises(QdKtDecisionSourceBlocked):
        require_latest_qdkt_reference([replace(D1, **{field: value})])


def test_unique_gate_does_not_accept_boolean_ordinal():
    with pytest.raises(QdKtDecisionSourceBlocked):
        require_unique_qdkt_source([replace(D1, ordinal=True)], plan_decision_reference=D1.reference,
            plan_decision_date=D1.decision_on, plan_decision_legacy_raw=D1.legacy_raw)


def test_foreign_atom_and_string_callbacks_are_not_executed():
    class ForeignText(str):
        def __eq__(self, other):
            raise AssertionError("foreign equality called")
    for row in (SimpleNamespace(**vars(D1)), replace(D1, reference=ForeignText(D1.reference))):
        with pytest.raises(QdKtDecisionSourceBlocked):
            require_latest_qdkt_reference([row])


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'lifecycle.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        company = Company(legal_name="Synthetic lifecycle")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Synthetic", site_address="Registered address", province_name="Đà Nẵng")
        session.add(site)
        session.flush()
        contexts = []
        for i in range(2):
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
            session.add(case)
            session.flush()
            plan = InspectionPlan(case_id=case.id, decision_reference=f"{i}/QD", decision_date=date(2026, 1, 1), decision_legacy_raw=f"{i}/QD raw")
            team = InspectionTeam(case_id=case.id)
            session.add_all([plan, team])
            session.flush()
            decision = InspectionDecision(inspection_plan_id=plan.id, ordinal=1, reference=plan.decision_reference, decision_on=plan.decision_date, legacy_raw=plan.decision_legacy_raw)
            member = InspectionTeamMember(team_id=team.id, sort_order=0, role_code="LEADER", display_name=f"Synthetic {i}", identity_kind="LEGACY_PERSON")
            session.add_all([decision, member])
            session.flush()
            contexts.append((case, plan, decision, team, member))
        session.commit()
        yield session, contexts
    engine.dispose()


def test_pending_plan_identity_cannot_redirect_to_another_case(db):
    session, (a, b) = db
    a[1].id = b[1].id
    selected = read_latest_qdkt_reference_for_case(session, case_id=a[0].id)
    assert selected.source_decision_id == a[2].id
    assert a[1] in session.dirty  # No flush, refresh, expiration or draft loss.


def test_pending_decision_and_team_changes_are_not_persisted_source(db):
    session, (a, _) = db
    a[2].reference = "UNSAVED REFERENCE"
    a[4].display_name = "UNSAVED NAME"
    assert read_latest_qdkt_reference_for_case(session, case_id=a[0].id).reference == "0/QD"
    assert read_qdkt_team_source(session, case_id=a[0].id).members[0].display_name == "Synthetic 0"
    assert a[2].reference == "UNSAVED REFERENCE" and a[4].display_name == "UNSAVED NAME"


def test_stale_identity_map_is_not_a_database_snapshot(db):
    session, (a, _) = db
    session.execute(update(InspectionDecision).where(InspectionDecision.id == a[2].id).values(reference="DB CURRENT").execution_options(synchronize_session=False))
    assert a[2].reference == "0/QD"
    assert read_latest_qdkt_reference_for_case(session, case_id=a[0].id).reference == "DB CURRENT"
    assert a[2].reference == "0/QD"  # Reader must not overwrite tracked objects.


def test_cross_case_decision_cannot_be_composed_with_local_site_and_team(db):
    session, (a, b) = db
    other = read_latest_qdkt_reference_for_case(session, case_id=b[0].id)
    with pytest.raises(QdKtCaseSourceBlocked, match="QDKT_CASE_SOURCE_IDENTITY_MISMATCH"):
        require_qdkt_case_source_bundle(case_id=a[0].id, decision=other,
            site=read_qdkt_registered_site(session, case_id=a[0].id), team=read_qdkt_team_source(session, case_id=a[0].id))


def test_reference_readiness_never_certifies_external_legal_issuance(db):
    session, (a, _) = db
    result = inspect_qdkt_case_readiness(session, case_id=a[0].id)
    assert result.decision_source_id == a[2].id
    assert "QDKT_LEGAL_ISSUANCE_EVIDENCE_UNPROVEN" in result.blockers
    assert result.ready_to_render is False


@pytest.mark.parametrize("count", [0, 1, 3])
def test_process_a_reads_no_decision_or_plan_even_with_existing_chain(db, count):
    session, (a, _) = db
    if count == 0:
        session.delete(a[2])
    elif count == 3:
        prior = a[2]
        for ordinal in (2, 3):
            row = InspectionDecision(inspection_plan_id=a[1].id, ordinal=ordinal, reference=f"{ordinal}/QD", decision_on=date(2026, 1, ordinal), legacy_raw="Synthetic replacement", relation_type="REPLACES", related_decision_id=prior.id)
            session.add(row)
            session.flush()
            prior = row
    session.commit()
    statements = []
    def trace(conn, cursor, statement, parameters, context, many):
        assert statement.lstrip().upper().startswith("SELECT")
        assert "inspection_decision" not in statement.lower()
        assert "inspection_plan" not in statement.lower()
        statements.append(statement)
    event.listen(session.bind, "before_cursor_execute", trace)
    try:
        source = read_qdkt_preapproval_case_source(session, case_id=a[0].id)
        readiness = inspect_qdkt_case_readiness(session, case_id=a[0].id, purpose="DRAFT_QDKT")
    finally:
        event.remove(session.bind, "before_cursor_execute", trace)
    assert statements
    assert not hasattr(source, "decision") and not hasattr(source, "decision_on")
    assert not hasattr(source, "decision_reference")
    assert source.process == "DRAFT_QDKT" and source.ready_to_render is False
    assert readiness.decision_source_id is None and readiness.ready_to_render is False


def test_explicit_same_day_chain_is_ordered_by_lineage_not_date():
    rows = [D1, replace(D2, decision_on=D1.decision_on), replace(D3, decision_on=D1.decision_on)]
    assert require_latest_qdkt_reference(list(reversed(rows))).source_decision_id == D3.id


@pytest.mark.parametrize("owner", ["plan", "team"])
def test_ownership_must_still_match_at_source_query(db, monkeypatch, owner):
    from backend.app.document.inspection_qd_kt_team_source import QdKtTeamSourceBlocked
    session, (a, _) = db
    third = Case(site_id=a[0].site_id, gxp_type="GMP", state=CaseState.DRAFT)
    session.add(third)
    session.commit()
    original = session.execute
    changed = []
    def move_owner(statement, *args, **kwargs):
        target = "inspection_decision" if owner == "plan" else "inspection_team_member"
        if statement.is_select and target in str(statement) and not changed:
            changed.append(True)
            model, row = (InspectionPlan, a[1]) if owner == "plan" else (InspectionTeam, a[3])
            original(update(model).where(model.id == row.id).values(case_id=third.id).execution_options(synchronize_session=False))
        return original(statement, *args, **kwargs)
    monkeypatch.setattr(session, "execute", move_owner)
    reader = read_latest_qdkt_reference_for_case if owner == "plan" else read_qdkt_team_source
    with pytest.raises((QdKtDecisionSourceBlocked, QdKtTeamSourceBlocked)):
        reader(session, case_id=a[0].id)
    assert changed


def test_readers_do_not_dispatch_mutations_renderer_or_storage(db, monkeypatch):
    session, (a, _) = db
    from backend.app.document import service
    def forbidden(*args, **kwargs):
        raise AssertionError("read-only source crossed mutation boundary")
    for method in ("flush", "commit", "add", "delete"):
        monkeypatch.setattr(session, method, forbidden)
    for name in vars(service):
        if "render" in name or "generate" in name:
            monkeypatch.setattr(service, name, forbidden)
    for method in ("read_stream", "write_stream", "move", "copy"):
        monkeypatch.setattr(service.LocalStorageService, method, forbidden)
    statements = []
    def only_select(conn, cursor, statement, params, context, many):
        assert statement.lstrip().upper().startswith("SELECT")
        statements.append(statement)
    event.listen(session.bind, "before_cursor_execute", only_select)
    try:
        bundle = read_qdkt_case_source_bundle(session, case_id=a[0].id)
        draft = read_qdkt_preapproval_case_source(session, case_id=a[0].id)
        ready = inspect_qdkt_case_readiness(session, case_id=a[0].id)
    finally:
        event.remove(session.bind, "before_cursor_execute", only_select)
    assert statements and not bundle.ready_to_render and not draft.ready_to_render and not ready.ready_to_render
    assert not bundle.decision.legal_issuance_verified
    with pytest.raises(QdKtCaseSourceBlocked, match="TYPE_INVALID"):
        require_qdkt_preapproval_case_source(case_id=a[0].id, site=bundle.site, proposed_team=bundle)


@pytest.mark.parametrize("target,change", [
    ("bundle", {"ready_to_render": True}),
    ("draft", {"ready_to_render": True}),
    ("draft", {"process": "EXISTING_APPROVED_DECISION_REFERENCE"}),
    ("readiness", {"ready_to_render": True}),
])
def test_constructed_results_cannot_claim_activation_or_process_conversion(db, target, change):
    session, (a, _) = db
    factory = {"bundle": read_qdkt_case_source_bundle, "draft": read_qdkt_preapproval_case_source, "readiness": inspect_qdkt_case_readiness}[target]
    result = factory(session, case_id=a[0].id)
    with pytest.raises(ValueError):
        replace(result, **change)


@pytest.mark.parametrize("rows", [
    [D1, replace(D2, ordinal=1)],
    [replace(D1, ordinal=2), replace(D2, ordinal=1)],
    [D1, replace(D2, related_decision_id=D3.id), D3],
    [D1, replace(D2, relation_type="AMENDS")],
    [D1, replace(D2, relation_type="SUPPLEMENTS")],
    [D1, replace(D2, decision_on=None)],
    [D1, replace(D2, ordinal=None)],
])
def test_additional_unsupported_or_contradictory_histories_stay_blocked(rows):
    with pytest.raises(QdKtDecisionSourceBlocked):
        require_latest_qdkt_reference(rows)


def test_unbound_pure_chain_cannot_be_promoted_into_case_bundle(db):
    session, (a, _) = db
    unbound = require_latest_qdkt_reference([D1])
    assert unbound.case_id is None and unbound.inspection_plan_id is None
    with pytest.raises(QdKtCaseSourceBlocked, match="IDENTITY_MISMATCH"):
        require_qdkt_case_source_bundle(case_id=a[0].id, decision=unbound,
            site=read_qdkt_registered_site(session, case_id=a[0].id), team=read_qdkt_team_source(session, case_id=a[0].id))


def test_bundle_does_not_execute_foreign_scope_comparison(db):
    session, (a, _) = db
    bundle = read_qdkt_case_source_bundle(session, case_id=a[0].id)
    class ForeignScope(str):
        def __ne__(self, other):
            raise AssertionError("foreign scope comparison invoked")
    with pytest.raises(QdKtCaseSourceBlocked):
        require_qdkt_case_source_bundle(case_id=a[0].id,
            decision=replace(bundle.decision, case_id=ForeignScope(a[0].id)), site=bundle.site, team=bundle.team)


def test_readiness_template_check_uses_persisted_case_gxp(db):
    session, (a, _) = db
    a[0].gxp_type = "GDP"  # Unsaved input, not the persisted GMP source.
    result = inspect_qdkt_case_readiness(session, case_id=a[0].id)
    assert "QDKT_CASE_GXP_TEMPLATE_CONTRACT_UNVERIFIED" not in result.blockers
    assert a[0].gxp_type == "GDP" and a[0] in session.dirty
