"""Isolated append-only GMP coverage evidence ledger.

DISABLED for application runtime: table is deliberately *not* imported into
global Base.metadata and has no Alembic revision. Only disposable tests may
create it explicitly. No reviewer authority is inferred from payload content.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json

from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, String, Table, Text, UniqueConstraint, select
from sqlalchemy.orm import Session

from backend.app.services.gmp_coverage_bundle import ReviewedCoverageBundle
from backend.app.services.gmp_coverage_persistence_preflight import prepare_coverage_persistence


ledger_metadata = MetaData()
coverage_evidence_ledger = Table(
    "gmp_coverage_evidence_ledger",
    ledger_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("certificate_version_id", String(36), nullable=False),
    Column("payload_sha256", String(64), nullable=False),
    Column("payload_json", Text, nullable=False),
    Column("recorded_by", String(128), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("certificate_version_id", "payload_sha256", name="uq_gmp_coverage_ledger_version_digest"),
)


@dataclass(frozen=True)
class StoredCoverageEvidence:
    id: int
    certificate_version_id: str
    payload_sha256: str
    recorded_by: str


def append_reviewed_evidence(
    session: Session,
    *,
    bundle: ReviewedCoverageBundle,
    actor_id: str,
) -> StoredCoverageEvidence:
    """Append once in caller transaction; caller supplies authenticated actor.

    This is a persistence primitive, NOT an authenticated approval endpoint.
    It cannot authorize Case links. Flush only; caller controls commit/rollback.
    """
    if not actor_id.strip():
        raise ValueError("Actor identity required.")
    preflight = prepare_coverage_persistence(bundle)
    # Capture the evidence exactly as supplied; no magic reconciliation.
    payload = {
        "schema": "gmp-coverage-ledger-v1",
        "certificate_version_id": bundle.certificate_version_id,
        "coverage": [
            {
                "site_id": e.site_id, "source_snapshot_sha256": e.source_snapshot_sha256,
                "source_document_sha256": e.source_document_sha256,
                "source_page_reference": e.source_page_reference,
                "decision": e.decision.value, "reviewer_id": e.reviewer_id,
                "reviewed_at_iso": e.reviewed_at_iso, "rationale": e.rationale,
            }
            for e in sorted(bundle.coverage, key=lambda e: e.site_id)
        ],
        "links": [
            {
                "case_id": e.case_id, "site_id": e.site_id, "gxp_type": e.gxp_type,
                "case_link_decision": e.case_link_decision.value,
                "reviewer_id": e.reviewer_id, "reviewed_at_iso": e.reviewed_at_iso,
            }
            for e in sorted(bundle.links, key=lambda e: e.case_id)
        ],
        "preflight_digest": preflight.canonical_payload_sha256,
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = sha256(text.encode("utf-8")).hexdigest()
    result = session.execute(
        coverage_evidence_ledger.insert().values(
            certificate_version_id=bundle.certificate_version_id,
            payload_sha256=digest,
            payload_json=text,
            recorded_by=actor_id,
            recorded_at=datetime.now(timezone.utc),
        )
    )
    return StoredCoverageEvidence(
        id=result.inserted_primary_key[0],
        certificate_version_id=bundle.certificate_version_id,
        payload_sha256=digest,
        recorded_by=actor_id,
    )


def read_ledger_entries(session: Session, *, certificate_version_id: str) -> tuple[StoredCoverageEvidence, ...]:
    rows = session.execute(
        select(
            coverage_evidence_ledger.c.id,
            coverage_evidence_ledger.c.certificate_version_id,
            coverage_evidence_ledger.c.payload_sha256,
            coverage_evidence_ledger.c.recorded_by,
        ).where(coverage_evidence_ledger.c.certificate_version_id == certificate_version_id)
        .order_by(coverage_evidence_ledger.c.id)
    )
    return tuple(StoredCoverageEvidence(*row) for row in rows)
