"""Internal decision-owned roster staging; no HTTP route and no legal issuance.

The caller must have independently verified external approval and document.write
authorization. No commit or storage action occurs here.
"""
from __future__ import annotations

import hashlib
import json
from sqlalchemy import select

from backend.app.db.enums import AuditActorType
from backend.app.db.models.phase1 import (
    AuditEvent, InspectionDecision, InspectionPlan, QdKtDraftRosterSnapshot,
    QdKtDraftRosterMember, QdKtIssuedRoster, QdKtIssuedRosterMember,
)
from backend.app.document.inspection_qd_kt_issued_team_choice import IssuedTeamChoice
from backend.app.document.inspection_qd_kt_team_snapshot_review import (
    DraftTeamSnapshot, TeamMemberAtDraft, review_issued_team, validate_members,
)


class QdKtIssuedRosterWriteBlocked(ValueError):
    pass


def _digest(members: tuple[TeamMemberAtDraft, ...]) -> str:
    payload = [
        {"position": i, "source_member_id": m.inspector_id,
         "display_name": m.display_name, "role_code": m.role, "job_title": m.job_title}
        for i, m in enumerate(members, 1)
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def stage_qdkt_issued_roster(session, *, decision_id: str, choice: IssuedTeamChoice,
                             final_members: tuple[TeamMemberAtDraft, ...],
                             actor_user_id: str):
    """Stage confirmed display roster + audit in one caller-owned transaction.

    Approval evidence, user permission, and externally signed document are not
    represented by these inputs. Do not expose as a writable endpoint until
    an authorized workflow supplies those independent proofs.
    """
    if not isinstance(decision_id, str) or not decision_id.strip():
        raise QdKtIssuedRosterWriteBlocked("QDKT_DECISION_ID_REQUIRED")
    if not isinstance(actor_user_id, str) or not actor_user_id.strip():
        raise QdKtIssuedRosterWriteBlocked("QDKT_CONFIRMING_ACTOR_REQUIRED")
    validate_members(final_members)
    decision = session.scalar(select(InspectionDecision).where(
        InspectionDecision.id == decision_id).with_for_update())
    if decision is None:
        raise QdKtIssuedRosterWriteBlocked("QDKT_DECISION_NOT_FOUND")
    plan = session.scalar(select(InspectionPlan).where(
        InspectionPlan.id == decision.inspection_plan_id).with_for_update())
    if plan is None or choice.case_id != plan.case_id:
        raise QdKtIssuedRosterWriteBlocked("QDKT_DECISION_CASE_MISMATCH")
    if choice.decision_reference != decision.reference or choice.issued_on != decision.decision_on:
        raise QdKtIssuedRosterWriteBlocked("QDKT_DECISION_METADATA_MISMATCH")

    snapshot_row = None
    draft = None
    if choice.roster_source != "USER_ENTERED":
        snapshot_row = session.scalar(select(QdKtDraftRosterSnapshot).where(
            QdKtDraftRosterSnapshot.case_id == plan.case_id,
            QdKtDraftRosterSnapshot.draft_id == choice.draft_id))
        if snapshot_row is None:
            raise QdKtIssuedRosterWriteBlocked("QDKT_DRAFT_SNAPSHOT_NOT_FOUND")
        draft_rows = session.scalars(select(QdKtDraftRosterMember).where(
            QdKtDraftRosterMember.snapshot_id == snapshot_row.id)
            .order_by(QdKtDraftRosterMember.position)).all()
        if not draft_rows or tuple(row.position for row in draft_rows) != tuple(range(1, len(draft_rows) + 1)):
            raise QdKtIssuedRosterWriteBlocked("QDKT_DRAFT_SNAPSHOT_ORDER_INVALID")
        draft = DraftTeamSnapshot(
            case_id=snapshot_row.case_id, draft_id=snapshot_row.draft_id,
            document_version_id=snapshot_row.document_version_id,
            team_id=snapshot_row.source_team_id,
            team_revision=snapshot_row.source_team_revision,
            members=tuple(TeamMemberAtDraft(
                row.source_team_member_id, row.display_name, row.role_code,
                row.job_title) for row in draft_rows),
        )
    review_issued_team(choice=choice, final_members=final_members, draft_snapshot=draft)
    digest = _digest(final_members)
    existing = session.scalar(select(QdKtIssuedRoster).where(
        QdKtIssuedRoster.inspection_decision_id == decision_id).with_for_update())
    if existing is not None:
        members = session.scalars(select(QdKtIssuedRosterMember).where(
            QdKtIssuedRosterMember.issued_roster_id == existing.id)
            .order_by(QdKtIssuedRosterMember.position)).all()
        if (existing.roster_source != choice.roster_source
            or existing.source_draft_snapshot_id != (snapshot_row.id if snapshot_row else None)
            or existing.confirmed_by_user_id != actor_user_id
            or existing.roster_sha256 != digest
            or len(members) != len(final_members)
            or any((row.position, row.source_member_id, row.display_name, row.role_code, row.job_title)
                   != (i, m.inspector_id, m.display_name, m.role, m.job_title)
                   for i, (row, m) in enumerate(zip(members, final_members), 1))):
            raise QdKtIssuedRosterWriteBlocked("QDKT_ISSUED_ROSTER_ALREADY_BOUND")
        return existing

    roster = QdKtIssuedRoster(
        inspection_decision_id=decision_id, roster_source=choice.roster_source,
        source_draft_snapshot_id=snapshot_row.id if snapshot_row else None,
        confirmed_by_user_id=actor_user_id, roster_sha256=digest)
    session.add(roster)
    session.flush()
    for i, member in enumerate(final_members, 1):
        session.add(QdKtIssuedRosterMember(
            issued_roster_id=roster.id, position=i,
            source_member_id=member.inspector_id, display_name=member.display_name,
            role_code=member.role, job_title=member.job_title))
    session.add(AuditEvent(
        actor_type=AuditActorType.USER, actor_user_id=actor_user_id,
        action="QDKT_ISSUED_ROSTER_CONFIRMED",
        entity_type="qdkt_issued_roster", entity_id=roster.id,
        new_values_json=json.dumps({
            "inspection_decision_id": decision_id, "case_id": plan.case_id,
            "roster_source": choice.roster_source, "roster_sha256": digest,
            "source_draft_snapshot_id": snapshot_row.id if snapshot_row else None,
        }, sort_keys=True),
    ))
    return roster
