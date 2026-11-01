"""Disposable transactional evidence ledger prototype; no runtime/importer authorization."""
from dataclasses import replace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.services.gmp_coverage_evidence import CoveredSiteEvidence, LinkedCaseEvidence, ReviewDecision
from backend.app.services.gmp_coverage_bundle import ReviewedCoverageBundle
from backend.app.services.gmp_coverage_evidence_ledger import (
    ledger_metadata, append_reviewed_evidence, read_ledger_entries,
)


def reviewed():
    site = CoveredSiteEvidence(
        certificate_version_id="version-a", site_id="site-b",
        source_snapshot_sha256="a" * 64, source_document_sha256="b" * 64,
        source_page_reference="p2", decision=ReviewDecision.VERIFIED,
        reviewer_id="reviewer-1", reviewed_at_iso="2026-11-01T09:00:00+07:00",
        rationale="Reviewed source",
    )
    link = LinkedCaseEvidence(
        certificate_version_id="version-a", case_id="case-1", site_id="site-b",
        gxp_type="GMP", coverage=site, case_link_decision=ReviewDecision.VERIFIED,
        reviewer_id="reviewer-2", reviewed_at_iso="2026-11-01T10:00:00+07:00",
    )
    return ReviewedCoverageBundle("version-a", (site,), (link,))


def test_ledger_commit_and_version_scoped_readback():
    engine = create_engine("sqlite:///:memory:", future=True)
    ledger_metadata.create_all(engine)
    try:
        with Session(engine) as s:
            row = append_reviewed_evidence(s, bundle=reviewed(), actor_id="operator-1")
            assert len(row.payload_sha256) == 64
            s.commit()
        with Session(engine) as s:
            assert read_ledger_entries(s, certificate_version_id="version-a") == (row,)
            assert read_ledger_entries(s, certificate_version_id="version-b") == ()
    finally:
        engine.dispose()


def test_ledger_rollback_does_not_leak_entry():
    engine = create_engine("sqlite:///:memory:", future=True)
    ledger_metadata.create_all(engine)
    try:
        with Session(engine) as s:
            append_reviewed_evidence(s, bundle=reviewed(), actor_id="operator-1")
            s.rollback()
        with Session(engine) as s:
            assert read_ledger_entries(s, certificate_version_id="version-a") == ()
    finally:
        engine.dispose()


def test_ledger_duplicate_digest_fails_closed():
    engine = create_engine("sqlite:///:memory:", future=True)
    ledger_metadata.create_all(engine)
    try:
        with Session(engine) as s:
            append_reviewed_evidence(s, bundle=reviewed(), actor_id="operator-1")
            s.commit()
        with Session(engine) as s:
            with pytest.raises(IntegrityError):
                append_reviewed_evidence(s, bundle=reviewed(), actor_id="operator-2")
            s.rollback()
        with Session(engine) as s:
            assert len(read_ledger_entries(s, certificate_version_id="version-a")) == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize("actor", ["", "   "])
def test_ledger_never_accepts_blank_actor(actor):
    engine = create_engine("sqlite:///:memory:", future=True)
    ledger_metadata.create_all(engine)
    try:
        with Session(engine) as s:
            with pytest.raises(ValueError, match="Actor identity"):
                append_reviewed_evidence(s, bundle=reviewed(), actor_id=actor)
    finally:
        engine.dispose()


def test_ledger_unverified_case_cannot_be_written():
    engine = create_engine("sqlite:///:memory:", future=True)
    ledger_metadata.create_all(engine)
    try:
        b = reviewed()
        b = replace(b, links=(replace(b.links[0], case_link_decision=ReviewDecision.UNRESOLVED),))
        with Session(engine) as s:
            with pytest.raises(ValueError):
                append_reviewed_evidence(s, bundle=b, actor_id="operator-1")
            assert read_ledger_entries(s, certificate_version_id="version-a") == ()
    finally:
        engine.dispose()
