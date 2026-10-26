"""Evidence replay must not silently trust stale/altered observation records."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.document import inspection_qd_kt_observation_replay as replay
from backend.app.document.inspection_qd_kt_dotx_binary_audit import QdKtDotxAuditBlocked


def _fixture():
    return json.loads(replay.OBSERVED_PATH.read_text(encoding="utf-8"))


def _measured(evidence):
    return tuple(
        SimpleNamespace(
            gxp_type=row["gxp_type"], actual_sha256=row["sha256"],
            bookmark_count=row["bookmark_count"],
            bookmark_names=tuple(row["bookmark_names"]),
        )
        for row in sorted(evidence["templates"], key=lambda item: item["gxp_type"])
    )


def _run(tmp_path, monkeypatch, mutate=None, mutate_measured=None):
    evidence = _fixture()
    if mutate:
        mutate(evidence)
    measured = _measured(_fixture())
    if mutate_measured:
        measured = mutate_measured(measured)
    path = tmp_path / "observed.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(replay, "inspect_supplied_qdkt_dotx_set", lambda directory: measured)
    return replay.require_matching_qdkt_binary_observations(tmp_path, evidence_path=path)


def test_exact_supplied_file_observations_can_be_replayed(tmp_path, monkeypatch):
    assert _run(tmp_path, monkeypatch) == ("GLP", "GMP", "GMPbb", "GSP")


@pytest.mark.parametrize("modify", [
    lambda e: e["templates"][0].update(sha256="0" * 64),
    lambda e: e["templates"][0].update(bookmark_count=23),
    lambda e: e["templates"][0]["bookmark_names"].append("Fake"),
    lambda e: e["templates"][0].update(bookmark_owner_parity_verified=True),
    lambda e: e["templates"][0].update(ready_to_render=True),
])
def test_changed_evidence_fails_closed(tmp_path, monkeypatch, modify):
    with pytest.raises(QdKtDotxAuditBlocked, match="QDKT_OBSERVED_TEMPLATE_DRIFT"):
        _run(tmp_path, monkeypatch, mutate=modify)


def test_renamed_actual_physical_bookmark_fails_closed(tmp_path, monkeypatch):
    def changed(measured):
        rows = list(measured)
        rows[0] = SimpleNamespace(**{**vars(rows[0]), "bookmark_names": ("changed",)})
        return tuple(rows)
    with pytest.raises(QdKtDotxAuditBlocked, match="QDKT_OBSERVED_TEMPLATE_DRIFT"):
        _run(tmp_path, monkeypatch, mutate_measured=changed)


def test_incomplete_or_promoted_manifest_fails_closed(tmp_path, monkeypatch):
    with pytest.raises(QdKtDotxAuditBlocked, match="QDKT_OBSERVATION_EVIDENCE_UNVERIFIED"):
        _run(tmp_path, monkeypatch, mutate=lambda e: e.update(ready_to_render=True))
    with pytest.raises(QdKtDotxAuditBlocked, match="QDKT_OBSERVATION_EVIDENCE_UNVERIFIED"):
        _run(tmp_path, monkeypatch, mutate=lambda e: e["templates"].pop())


def test_absent_evidence_file_fails_closed(tmp_path):
    with pytest.raises(QdKtDotxAuditBlocked, match="QDKT_OBSERVATION_EVIDENCE_UNAVAILABLE"):
        replay.require_matching_qdkt_binary_observations(tmp_path, evidence_path=tmp_path / "missing.json")
