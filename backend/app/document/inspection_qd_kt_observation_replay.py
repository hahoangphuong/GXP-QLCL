"""Re-run the four-DOTX observation against supplied local files.

This is an offline evidence comparison, not a renderability or business-owner gate.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.app.document.inspection_qd_kt_dotx_binary_audit import (
    QdKtDotxAuditBlocked,
    inspect_supplied_qdkt_dotx_set,
)

OBSERVED_PATH = Path(__file__).resolve().parents[3] / "tests/fixtures/inspection_qd_kt_observed_template_binaries.json"


def require_matching_qdkt_binary_observations(
    directory: Path, *, evidence_path: Path = OBSERVED_PATH,
) -> tuple[str, ...]:
    """Require exact four-file checksum AND all physical bookmark names.

    Comparing the recorded names to actual XML prevents promoting a historical
    metadata fixture into a claim that newly supplied bytes were inspected.
    """
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QdKtDotxAuditBlocked("QDKT_OBSERVATION_EVIDENCE_UNAVAILABLE") from exc
    if not isinstance(evidence, dict) or evidence.get("schema_version") != "inspection-qd-kt-observed-dotx-binaries/v1":
        raise QdKtDotxAuditBlocked("QDKT_OBSERVATION_EVIDENCE_UNVERIFIED")
    rows = evidence.get("templates")
    if not isinstance(rows, list) or len(rows) != 4 or any(not isinstance(row, dict) for row in rows):
        raise QdKtDotxAuditBlocked("QDKT_OBSERVATION_EVIDENCE_UNVERIFIED")
    by_kind = {row.get("gxp_type"): row for row in rows}
    if len(by_kind) != 4 or set(by_kind) != {"GLP", "GMP", "GMPbb", "GSP"}:
        raise QdKtDotxAuditBlocked("QDKT_OBSERVATION_EVIDENCE_UNVERIFIED")
    actual = inspect_supplied_qdkt_dotx_set(directory)
    for measured in actual:
        row = by_kind[measured.gxp_type]
        names = row.get("bookmark_names")
        if (
            row.get("sha256") != measured.actual_sha256
            or row.get("bookmark_count") != measured.bookmark_count
            or not isinstance(names, list)
            or names != list(measured.bookmark_names)
            or row.get("bookmark_owner_parity_verified") is not False
            or row.get("ready_to_render") is not False
        ):
            raise QdKtDotxAuditBlocked("QDKT_OBSERVED_TEMPLATE_DRIFT")
    if evidence.get("ready_to_render") is not False:
        raise QdKtDotxAuditBlocked("QDKT_OBSERVATION_EVIDENCE_UNVERIFIED")
    return tuple(measured.gxp_type for measured in actual)
