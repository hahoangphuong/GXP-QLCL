"""Offline Case source composition; no database, rendering or storage writes."""
from datetime import date
from types import SimpleNamespace

import pytest

from backend.app.document.inspection_qd_kt_case_source_bundle import (
    QdKtCaseSourceBlocked, require_qdkt_case_source_bundle,
)
from backend.app.document.inspection_qd_kt_decision_source import QdKtDecisionAtoms
from backend.app.document.inspection_qd_kt_registered_site import QdKtRegisteredSite
from backend.app.document.inspection_qd_kt_team_source import (
    QdKtTeamMemberSource, QdKtTeamSource,
)


def _sources(*, site_case="c1", team_case="c1", mapped=False):
    decision = QdKtDecisionAtoms(
        source_decision_id="decision1", reference="QD-123",
        decision_on=date(2026, 10, 1), legacy_raw="raw",
        case_id="c1", inspection_plan_id="plan1",
    )
    site = QdKtRegisteredSite(
        case_id=site_case, site_id="site1", registered_address="123 Street", province_name="Hà Nội",
    )
    member = QdKtTeamMemberSource(
        id="member1", sort_order=0, role_code="LEADER", display_name="A",
        identity_kind="INSPECTOR_PROFILE", inspector_profile_id="inspector1",
        person_id=None, participant_catalog_id=None,
    )
    team = QdKtTeamSource(
        case_id=team_case, team_id="team1", members=(member,),
        bookmark_mapping_verified=mapped,
    )
    return decision, site, team


def test_matching_sources_remain_unrenderable():
    decision, site, team = _sources()
    bundle = require_qdkt_case_source_bundle(case_id="c1", decision=decision, site=site, team=team)
    assert bundle.decision.source_decision_id == "decision1"
    assert bundle.site.registered_address == "123 Street"
    assert bundle.team.members[0].role_code == "LEADER"
    assert bundle.team_display_equivalence_verified is False
    assert bundle.location_render_format_verified is False
    assert bundle.ready_to_render is False


@pytest.mark.parametrize("site_case,team_case", [
    ("c2", "c1"), ("c1", "c2"), ("c2", "c2"),
])
def test_cross_case_sources_blocked(site_case, team_case):
    decision, site, team = _sources(site_case=site_case, team_case=team_case)
    with pytest.raises(QdKtCaseSourceBlocked, match="QDKT_CASE_SOURCE_IDENTITY_MISMATCH"):
        require_qdkt_case_source_bundle(case_id="c1", decision=decision, site=site, team=team)


def test_unreviewed_mapping_flag_never_authorizes_rendering():
    decision, site, team = _sources(mapped=True)
    with pytest.raises(QdKtCaseSourceBlocked, match="QDKT_TEAM_CONTRACT_UNSUPPORTED"):
        require_qdkt_case_source_bundle(case_id="c1", decision=decision, site=site, team=team)


@pytest.mark.parametrize("field,value", [
    ("reference", " QD-123"),
    ("reference", ""),
    ("decision_on", None),
    ("decision_on", "2026-10-01"),
    ("legacy_raw", "   "),
])
def test_forged_decision_atoms_cannot_bypass_bundle_validation(field, value):
    from dataclasses import replace
    decision, site, team = _sources()
    with pytest.raises(QdKtCaseSourceBlocked, match="QDKT_DECISION_SOURCE_INCOMPLETE"):
        require_qdkt_case_source_bundle(
            case_id="c1", decision=replace(decision, **{field: value}),
            site=site, team=team,
        )


@pytest.mark.parametrize("field,value,code", [
    ("registered_address", " 123 Street", "REGISTERED_SITE_ADDRESS_UNNORMALIZED"),
    ("registered_address", "", "REGISTERED_SITE_ADDRESS_MISSING"),
    ("site_id", "", "QDKT_SOURCE_IDENTITY_MISSING"),
])
def test_forged_site_atoms_cannot_bypass_bundle_validation(field, value, code):
    from dataclasses import replace
    decision, site, team = _sources()
    with pytest.raises(QdKtCaseSourceBlocked, match=code):
        require_qdkt_case_source_bundle(
            case_id="c1", decision=decision, site=replace(site, **{field: value}),
            team=team,
        )


@pytest.mark.parametrize("field,value,code", [
    ("role_code", "DIRECTOR", "INSPECTION_TEAM_ROLE_UNPROVEN"),
    ("sort_order", -1, "INSPECTION_TEAM_ORDER_AMBIGUOUS"),
    ("display_name", "  A", "INSPECTION_TEAM_DISPLAY_NAME_UNPROVEN"),
    ("identity_kind", "UNKNOWN", "INSPECTION_TEAM_IDENTITY_UNPROVEN"),
])
def test_forged_team_atoms_cannot_bypass_bundle_validation(field, value, code):
    from dataclasses import replace
    decision, site, team = _sources()
    team = replace(team, members=(replace(team.members[0], **{field: value}),))
    with pytest.raises(QdKtCaseSourceBlocked, match=code):
        require_qdkt_case_source_bundle(
            case_id="c1", decision=decision, site=site, team=team,
        )


def test_missing_decision_identity_is_rejected_before_value_contract():
    from dataclasses import replace
    decision, site, team = _sources()
    with pytest.raises(QdKtCaseSourceBlocked, match="QDKT_SOURCE_IDENTITY_MISSING"):
        require_qdkt_case_source_bundle(
            case_id="c1", decision=replace(decision, source_decision_id=""),
            site=site, team=team,
        )
