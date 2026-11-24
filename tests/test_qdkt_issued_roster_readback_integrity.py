"""Persisted QĐKT decision-specific roster readback fails closed on drift."""
from __future__ import annotations

import hashlib
import json

import pytest

from backend.app.document.inspection_qd_kt_issued_roster_persistence import (
    QdKtIssuedRosterReadBlocked, require_qdkt_issued_roster_readback_integrity,
)


def members():
    return (
        (1, "source-member-1", "Official Leader", "LEADER", "Inspector"),
        (2, "source-member-2", "Official Secretary", "SECRETARY", "Officer"),
    )


def digest(rows):
    # Independent canonical fixture: position is part of the hash, not just
    # the multiset of names. This is the persisted write-contract algorithm.
    payload = [
        {
            "position": position, "source_member_id": source_id,
            "display_name": name, "role_code": role, "job_title": title,
        }
        for position, source_id, name, role, title in rows
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def test_exact_issued_roster_round_trip_integrity():
    rows = members()
    assert require_qdkt_issued_roster_readback_integrity(
        roster_sha256=digest(rows), members=rows,
    ) is None


@pytest.mark.parametrize("mutate", [
    lambda x: x[:1] + ((2, x[1][1], "Altered", x[1][3], x[1][4]),),
    lambda x: x[:1] + ((2, x[1][1], x[1][2], "MEMBER", x[1][4]),),
    lambda x: x[:1] + ((2, x[1][1], x[1][2], x[1][3], "Changed title"),),
    lambda x: x[:1],
    lambda x: (),
    lambda x: ((2, *x[0][1:]), x[1]),
    lambda x: (x[0], (2, x[0][1], *x[1][2:])),
    lambda x: ((1, None, *x[0][2:]), x[1]),
])
def test_missing_mutated_or_reordered_roster_cannot_be_read_as_confirmed(mutate):
    good = members()
    with pytest.raises(QdKtIssuedRosterReadBlocked):
        require_qdkt_issued_roster_readback_integrity(
            roster_sha256=digest(good), members=mutate(good),
        )


@pytest.mark.parametrize("bad", [
    "0" * 64, "F" * 64, "g" * 64, "", "0" * 63, None,
])
def test_forged_or_malformed_stored_digest_is_rejected(bad):
    with pytest.raises(QdKtIssuedRosterReadBlocked):
        require_qdkt_issued_roster_readback_integrity(
            roster_sha256=bad, members=members(),
        )


@pytest.mark.parametrize("damage", ["name", "digest", "missing_roster"])
def test_http_readback_rejects_corrupted_persisted_roster(tmp_path, damage):
    """HTTP GET never reports damaged frozen roster as a confirmed source.

    SQLite intentionally has no PostgreSQL append-only trigger, so this can
    simulate historical corruption without touching any real database.
    """
    import asyncio
    from datetime import date
    from uuid import uuid4

    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session
    from backend.app.auth import (
        ROLE_PERMISSIONS, build_authenticated_user, get_authenticated_user,
    )
    from backend.app.db.base import Base
    from backend.app.db.enums import AuditActorType, CaseState
    from backend.app.db.models.phase1 import (
        AppUser, AuditEvent, Case, Company, InspectionDecision,
        InspectionPlan, QdKtIssuedRoster, QdKtIssuedRosterMember, Site,
    )
    from backend.app.main import create_app

    database_url = f"sqlite:///{(tmp_path / 'qdkt-readback.sqlite').as_posix()}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    member_rows = ((1, str(uuid4()), "Confirmed Leader", "LEADER", "Inspector"),)
    with Session(engine) as session:
        company = Company(legal_name="QDKT integrity test company")
        session.add(company); session.flush()
        site = Site(company_id=company.id, site_name="Integrity test site")
        session.add(site); session.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_IN_PROGRESS)
        session.add(case); session.flush()
        plan = InspectionPlan(case_id=case.id)
        session.add(plan); session.flush()
        decision = InspectionDecision(
            inspection_plan_id=plan.id, ordinal=1, reference="R-QDKT",
            decision_on=date(2026, 11, 24), legacy_raw="Unverified signed source transcription",
        )
        actor = AppUser(username="integrity-operator", is_active=True)
        session.add_all((decision, actor)); session.flush()
        roster = QdKtIssuedRoster(
            inspection_decision_id=decision.id, confirmed_by_user_id=actor.id,
            roster_source="USER_ENTERED", roster_sha256=digest(member_rows),
        )
        session.add(roster); session.flush()
        member = QdKtIssuedRosterMember(
            issued_roster_id=roster.id, position=1,
            source_member_id=member_rows[0][1],
            display_name=member_rows[0][2],
            role_code=member_rows[0][3],
            job_title=member_rows[0][4],
        )
        audit = AuditEvent(
            actor_type=AuditActorType.USER, actor_user_id=actor.id,
            entity_type="inspection_decision", entity_id=decision.id,
            action="qdkt_issued_decision.record",
        )
        session.add_all((member, audit))
        session.commit()
        case_id, decision_id, roster_id = case.id, decision.id, roster.id

    app = create_app(database_url)
    user = build_authenticated_user(
        "integrity-operator", "admin", permissions=ROLE_PERMISSIONS["admin"],
    )
    app.dependency_overrides[get_authenticated_user] = lambda: user
    url = f"/cases/{case_id}/qdkt-issued-decisions/{decision_id}"

    async def get():
        outputs = []
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(message):
            outputs.append(message)
        await app({
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "GET", "scheme": "http", "path": url, "raw_path": url.encode(),
            "query_string": b"", "headers": [],
            "client": ("127.0.0.1", 12345), "server": ("localhost", 80),
            "root_path": "",
        }, receive, send)
        status = next(v["status"] for v in outputs if v["type"] == "http.response.start")
        body = b"".join(v.get("body", b"") for v in outputs if v["type"] == "http.response.body")
        return status, json.loads(body)

    status, body = asyncio.run(get())
    assert status == 200, body
    assert body["roster_id"] == roster_id
    assert body["members"][0]["display_name"] == "Confirmed Leader"
    assert body["legal_issuance_verified"] is False
    with Session(engine) as session:
        roster = session.get(QdKtIssuedRoster, roster_id)
        member = session.scalar(select(QdKtIssuedRosterMember).where(
            QdKtIssuedRosterMember.issued_roster_id == roster_id,
        ))
        if damage == "name":
            member.display_name = "Tampered Leader"
        elif damage == "digest":
            roster.roster_sha256 = "0" * 64
        else:
            session.delete(member)
            session.flush()
            session.delete(roster)
        session.commit()
    status, body = asyncio.run(get())
    assert status == 409, body
    assert body["detail"] == (
        "QDKT_ISSUED_ROSTER_MISSING"
        if damage == "missing_roster" else "QDKT_ISSUED_ROSTER_DIGEST_MISMATCH"
    )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.entity_type == "inspection_decision",
            AuditEvent.entity_id == decision_id,
        )) == 1
    engine.dispose()
