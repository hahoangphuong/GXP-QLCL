"""QĐKT i=2 bookmark targets must follow the actual VBA helper."""
from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from backend.app.document.inspection_qd_kt_vba_bookmark_series import (
    QdKtVbaBookmarkContractError,
    plan_repeated_bookmark_value,
    reconcile_qdkt_i2_bookmarks,
    resolve_vba_bookmark_targets,
)


OBSERVATIONS = (
    Path(__file__).resolve().parent
    / "fixtures/inspection_qd_kt_observed_template_binaries.json"
)
SOURCE_ZIP = Path(__file__).resolve().parents[1] / "legacy/GXP-VBA code.zip"


def _templates() -> dict[str, dict]:
    source = json.loads(OBSERVATIONS.read_text(encoding="utf-8"))
    return {row["gxp_type"]: row for row in source["templates"]}


def _source_lines(entry: str) -> list[str]:
    with ZipFile(SOURCE_ZIP) as archive:
        # Relevant VBA statements are ASCII; latin-1 preserves every source
        # byte while avoiding a platform-dependent legacy code-page decode.
        return archive.read(entry).decode("latin-1").splitlines()


def test_rules_are_pinned_to_the_direct_vba_zip_i2_call_chain():
    record = _source_lines("RecordForm.frm")
    module = _source_lines("Module1.bas")
    assert record[588].startswith("Private Sub Replace_Bookmark")
    assert record[591].strip() == "On Error Resume Next"
    assert record[594].strip() == "If (i >= 0) And (j > 0) Then"
    assert record[595].strip() == "For k = i To j"
    assert (
        record[596].strip()
        == ".Bookmarks(bm & IIf(k = 0, vbNullString, k)).Range.Text = txt"
    )
    assert record[599].strip() == ".Bookmarks(bm).Range.Text = txt"
    assert record[665].strip() == "Case 2      ' Quyet dinh kiem tra"
    assert record[666].strip() == 'tpl = "2. QD KT - " & S_GPs & ".dotx"'
    assert record[743].strip() == (
        'Replace_Bookmark wdDoc, "Tencoso", TenCtydd, 1, 8'
    )
    assert record[750].strip().endswith(
        'Replace_Bookmark wdDoc, "VKNx", s1'
    )
    assert record[751].strip() == (
        'If i = 2 Then Replace_Bookmark wdDoc, "VKN", s2, 1, 2'
    )
    assert record[756].strip().startswith(
        'Replace_Bookmark wdDoc, "TT" & (k + 1) & "x"'
    )
    assert record[764].strip() == 'Replace_Bookmark wdDoc, "TT3x", TVss'
    assert record[765].strip() == 'Else:  Delete_Bookmark wdDoc, "TT3Del"'
    assert record[1733].strip() == "Case 2, 3, 4    ' Quyet dinh KT & Ke hoach KT & Bien ban KT"
    assert record[1734].strip() == "Tao_QDKT_KHKT_BBKT wdDoc, i"
    assert module[647].strip().startswith(
        'rs = .CreateFile(fpath & "\\", 2, syear, False, fname'
    )


def test_vba_helper_uses_exact_name_without_active_series_bounds():
    names = {"VKNx", "VKNx1", "VKNx_extra"}
    assert resolve_vba_bookmark_targets("VKNx", names) == ("VKNx",)
    assert resolve_vba_bookmark_targets(
        "VKNx", names, first_index=-1, last_index=3,
    ) == ("VKNx",)


def test_vba_helper_k_zero_explicitly_addresses_the_unnumbered_name():
    names = {"Base", "Base1", "Base2"}
    assert resolve_vba_bookmark_targets(
        "Base", names, first_index=0, last_index=1,
    ) == ("Base", "Base1")


def test_vba_series_attempts_every_inclusive_index_and_does_not_stop_at_a_gap():
    names = {"Tencoso1", "Tencoso3", "Tencoso8", "Tencoso9"}
    assert resolve_vba_bookmark_targets(
        "Tencoso", names, first_index=1, last_index=8,
    ) == ("Tencoso1", "Tencoso3", "Tencoso8")


def test_vba_series_rejects_near_prefixes_and_does_not_include_unnumbered_name():
    names = {
        "Tencoso", "Tencoso01", "Tencoso1x", "Tencoso_1",
        "OtherTencoso1", "Tencoso1",
    }
    assert resolve_vba_bookmark_targets(
        "Tencoso", names, first_index=1, last_index=8,
    ) == ("Tencoso1",)


@pytest.mark.parametrize("gxp_type", ["GLP", "GMP", "GMPbb", "GSP"])
def test_tencoso_reconciles_to_all_three_real_physical_targets(gxp_type):
    row = _templates()[gxp_type]
    operations = reconcile_qdkt_i2_bookmarks(gxp_type, row["bookmark_names"])
    tencoso = operations["Tencoso"]
    assert tencoso.operation_type == "WRITE"
    assert tencoso.branch_reachable is True
    assert tencoso.candidate_targets == tuple(f"Tencoso{i}" for i in range(1, 9))
    assert tencoso.effective_targets == ("Tencoso1", "Tencoso2", "Tencoso3")
    assert "Tencoso" not in tencoso.effective_targets
    assert "Tencoso9" not in tencoso.candidate_targets


@pytest.mark.parametrize(
    ("gxp_type", "targets"),
    [
        ("GLP", ("Diadiemx1", "Diadiemx2", "Diadiemx3")),
        ("GMP", ("Diadiemx1", "Diadiemx2", "Diadiemx3")),
        ("GMPbb", ("Diadiemx1", "Diadiemx2")),
        ("GSP", ("Diadiemx1", "Diadiemx2")),
    ],
)
def test_diadiemx_uses_its_independent_proven_series(gxp_type, targets):
    row = _templates()[gxp_type]
    operation = reconcile_qdkt_i2_bookmarks(gxp_type, row["bookmark_names"])[
        "Diadiemx"
    ]
    assert operation.candidate_targets == (
        "Diadiemx1", "Diadiemx2", "Diadiemx3",
    )
    assert operation.effective_targets == targets


def test_repeated_content_is_unchanged_for_each_effective_target():
    row = _templates()["GMP"]
    operation = reconcile_qdkt_i2_bookmarks("GMP", row["bookmark_names"])["Tencoso"]
    value = "Cơ sở kiểm thử"
    assert plan_repeated_bookmark_value(operation, value) == (
        ("Tencoso1", value),
        ("Tencoso2", value),
        ("Tencoso3", value),
    )


@pytest.mark.parametrize("gxp_type", ["GLP", "GMP"])
def test_vkn_i2_branch_targets_numbered_series_only_for_glp_and_gmp(gxp_type):
    row = _templates()[gxp_type]
    operations = reconcile_qdkt_i2_bookmarks(gxp_type, row["bookmark_names"])
    assert operations["VKN"].effective_targets == ("VKN1", "VKN2")
    assert "VKN" not in operations["VKN"].effective_targets
    assert operations["VKNx"].effective_targets == ("VKNx",)


@pytest.mark.parametrize("gxp_type", ["GMPbb", "GSP"])
def test_vkn_i2_branch_is_not_executed_for_gmpbb_or_gsp(gxp_type):
    row = _templates()[gxp_type]
    operations = reconcile_qdkt_i2_bookmarks(gxp_type, row["bookmark_names"])
    assert operations["VKN"].branch_reachable is False
    assert operations["VKN"].effective_targets == ()
    assert operations["VKNx"].branch_reachable is False
    assert operations["VKNx"].effective_targets == ()


@pytest.mark.parametrize("gxp_type", ["GLP", "GMP", "GMPbb", "GSP"])
def test_team_targets_keep_dynamic_writes_and_conditional_delete_distinct(gxp_type):
    row = _templates()[gxp_type]
    operations = reconcile_qdkt_i2_bookmarks(gxp_type, row["bookmark_names"])
    assert operations["TTx"].effective_targets == ("TT1x", "TT2x")
    assert operations["TT3x"].operation_type == "WRITE"
    assert operations["TT3x"].effective_targets == ("TT3x",)
    assert operations["TT3Del"].operation_type == "DELETE"
    assert operations["TT3Del"].effective_targets == ("TT3Del",)
    with pytest.raises(QdKtVbaBookmarkContractError, match="QDKT_OPERATION_NOT_WRITE"):
        plan_repeated_bookmark_value(operations["TT3Del"], "must not write")


def test_i3_i4_only_targets_are_not_part_of_the_i2_operation_contract():
    row = _templates()["GMP"]
    operations = reconcile_qdkt_i2_bookmarks("GMP", row["bookmark_names"])
    assert set(operations) == {
        "Tencoso", "Diadiemx", "VKNx", "VKN", "TTx", "TT3x", "TT3Del",
    }
    assert "Tencoso9" not in operations["Tencoso"].candidate_targets
    assert "Tencoso10" not in operations["Tencoso"].candidate_targets
    assert "Daychuyen" not in operations
    assert "TT_VKNx" not in operations


def test_observation_fixture_remains_non_renderable_and_unmodified_in_meaning():
    source = json.loads(OBSERVATIONS.read_text(encoding="utf-8"))
    assert source["ready_to_render"] is False
    assert {row["bookmark_count"] for row in source["templates"]} == {11, 14, 22}
    assert all(row["ready_to_render"] is False for row in source["templates"])
