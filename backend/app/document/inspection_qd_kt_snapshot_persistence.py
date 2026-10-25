"""Internal QĐKT draft snapshot persistence; no public route or issuance.

Caller owns a single transaction, RBAC, and independent proof of rendered
DOCX content. This function never commits, never writes storage, and never
converts a draft into an approved decision.
"""
from __future__ import annotations

from hashlib import sha256
import json
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.db.models.phase1 import (
    InspectionTeam, InspectionTeamMember, QdKtDraftRosterMember,
    QdKtDraftRosterSnapshot, AuditEvent,
)
from backend.app.db.enums import AuditActorType
from backend.app.document.inspection_qd_kt_draft_version_binding import (
    require_qdkt_draft_version_binding,
)
from backend.app.document.inspection_qd_kt_team_snapshot_review import (
    DraftTeamSnapshot, validate_draft_snapshot,
)


class QdKtSnapshotWriteBlocked(ValueError):
    pass


def canonical_roster_sha256(snapshot: DraftTeamSnapshot) -> str:
    validate_draft_snapshot(snapshot)
    data = [
        {"source_team_member_id": m.inspector_id, "position": i,
         "display_name": m.display_name, "role_code": m.role,
         "job_title": m.job_title}
        for i, m in enumerate(snapshot.members, 1)
    ]
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def stage_qdkt_draft_snapshot(
    session, *, snapshot: DraftTeamSnapshot, actor_user_id: str,
    rendered_roster_sha256: str, expected_docx_sha256: str,
):
    """Stage rows and audit in caller transaction; never commit.

    This is intentionally an internal service boundary: a trusted renderer
    must produce rendered_roster_sha256, not the browser. The caller must
    enforce document.write authorization and commit only after the DOCX
    storage operation is durably finalized and verified.
    """
    if not actor_user_id or not actor_user_id.strip():
        raise QdKtSnapshotWriteBlocked("QDKT_SNAPSHOT_ACTOR_REQUIRED")
    digest = canonical_roster_sha256(snapshot)
    if rendered_roster_sha256 != digest:
        raise QdKtSnapshotWriteBlocked("QDKT_RENDERED_ROSTER_DIGEST_MISMATCH")
    # Lock team before checking revision and members to close the concurrent
    # edit gap. This is PostgreSQL row locking; do not use SQLite as evidence.
    team = session.scalar(
        select(InspectionTeam).where(
            InspectionTeam.id == snapshot.team_id,
            InspectionTeam.case_id == snapshot.case_id,
        ).with_for_update()
    )
    if team is None or team.row_version != snapshot.team_revision:
        raise QdKtSnapshotWriteBlocked("QDKT_DRAFT_TEAM_STALE")
    binding = require_qdkt_draft_version_binding(session, snapshot=snapshot)
    if expected_docx_sha256 != binding.stored_checksum_sha256:
        raise QdKtSnapshotWriteBlocked("QDKT_DRAFT_BINARY_CHECKSUM_CHANGED")
    rows = session.scalars(
        select(InspectionTeamMember)
        .where(InspectionTeamMember.team_id == snapshot.team_id)
        .order_by(InspectionTeamMember.sort_order, InspectionTeamMember.id)
    ).all()
    if tuple(row.id for row in rows) != tuple(m.inspector_id for m in snapshot.members):
        raise QdKtSnapshotWriteBlocked("QDKT_DRAFT_TEAM_MEMBERS_STALE")
    if any(row.display_name != member.display_name or row.role_code != member.role
           for row, member in zip(rows, snapshot.members)):
        raise QdKtSnapshotWriteBlocked("QDKT_DRAFT_TEAM_DISPLAY_STALE")
    existing = session.scalar(
        select(QdKtDraftRosterSnapshot)
        .where(QdKtDraftRosterSnapshot.document_version_id == snapshot.document_version_id)
        .with_for_update()
    )
    if existing is not None:
        # Fail closed even when the digest matches: caller cannot claim
        # idempotency without comparing persisted member rows as well.
        persisted = session.scalars(
            select(QdKtDraftRosterMember)
            .where(QdKtDraftRosterMember.snapshot_id == existing.id)
            .order_by(QdKtDraftRosterMember.position)
        ).all()
        same = (
            existing.case_id == snapshot.case_id
            and existing.draft_id == snapshot.draft_id
            and existing.source_team_id == snapshot.team_id
            and existing.source_team_revision == snapshot.team_revision
            and existing.roster_sha256 == digest
            and len(persisted) == len(snapshot.members)
            and all(
                (p.source_team_member_id, p.position, p.display_name, p.role_code, p.job_title)
                == (m.inspector_id, i, m.display_name, m.role, m.job_title)
                for i, (p, m) in enumerate(zip(persisted, snapshot.members), 1)
            )
        )
        if not same:
            raise QdKtSnapshotWriteBlocked("QDKT_DRAFT_SNAPSHOT_ALREADY_BOUND")
        return existing
    record = QdKtDraftRosterSnapshot(
        case_id=snapshot.case_id, draft_id=snapshot.draft_id,
        document_version_id=snapshot.document_version_id,
        source_team_id=snapshot.team_id, source_team_revision=snapshot.team_revision,
        roster_sha256=digest,
    )
    session.add(record)
    session.flush()
    for i, member in enumerate(snapshot.members, 1):
        session.add(QdKtDraftRosterMember(
            snapshot_id=record.id, source_team_member_id=member.inspector_id,
            position=i, display_name=member.display_name,
            role_code=member.role, job_title=member.job_title,
        ))
    session.add(AuditEvent(
        actor_type=AuditActorType.USER, actor_user_id=actor_user_id,
        action="QDKT_DRAFT_ROSTER_SNAPSHOT_CREATED",
        entity_type="qdkt_draft_roster_snapshot", entity_id=record.id,
        new_values_json=json.dumps({
            "case_id":snapshot.case_id,
            "draft_id":snapshot.draft_id,
            "document_version_id":snapshot.document_version_id,
            "roster_sha256":digest,
        },sort_keys=True),
    ))
    # Caller may flush/commit; database constraints forbid duplicate version
    # under concurrent writers. Do not swallow IntegrityError.
    return record
