"""QĐKT cross-system identity must not be established by column-name similarity."""
import json
import hashlib
from datetime import datetime
from pathlib import Path
import zipfile

import pytest

from backend.app.document.inspection_qd_kt_cross_system_identity_evidence import (
    CanonicalQdKtCaseEvidence,
    LegacyRg3DossierRow,
    Rg3Selection,
    assess_qdkt_rg3_crosswalk,
    inspect_qdkt_rg3_baseline,
    inspect_qdkt_cross_system_identity,
)

SOURCE = Path(__file__).resolve().parents[1] / "artifacts/legacy_audit/inspection_qd_kt_input_provenance.json"
CANDIDATES = {
    "HsDK": "CaseApplication.dossier_code",
    "NgaynopHsDK": "CaseApplication.submitted_on",
    "Tencoso": "Site.site_name",
}

WORKBOOK_SHA = "c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d"
ROW_HASH = "a" * 64


def legacy_row(**changes):
    values = {
        "source_workbook_sha256": WORKBOOK_SHA,
        "source_sheet": "db.ktra",
        "source_row": 14,
        "named_range_index": 10,
        "legacy_inspection_id": 501,
        "legacy_site_id": 71,
        "dossier_code": "HS-501",
        "submitted_raw": "02/01/2024",
        "anchor_source_hash": ROW_HASH,
    }
    values.update(changes)
    return LegacyRg3DossierRow(**values)


def canonical_case(**changes):
    values = {
        "case_id": "case-501",
        "case_legacy_inspection_id": 501,
        "case_site_id": "site-71",
        "site_id": "site-71",
        "site_legacy_id": 71,
        "application_case_id": "case-501",
        "application_dossier_code": "HS-501",
        "application_submitted_on": datetime(2024, 1, 2),
        "anchor_case_id": "case-501",
        "anchor_source_sheet": "db.ktra",
        "anchor_source_row": 14,
        "anchor_source_version": WORKBOOK_SHA,
        "anchor_source_hash": ROW_HASH,
    }
    values.update(changes)
    return CanonicalQdKtCaseEvidence(**values)


def assess(*, rows=None, cases=None, selection=None):
    return assess_qdkt_rg3_crosswalk(
        selection=selection or Rg3Selection(origin="MAIN_HISTORY", named_range_index=10),
        legacy_rows=[legacy_row()] if rows is None else rows,
        canonical_candidates=[canonical_case()] if cases is None else cases,
        expected_workbook_sha256=WORKBOOK_SHA,
    )


def test_candidate_labels_do_not_prove_record_identity_or_rendering():
    rows = inspect_qdkt_cross_system_identity(proposed_mapping=CANDIDATES)
    assert {row.logical_name for row in rows} == set(CANDIDATES)
    for row in rows:
        assert row.modern_candidate == CANDIDATES[row.logical_name]
        assert row.legacy_source
        assert row.legacy_row_identity_verified is False
        assert row.canonical_case_identity_verified is False
        assert row.record_selection_rule_verified is False
        assert row.value_semantics_verified is False
        assert row.modern_owner_verified is False
        assert row.ready_to_render is False


def test_even_different_proposed_owner_does_not_prove_parity():
    proposed = dict(CANDIDATES, HsDK="Unverified.external_column")
    rows = inspect_qdkt_cross_system_identity(proposed_mapping=proposed)
    assert all(not row.modern_owner_verified for row in rows)


@pytest.mark.parametrize("change", [
    {"HsDK": "OWNER_PROVEN"},
    {"NgaynopHsDK": "OWNER_PROVEN"},
    {"Tencoso": "OWNER_PROVEN"},
])
def test_source_owner_promotion_fails_closed(tmp_path, change):
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    for key, status in change.items():
        data["fields"][key]["owner_classification"] = status
    path = tmp_path / "provenance.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="QDKT_CROSS_SYSTEM_SOURCE_OR_OWNER_DRIFT"):
        inspect_qdkt_cross_system_identity(provenance_path=path)


def test_missing_mapping_or_blank_candidate_is_rejected():
    with pytest.raises(ValueError, match="QDKT_CROSS_SYSTEM_MAPPING_INCOMPLETE"):
        inspect_qdkt_cross_system_identity(proposed_mapping={"HsDK": "X"})
    with pytest.raises(ValueError, match="QDKT_CROSS_SYSTEM_MAPPING_INVALID"):
        inspect_qdkt_cross_system_identity(proposed_mapping=dict(CANDIDATES, HsDK=" "))


def test_exact_rg3_row_case_application_and_site_identity_is_proven_without_owner_promotion():
    result = assess()
    assert result.status == "IDENTITY_PROVEN_SEMANTICS_PARTIAL"
    assert result.same_worksheet_row is True
    assert result.same_inspection_record is True
    assert result.same_registered_site is True
    assert result.same_canonical_case is True
    assert result.same_application is True
    assert result.dossier_value_projection_verified is True
    assert result.submitted_value_projection_verified is True
    assert result.submitted_business_semantics_verified is False
    assert result.modern_owner_verified is False
    assert result.ready_to_render is False


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([], "NO_MATCHING_LEGACY_ROW"),
        ([legacy_row(), legacy_row(legacy_inspection_id=502)], "AMBIGUOUS_LEGACY_ROW"),
    ],
)
def test_rg3_selection_requires_exactly_one_source_row(rows, expected):
    assert assess(rows=rows).status == expected


def test_khkt_active_row_path_does_not_manufacture_an_rg3_selection():
    result = assess(selection=Rg3Selection(origin="KHKT_ACTIVE_ROW", named_range_index=None))
    assert result.status == "KHKT_PATH_HAS_NO_RG3_SELECTION"
    assert result.same_worksheet_row is False


def test_multiple_rows_for_one_site_are_disambiguated_only_by_selected_row_index():
    other = legacy_row(source_row=15, named_range_index=11, legacy_inspection_id=502, dossier_code="HS-502")
    result = assess(rows=[legacy_row(), other])
    assert result.status == "IDENTITY_PROVEN_SEMANTICS_PARTIAL"
    assert result.legacy_inspection_id == 501


def test_multiple_cases_for_one_site_are_disambiguated_by_legacy_inspection_id_not_site():
    other_case = canonical_case(
        case_id="case-502",
        case_legacy_inspection_id=502,
        application_case_id="case-502",
        anchor_case_id="case-502",
        anchor_source_row=15,
    )
    result = assess(cases=[other_case, canonical_case()])
    assert result.status == "IDENTITY_PROVEN_SEMANTICS_PARTIAL"
    assert result.case_id == "case-501"


def test_duplicate_dossier_code_does_not_collapse_distinct_inspection_rows():
    duplicate = legacy_row(source_row=15, named_range_index=11, legacy_inspection_id=502)
    result = assess(rows=[legacy_row(), duplicate])
    assert result.status == "IDENTITY_PROVEN_SEMANTICS_PARTIAL"
    assert result.legacy_inspection_id == 501


def test_matching_dossier_code_cannot_override_conflicting_inspection_identity():
    wrong = canonical_case(case_id="case-other", case_legacy_inspection_id=999, application_case_id="case-other", anchor_case_id="case-other")
    result = assess(cases=[wrong])
    assert result.status == "NO_MATCHING_CANONICAL_CASE"
    assert result.same_canonical_case is False


def test_missing_legacy_inspection_identifier_fails_closed():
    assert assess(rows=[legacy_row(legacy_inspection_id=None)]).status == "MISSING_LEGACY_INSPECTION_ID"


def test_correct_source_row_cannot_bind_to_the_wrong_canonical_case():
    wrong = canonical_case(case_legacy_inspection_id=777)
    assert assess(cases=[wrong]).status == "NO_MATCHING_CANONICAL_CASE"


def test_duplicate_canonical_case_for_one_inspection_id_fails_closed():
    duplicate = canonical_case(
        case_id="case-duplicate",
        application_case_id="case-duplicate",
        anchor_case_id="case-duplicate",
    )
    assert assess(cases=[canonical_case(), duplicate]).status == "AMBIGUOUS_CANONICAL_CASE"


@pytest.mark.parametrize(
    ("case_change", "expected"),
    [
        ({"anchor_source_row": 99}, "SOURCE_ROW_CHANGED_AFTER_IMPORT"),
        ({"anchor_source_version": "b" * 64}, "SOURCE_VERSION_MISMATCH"),
        ({"anchor_source_hash": "b" * 64}, "SOURCE_HASH_MISMATCH"),
        ({"site_legacy_id": 72}, "SITE_IDENTITY_CONFLICT"),
        ({"application_case_id": None}, "MISSING_CANONICAL_APPLICATION"),
        ({"matching_application_count": 2}, "AMBIGUOUS_CANONICAL_APPLICATION"),
        ({"application_case_id": "case-other"}, "APPLICATION_CASE_IDENTITY_CONFLICT"),
        ({"application_dossier_code": "HS-OTHER"}, "DOSSIER_VALUE_CONFLICT"),
        ({"application_submitted_on": datetime(2024, 1, 3)}, "SUBMISSION_VALUE_CONFLICT"),
        ({"anchor_case_id": None}, "INSUFFICIENT_CANONICAL_IDENTITY_EVIDENCE"),
    ],
)
def test_crosswalk_rejects_changed_or_incomplete_canonical_provenance(case_change, expected):
    assert assess(cases=[canonical_case(**case_change)]).status == expected


def test_ambiguous_submission_date_semantics_remain_blocked():
    result = assess(rows=[legacy_row(submitted_raw="received/submitted 02/01/2024")])
    assert result.status == "AMBIGUOUS_SUBMISSION_DATE"
    assert result.submitted_business_semantics_verified is False


def test_one_modern_candidate_with_matching_labels_is_not_enough_without_exact_identity():
    candidate = canonical_case(case_legacy_inspection_id=None, anchor_case_id=None)
    result = assess(cases=[candidate])
    assert result.status == "NO_MATCHING_CANONICAL_CASE"
    assert result.modern_owner_verified is False


def test_proposed_owner_promotion_is_denied_even_after_row_identity_is_proven():
    result = assess()
    assert result.owner_promotion_allowed is False
    assert result.ready_to_render is False


def test_committed_baseline_proves_row_index_bridge_and_real_world_ambiguity_without_raw_values():
    baseline = inspect_qdkt_rg3_baseline()
    assert baseline.source_workbook_sha256 == WORKBOOK_SHA
    assert baseline.named_range_first_row == 5
    assert baseline.effective_row_count == 1496
    assert baseline.projection_exact_id_row_count == 1496
    assert baseline.legacy_id_differs_from_named_range_index_count == 917
    assert baseline.sites_with_multiple_cases == 276
    assert baseline.duplicate_dossier_value_count == 138
    assert baseline.contains_raw_business_values is False


def test_direct_anchor_projection_matches_contract_when_local_evidence_is_available():
    anchor = (
        Path(__file__).resolve().parents[1]
        / "artifacts/legacy_audit/legacy_inspection_storage_anchor_projection.json"
    )
    if not anchor.exists():
        pytest.skip("raw local anchor projection is intentionally excluded from Git")
    baseline = inspect_qdkt_rg3_baseline(anchor_path=anchor)
    assert baseline.anchor_projection_row_count == 1496
    assert baseline.projection_exact_id_row_count == 1496


def test_direct_vba_rg3_selection_trace_when_pinned_archive_is_available():
    """The public legacy archive is excluded from CI; verify it directly when present."""
    archive = Path(__file__).resolve().parents[1] / "legacy/GXP-VBA code.zip"
    if not archive.exists():
        pytest.skip("pinned legacy VBA archive is intentionally unavailable in this checkout")
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == (
        "6227fb0a6b3d74fa0f4cc655b94b021a40d65a508c2f2eefc62f1724c7b89ff7"
    )
    with zipfile.ZipFile(archive) as source:
        main = source.read("MainForm.frm").decode("cp1252")
        module = source.read("Module1.bas").decode("cp1252")
        record = source.read("RecordForm.frm").decode("cp1252")

    assert "Get_IdxKtra = Me.lbHist.List(Me.lbHist.ListIndex, 0)" in main
    assert 'LoadMappingList(TTList, "db_ID_Cs_Ktra", idcs, True, "db_Loai_Ktra", GPs_Textx, True)' in main
    assert "TTList(count) = i" in module
    assert 'Set Rg3 = Names("db_ktra").RefersToRange.Rows(Idx_Ktr)' in record
    assert "s_MaHsDk = Rg3.Cells(1, ColDB_HSDK_Ktra + 1).Value" in record
    assert "s_NgaynopHsDk = Rg3.Cells(1, ColDB_HSDK_Ktra).Value" in record
    assert "rs = .CreateFile(fpath & \"\\\", 2, syear" in module

    khkt_start = module.index("Sub TaoQDKT_KHKT")
    khkt_body = module[khkt_start:module.index("End Sub", khkt_start)]
    assert "Rg3" not in khkt_body
    assert "s_MaHsDk" not in khkt_body
    assert "s_NgaynopHsDk" not in khkt_body


def test_canonical_import_and_models_keep_one_row_one_case_application_identity_contract():
    root = Path(__file__).resolve().parents[1]
    importer = (root / "backend/app/domain/phase2_import.py").read_text(encoding="utf-8")
    models = (root / "backend/app/db/models/phase1.py").read_text(encoding="utf-8")

    assert 'for raw_row in snapshot["db.ktra"]:' in importer
    assert '"legacy_inspection_id": legacy_id' in importer
    assert '"site_id": site_id' in importer
    assert 'filters={"case_id": entity.id}' in importer
    assert '"submitted_on": submitted_at' in importer
    assert '"dossier_code": row.get("dossier_code") or None' in importer
    assert "legacy_inspection_id: Mapped[int | None] = mapped_column(Integer, unique=True)" in models
    assert 'case_id: Mapped[str] = mapped_column(ForeignKey("case.id"), nullable=False, unique=True)' in models
    assert 'UniqueConstraint("source_sheet", "source_row")' in models
