"""Real Case team owner, QĐKT current-team and draft readiness integration.

A current Case team is not an approved QĐKT roster or a legally issued decision.
This suite uses a private Alembic-migrated PostgreSQL schema and real HTTP.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    AuditEvent, Case, Document, InspectionTeam, InspectionTeamMember,
    InspectionTeamParticipantCatalog, InspectorProfile, Person,
)
from test_canonical_http_workflow_postgres import api, ok
from test_canonical_workflow_postgres import pg_engine
from test_catalog_qdkt_readiness_http_postgres import (
    _create_catalog_case, _readiness,
)


def test_new_case_team_canonical_http_never_becomes_issued_qdkt(pg_engine, api):
    """Persist a real operator team and prove Process A reads it without issuance."""
    _, site_id, line_id, case_id = _create_catalog_case(api)
    route = f"/cases/{case_id}/documents/inspection-qd-kt/current-team"
    status, _ = api("GET", route)
    assert status == 409
    blocked = _readiness(api, case_id, "DRAFT_QDKT")
    assert "CASE_INSPECTION_TEAM_NOT_UNIQUE" in blocked["blocked_reasons"]
    assert blocked["ready_to_render"] is False

    # Catalog actors are test fixtures; the team write itself is a real
    # authorized PUT into the canonical Case-owned aggregate.
    with Session(pg_engine) as db:
        inspector = Person(full_name="Synthetic Inspector", display_name="Inspector A")
        db.add(inspector)
        db.flush()
        profile = InspectorProfile(person_id=inspector.id)
        representative = InspectionTeamParticipantCatalog(
            code="SYNTH-QDKT-" + case_id[:10],
            participant_kind="ORGANIZATION_REPRESENTATIVE",
            display_name="Synthetic Organization Representative",
            organization_name="Synthetic company",
        )
        db.add_all([profile, representative])
        db.commit()
        profile_id, catalog_id = profile.id, representative.id

    members = [
        {
            "identity_kind": "INSPECTOR_PROFILE",
            "inspector_profile_id": profile_id,
            "role_code": "LEADER", "sort_order": 1,
        },
        {
            "identity_kind": "ORGANIZATION_REPRESENTATIVE",
            "participant_catalog_id": catalog_id,
            "role_code": "MEMBER", "sort_order": 2,
        },
    ]
    status, _ = api("PUT", f"/cases/{case_id}/team", {
        "members": members,
    }, role="reader")
    assert status == 403
    before = _readiness(api, case_id, "DRAFT_QDKT")
    created = ok(api, "PUT", f"/cases/{case_id}/team", {
        "members": members,
        "reason": "Explicit synthetic operator team",
    })
    assert created["case_id"] == case_id
    assert len(created["members"]) == 2
    assert created["row_version"] >= 2
    team_id = created["team_id"]
    view = ok(api, "GET", route)
    assert view["case_id"] == case_id and view["team_id"] == team_id
    assert view["team_revision"] == created["row_version"]
    assert [row["role_code"] for row in view["members"]] == ["LEADER", "MEMBER"]
    assert [row["sort_order"] for row in view["members"]] == [1, 2]
    assert [row["display_name"] for row in view["members"]] == [
        "Inspector A", "Synthetic Organization Representative",
    ]
    assert view["source_kind"] == "CURRENT_CASE_TEAM"
    assert view["draft_snapshot_available"] is False
    assert view["issued_team_confirmed"] is False
    after = _readiness(api, case_id, "DRAFT_QDKT")
    assert "CASE_INSPECTION_TEAM_NOT_UNIQUE" not in after["blocked_reasons"]
    assert "QDKT_TYPED_RENDER_CONTRACT_MISSING" in after["blocked_reasons"]
    assert after["decision_source_id"] is None
    assert after["ready_to_render"] is False
    reference = _readiness(api, case_id)
    assert reference["decision_source_id"] is None
    assert "QDKT_LEGAL_ISSUANCE_EVIDENCE_UNPROVEN" in reference["blocked_reasons"]

    with Session(pg_engine) as db:
        row = db.get(Case, case_id)
        assert row.site_id == site_id and row.production_line_id == line_id
        assert db.scalar(select(func.count()).select_from(Document)
                         .where(Document.case_id == case_id)) == 0
        assert db.scalar(select(func.count()).select_from(InspectionTeam)
                         .where(InspectionTeam.case_id == case_id)) == 1
        assert db.scalar(select(func.count()).select_from(InspectionTeamMember)
                         .where(InspectionTeamMember.team_id == team_id)) == 2
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.entity_id == team_id,
            AuditEvent.action == "inspection_team.upsert",
        )) == 1

    # The caller must carry the aggregate's current row_version; no implicit
    # replacement or new roster after a failed ambiguous POST.
    with Session(pg_engine) as db:
        before_audit = db.scalar(select(func.count()).select_from(AuditEvent)
                                 .where(AuditEvent.entity_id == team_id))
    status, _ = api("PUT", f"/cases/{case_id}/team", {"members": members})
    assert status == 409
    status, _ = api("PUT", f"/cases/{case_id}/team", {
        "members": members, "expected_version": created["row_version"] + 1,
    })
    assert status == 409
    status, _ = api("PUT", f"/cases/{case_id}/team", {
        "members": members, "expected_version": created["row_version"],
        "display_text": "Client cannot invent issued roster",
    })
    assert status == 422
    assert ok(api, "GET", route) == view
    with Session(pg_engine) as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent)
                         .where(AuditEvent.entity_id == team_id)) == before_audit


def test_qdkt_current_team_cannot_borrow_another_case_team(pg_engine, api):
    """Distinct Case UUIDs remain distinct even on the same physical Site."""
    _, _, _, case_a = _create_catalog_case(api)
    _, _, _, case_b = _create_catalog_case(api)
    with Session(pg_engine) as db:
        owner_b = InspectionTeam(case_id=case_b)
        db.add(owner_b)
        db.flush()
        db.add(InspectionTeamMember(
            team_id=owner_b.id, role_code="LEADER", sort_order=0,
            identity_kind="LEGACY_PERSON", display_name="Synthetic Legacy B",
        ))
        db.commit()
    status, _ = api(
        "GET", f"/cases/{case_a}/documents/inspection-qd-kt/current-team",
    )
    assert status == 409
    other = ok(api, "GET", f"/cases/{case_b}/documents/inspection-qd-kt/current-team")
    assert other["case_id"] == case_b
    assert other["members"][0]["display_name"] == "Synthetic Legacy B"
    assert other["issued_team_confirmed"] is False
    blocked = _readiness(api, case_a, "DRAFT_QDKT")
    assert "CASE_INSPECTION_TEAM_NOT_UNIQUE" in blocked["blocked_reasons"]
    assert not blocked["ready_to_render"]
