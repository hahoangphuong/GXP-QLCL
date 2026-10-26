"""Read-only evidence for the legacy QĐKT Rg3-to-canonical identity bridge.

The module proves only record identity and literal value projection.  It does
not promote a modern rendering owner, interpret ambiguous business semantics,
or authorize document generation.  No database, service, or storage access.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Literal, Mapping, Sequence

from backend.app.domain.phase2_import import normalize_row, parse_dt, parse_int

_ROOT = Path(__file__).resolve().parents[3]
_SOURCE = _ROOT / "artifacts/legacy_audit/inspection_qd_kt_input_provenance.json"
_RG3_CONTRACT = _ROOT / "artifacts/legacy_audit/inspection_qd_kt_rg3_crosswalk_contract.json"
_SNAPSHOT = _ROOT / "artifacts/phase3c/legacy_snapshot.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED = {
    "HsDK": ("CaseApplication.dossier_code", "db.ktra row, ColDB_HSDK_Ktra + 1"),
    "NgaynopHsDK": ("CaseApplication.submitted_on", "db.ktra row, ColDB_HSDK_Ktra"),
    "Tencoso": ("Site.site_name", "planning row cell 4; fallback/alternate db_cso site row"),
}


@dataclass(frozen=True)
class QdKtIdentityEvidenceResult:
    logical_name: str
    modern_candidate: str
    legacy_source: str
    legacy_row_identity_verified: bool = False
    canonical_case_identity_verified: bool = False
    record_selection_rule_verified: bool = False
    value_semantics_verified: bool = False
    modern_owner_verified: bool = False
    ready_to_render: bool = False


@dataclass(frozen=True)
class Rg3Selection:
    """The only two observed QĐKT launch origins.

    MAIN_HISTORY carries the selected db.ktra named-range row index.  The
    independent KHKT ActiveSheet route does not establish Rg3 at all.
    """

    origin: Literal["MAIN_HISTORY", "KHKT_ACTIVE_ROW"]
    named_range_index: int | None


@dataclass(frozen=True)
class LegacyRg3DossierRow:
    source_workbook_sha256: str
    source_sheet: str
    source_row: int
    named_range_index: int
    legacy_inspection_id: int | None
    legacy_site_id: int | None
    dossier_code: str | None
    submitted_raw: str | None
    anchor_source_hash: str


@dataclass(frozen=True)
class CanonicalQdKtCaseEvidence:
    case_id: str
    case_legacy_inspection_id: int | None
    case_site_id: str
    site_id: str
    site_legacy_id: int | None
    application_case_id: str | None
    application_dossier_code: str | None
    application_submitted_on: datetime | None
    anchor_case_id: str | None
    anchor_source_sheet: str | None
    anchor_source_row: int | None
    anchor_source_version: str | None
    anchor_source_hash: str | None
    matching_application_count: int = 1


@dataclass(frozen=True)
class QdKtRg3CrosswalkResult:
    status: str
    legacy_inspection_id: int | None = None
    case_id: str | None = None
    same_worksheet_row: bool = False
    same_inspection_record: bool = False
    same_registered_site: bool = False
    same_canonical_case: bool = False
    same_application: bool = False
    dossier_value_projection_verified: bool = False
    submitted_value_projection_verified: bool = False
    submitted_business_semantics_verified: bool = False
    modern_owner_verified: bool = False
    owner_promotion_allowed: bool = False
    ready_to_render: bool = False


@dataclass(frozen=True)
class QdKtRg3BaselineEvidence:
    source_workbook_sha256: str
    named_range_first_row: int
    snapshot_row_count: int
    effective_row_count: int
    unique_legacy_inspection_id_count: int
    anchor_projection_row_count: int
    projection_exact_id_row_count: int
    legacy_id_differs_from_named_range_index_count: int
    sites_with_multiple_cases: int
    max_cases_per_site: int
    nonblank_dossier_row_count: int
    duplicate_dossier_value_count: int
    rows_with_duplicate_dossier_value: int
    contains_raw_business_values: bool = False


def inspect_qdkt_cross_system_identity(
    *, provenance_path: Path = _SOURCE,
    proposed_mapping: Mapping[str, str] | None = None,
) -> tuple[QdKtIdentityEvidenceResult, ...]:
    """Validate pinned candidate labels, but NEVER authorize an ORM mapping."""
    try:
        data = json.loads(Path(provenance_path).read_text(encoding="utf-8"))
        fields = data["fields"]
        results = []
        for name, (candidate, source) in _EXPECTED.items():
            row = fields[name]
            if (
                row["owner_classification"] != "OWNER_PARTIAL"
                or row["modern_owner_candidate"] != candidate
                or row["source_semantic_endpoint"] != source
                or not row["blocker"]
            ):
                raise ValueError("QDKT_CROSS_SYSTEM_SOURCE_OR_OWNER_DRIFT")
            results.append(QdKtIdentityEvidenceResult(
                logical_name=name, modern_candidate=candidate, legacy_source=source,
            ))
        if proposed_mapping is not None:
            if not isinstance(proposed_mapping, Mapping) or set(proposed_mapping) != set(_EXPECTED):
                raise ValueError("QDKT_CROSS_SYSTEM_MAPPING_INCOMPLETE")
            if any(not isinstance(value, str) or not value.strip() for value in proposed_mapping.values()):
                raise ValueError("QDKT_CROSS_SYSTEM_MAPPING_INVALID")
        return tuple(results)
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("QDKT_CROSS_SYSTEM_PROVENANCE_UNAVAILABLE") from exc


def _result(status: str, **evidence: object) -> QdKtRg3CrosswalkResult:
    """Construct a fail-closed result; promotion flags cannot be overridden."""
    forbidden = {"modern_owner_verified", "owner_promotion_allowed", "ready_to_render"}
    if forbidden.intersection(evidence):
        raise ValueError("QDKT_RG3_PROMOTION_OVERRIDE_DENIED")
    return QdKtRg3CrosswalkResult(status=status, **evidence)


def assess_qdkt_rg3_crosswalk(
    *,
    selection: Rg3Selection,
    legacy_rows: Sequence[LegacyRg3DossierRow],
    canonical_candidates: Sequence[CanonicalQdKtCaseEvidence],
    expected_workbook_sha256: str,
) -> QdKtRg3CrosswalkResult:
    """Prove an exact selected db.ktra row and its canonical projection.

    No name, dossier value, date, or Site alone is accepted as a join key.
    """
    if selection.origin == "KHKT_ACTIVE_ROW":
        return _result("KHKT_PATH_HAS_NO_RG3_SELECTION")
    if selection.origin != "MAIN_HISTORY" or selection.named_range_index is None:
        return _result("NO_MATCHING_LEGACY_ROW")
    if not _SHA256.fullmatch(expected_workbook_sha256):
        raise ValueError("QDKT_RG3_EXPECTED_SOURCE_VERSION_INVALID")

    rows = [row for row in legacy_rows if row.named_range_index == selection.named_range_index]
    if not rows:
        return _result("NO_MATCHING_LEGACY_ROW")
    if len(rows) != 1:
        return _result("AMBIGUOUS_LEGACY_ROW")
    row = rows[0]
    identified = {"legacy_inspection_id": row.legacy_inspection_id}

    # db_ktra starts at physical row 5, so named-range row n is sheet row n+4.
    if row.source_sheet != "db.ktra" or row.source_row != row.named_range_index + 4:
        return _result("SOURCE_ROW_COORDINATE_MISMATCH", **identified)
    if row.source_workbook_sha256 != expected_workbook_sha256:
        return _result("SOURCE_VERSION_MISMATCH", **identified)
    if row.legacy_inspection_id is None:
        return _result("MISSING_LEGACY_INSPECTION_ID", same_worksheet_row=True, **identified)

    cases = [case for case in canonical_candidates if case.case_legacy_inspection_id == row.legacy_inspection_id]
    if not cases:
        return _result("NO_MATCHING_CANONICAL_CASE", same_worksheet_row=True, **identified)
    if len(cases) != 1:
        return _result("AMBIGUOUS_CANONICAL_CASE", same_worksheet_row=True, **identified)
    case = cases[0]
    identified.update(case_id=case.case_id)

    if case.anchor_case_id is None or case.anchor_source_sheet is None or case.anchor_source_row is None:
        return _result("INSUFFICIENT_CANONICAL_IDENTITY_EVIDENCE", same_worksheet_row=True, **identified)
    if case.anchor_case_id != case.case_id:
        return _result("ANCHOR_CASE_IDENTITY_CONFLICT", same_worksheet_row=True, **identified)
    if case.anchor_source_sheet != row.source_sheet or case.anchor_source_row != row.source_row:
        return _result("SOURCE_ROW_CHANGED_AFTER_IMPORT", same_worksheet_row=True, **identified)
    if case.anchor_source_version != expected_workbook_sha256:
        return _result("SOURCE_VERSION_MISMATCH", same_worksheet_row=True, **identified)
    if case.anchor_source_hash != row.anchor_source_hash:
        return _result("SOURCE_HASH_MISMATCH", same_worksheet_row=True, **identified)

    base = dict(
        same_worksheet_row=True,
        same_inspection_record=True,
        same_canonical_case=True,
        **identified,
    )
    if (
        row.legacy_site_id is None
        or case.site_legacy_id != row.legacy_site_id
        or case.case_site_id != case.site_id
    ):
        return _result("SITE_IDENTITY_CONFLICT", **base)
    base["same_registered_site"] = True

    if case.matching_application_count == 0 or case.application_case_id is None:
        return _result("MISSING_CANONICAL_APPLICATION", **base)
    if case.matching_application_count != 1:
        return _result("AMBIGUOUS_CANONICAL_APPLICATION", **base)
    if case.application_case_id != case.case_id:
        return _result("APPLICATION_CASE_IDENTITY_CONFLICT", **base)
    base["same_application"] = True

    legacy_dossier = None if row.dossier_code is None else str(row.dossier_code).strip() or None
    modern_dossier = (
        None if case.application_dossier_code is None
        else str(case.application_dossier_code).strip() or None
    )
    if legacy_dossier != modern_dossier:
        return _result("DOSSIER_VALUE_CONFLICT", **base)
    base["dossier_value_projection_verified"] = True

    legacy_submitted = parse_dt(row.submitted_raw)
    if row.submitted_raw not in (None, "") and legacy_submitted is None:
        return _result("AMBIGUOUS_SUBMISSION_DATE", **base)
    modern_submitted = case.application_submitted_on
    if isinstance(modern_submitted, datetime) and modern_submitted.tzinfo is not None:
        modern_submitted = modern_submitted.replace(tzinfo=None)
    if legacy_submitted != modern_submitted:
        return _result("SUBMISSION_VALUE_CONFLICT", **base)
    base["submitted_value_projection_verified"] = True
    return _result("IDENTITY_PROVEN_SEMANTICS_PARTIAL", **base)


def _snapshot_rows(data: object, table_name: str = "db.ktra") -> list[dict[str, object]]:
    if not isinstance(data, dict):
        raise ValueError("QDKT_RG3_SNAPSHOT_INVALID")
    for key in (table_name.replace(".", "_"), table_name):
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    tables = data.get("tables")
    if isinstance(tables, dict):
        for key in (table_name.replace(".", "_"), table_name):
            value = tables.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    raise ValueError("QDKT_RG3_SNAPSHOT_TABLE_MISSING")


def inspect_qdkt_rg3_baseline(
    *,
    contract_path: Path = _RG3_CONTRACT,
    snapshot_path: Path = _SNAPSHOT,
    anchor_path: Path | None = None,
) -> QdKtRg3BaselineEvidence:
    """Recompute privacy-safe aggregate claims from committed source evidence."""
    try:
        contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
        snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
        rows = _snapshot_rows(snapshot)
        site_rows = _snapshot_rows(snapshot, "db.cso")
        aliases = contract["snapshot_columns"]
        first_row = int(contract["named_range"]["physical_first_row"])
        workbook_sha = contract["sources"]["workbook_sha256"]
        if not _SHA256.fullmatch(workbook_sha):
            raise ValueError("QDKT_RG3_SOURCE_VERSION_INVALID")

        valid_site_ids = {
            parsed
            for raw in site_rows
            if (parsed := parse_int(normalize_row(raw).get("ID"))) is not None
        }
        effective: list[tuple[int, int, int | None, str | None]] = []
        for raw in rows:
            normalized = normalize_row(raw)
            legacy_id = parse_int(normalized.get(aliases["legacy_inspection_id"]))
            if legacy_id is None:
                continue
            site_id = parse_int(normalized.get(aliases["legacy_site_id"]))
            dossier_value = normalized.get(aliases["dossier_code"])
            dossier = None if dossier_value is None else str(dossier_value).strip() or None
            source_row = parse_int(normalized.get("__excel_row_number"))
            if source_row is None:
                raise ValueError("QDKT_RG3_SOURCE_ROW_MISSING")
            if site_id not in valid_site_ids:
                continue
            if dossier == "-":
                dossier = None
            effective.append((legacy_id, source_row, site_id, dossier))

        anchor_audit = contract["anchor_projection_audit"]
        anchor_count = int(anchor_audit["effective_case_count"])
        exact_projection_count = int(anchor_audit["exact_id_source_row_match_count"])
        if not anchor_audit["parity_passed"]:
            raise ValueError("QDKT_RG3_ANCHOR_AUDIT_NOT_PASSED")
        if anchor_path is not None:
            anchors_data = json.loads(Path(anchor_path).read_text(encoding="utf-8"))
            anchors = anchors_data["rows"] if isinstance(anchors_data, dict) else anchors_data
            if not isinstance(anchors, list):
                raise ValueError("QDKT_RG3_ANCHOR_PROJECTION_INVALID")
            if any(
                anchor.get("source_sheet") != "db.ktra"
                or anchor.get("source_version") != workbook_sha
                for anchor in anchors
            ):
                raise ValueError("QDKT_RG3_ANCHOR_SOURCE_DRIFT")
            anchor_pairs = {
                (int(anchor["legacy_inspection_id"]), int(anchor["source_row"]))
                for anchor in anchors
            }
            anchor_count = len(anchors)
            exact_projection_count = sum(
                (legacy_id, source_row) in anchor_pairs
                for legacy_id, source_row, _, _ in effective
            )
        site_counts = Counter(site for _, _, site, _ in effective if site is not None)
        dossier_counts = Counter(dossier for _, _, _, dossier in effective if dossier is not None)
        evidence = QdKtRg3BaselineEvidence(
            source_workbook_sha256=workbook_sha,
            named_range_first_row=first_row,
            snapshot_row_count=len(rows),
            effective_row_count=len(effective),
            unique_legacy_inspection_id_count=len({row[0] for row in effective}),
            anchor_projection_row_count=anchor_count,
            projection_exact_id_row_count=exact_projection_count,
            legacy_id_differs_from_named_range_index_count=sum(legacy_id != source_row - first_row + 1 for legacy_id, source_row, _, _ in effective),
            sites_with_multiple_cases=sum(count > 1 for count in site_counts.values()),
            max_cases_per_site=max(site_counts.values(), default=0),
            nonblank_dossier_row_count=sum(dossier is not None for _, _, _, dossier in effective),
            duplicate_dossier_value_count=sum(count > 1 for count in dossier_counts.values()),
            rows_with_duplicate_dossier_value=sum(count for count in dossier_counts.values() if count > 1),
        )
        expected = contract["privacy_safe_aggregates"]
        for field, value in expected.items():
            if not hasattr(evidence, field) or getattr(evidence, field) != value:
                raise ValueError("QDKT_RG3_AGGREGATE_DRIFT")
        if contract["invariants"]["contains_raw_business_values"] is not False:
            raise ValueError("QDKT_RG3_RAW_VALUE_POLICY_DRIFT")
        return evidence
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("QDKT_RG3_BASELINE_EVIDENCE_UNAVAILABLE") from exc
