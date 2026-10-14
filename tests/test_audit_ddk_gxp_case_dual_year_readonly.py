"""Both physical db.ktra source years are checked without NAS/DB writes."""
from __future__ import annotations

from backend.app.db.enums import StorageResolutionStatus
from backend.app.storage.smb import SmbStorageService
from tools.audit_ddk_gxp_case_dual_year_readonly import probe_source_years_readonly


def _cases():
    return [
        {
            "parent_id": str(n),
            "site_legacy_id": 103,
            "inspection_legacy_code": "KT-1376-GMP",
            "source_years": [
                {"year": 2023, "provenance": ["submission"]},
                {"year": 2026, "provenance": ["inspection"]},
            ],
        }
        for n in range(6)
    ]


def test_case_can_exist_only_under_inspection_year(monkeypatch):
    service = object.__new__(SmbStorageService)
    calls = []
    def lookup(*, year, site_legacy_id, inspection_legacy_code):
        calls.append(year)
        status = (StorageResolutionStatus.RESOLVED if year == 2026
                  else StorageResolutionStatus.NOT_FOUND)
        return type("Resolution", (), {
            "status": status,
            "candidate_count": 1 if status == StorageResolutionStatus.RESOLVED else 0,
            "relative_path": ("2026/Match" if status == StorageResolutionStatus.RESOLVED else None),
        })()
    monkeypatch.setattr(service, "resolve_inspection_folder", lookup)
    report = probe_source_years_readonly(service, _cases())
    assert report["counts"]["CASE_RESOLVED"] == 6
    assert report["counts"]["RESOLVED_BY_INSPECTION_YEAR"] == 6
    assert report["year_specific_lookups"] == 12
    assert calls == [2023, 2026] * 6
    assert report["database_writes"] == 0
    assert report["storage_writes"] == 0
    assert report["canonical_links_created"] == 0


def test_two_matching_years_ambiguous_without_unverified_choice(monkeypatch):
    service = object.__new__(SmbStorageService)
    def lookup(*, year, site_legacy_id, inspection_legacy_code):
        return type("Resolution", (), {
            "status": StorageResolutionStatus.RESOLVED,
            "candidate_count": 1,
            "relative_path": str(year) + "/Match",
        })()
    monkeypatch.setattr(service, "resolve_inspection_folder", lookup)
    report = probe_source_years_readonly(service, _cases())
    assert report["counts"]["CASE_AMBIGUOUS"] == 6
    assert "CASE_RESOLVED" not in report["counts"]
    assert report["approval_status"] == "NOT_APPROVED"


def _unresolved_cases():
    def source_year(year, provenance):
        return {
            "source_year": year,
            "provenance": provenance,
            "status": "not_found",
            "candidate_count": 0,
            "relative_path_private_unverified": None,
        }
    return [
        {
            "parent_id": "case-a", "final_status": "NOT_FOUND",
            "site_legacy_id": 103, "inspection_legacy_code": "KT-1376-GMP",
            "year_specific_observations": [source_year(2023, ["submission"])],
        },
        {
            "parent_id": "case-b", "final_status": "NOT_FOUND",
            "site_legacy_id": 104, "inspection_legacy_code": "KT-1377-GMP",
            "year_specific_observations": [source_year(2024, ["inspection"])],
        },
        {
            "parent_id": "case-c", "final_status": "NOT_FOUND",
            "site_legacy_id": 105, "inspection_legacy_code": "KT-1378-GMP",
            "year_specific_observations": [
                source_year(2025, ["submission"]),
                source_year(2026, ["inspection"]),
            ],
        },
    ]


def _fake_metadata(monkeypatch, year_directories):
    from types import SimpleNamespace
    import tools.audit_ddk_gxp_case_dual_year_readonly as owner

    service = object.__new__(SmbStorageService)
    service.inspection_root = r"\\mock-server\private\inspections"

    def key(path):
        return int(path.rsplit("\\", 1)[-1])

    def entry(name):
        return SimpleNamespace(name=name, is_dir=lambda: True)

    monkeypatch.setattr(
        owner, "smbpath",
        SimpleNamespace(
            exists=lambda path: key(path) in year_directories,
            isdir=lambda path: key(path) in year_directories,
        ),
    )
    monkeypatch.setattr(
        owner, "smbclient",
        SimpleNamespace(
            scandir=lambda path: [entry(name) for name in year_directories[key(path)]],
        ),
    )
    return service


def test_missing_case_year_directories_are_only_aggregate_metadata(monkeypatch):
    from tools.audit_ddk_gxp_case_dual_year_readonly import (
        classify_unresolved_case_year_roots_readonly,
    )
    service = _fake_metadata(monkeypatch, {
        2024: ["completely unrelated"],
        2025: ["Site (ID-105)", "Inspection (KT-1378-GMP)"],
        2026: ["Site (ID-105)"],
    })
    report = classify_unresolved_case_year_roots_readonly(
        service, _unresolved_cases())
    assert report["missing_case_parents_checked"] == 3
    assert report["source_year_observations_checked"] == 4
    assert report["classification_counts"] == {
        "NO_EXACT_TOKEN": 1,
        "SITE_TOKEN_ONLY": 1,
        "SPLIT_TOKENS_DIFFERENT_FOLDERS": 1,
        "YEAR_ROOT_NOT_FOUND": 1,
    }
    assert report["year_root_entries_scanned"] == 4
    assert report["database_connected"] is False
    assert report["storage_file_contents_accessed"] is False
    assert report["storage_writes"] == 0
    assert report["canonical_links_created"] == 0
    protected = report["private_case_year_metadata_observations"]
    assert len(protected) == 4
    assert {row["originating_case_id"] for row in protected} == {
        "case-a", "case-b", "case-c",
    }
    safe = {
        key: value for key, value in report.items()
        if key != "private_case_year_metadata_observations"
    }
    assert "KT-1378" not in str(safe)
    assert "case-" not in str(safe)
    assert "mock-server" not in str(safe)
    assert not any(key.endswith("_id") for key in safe)


def test_missing_case_diagnostic_blocks_changed_complete_match(monkeypatch):
    import pytest
    from tools.audit_ddk_gxp_case_dual_year_readonly import (
        classify_unresolved_case_year_roots_readonly, DualYearCaseAuditBlocked,
    )
    service = _fake_metadata(monkeypatch, {
        2023: ["(ID-103) inspection (KT-1376-GMP)"],
        2024: [], 2025: [], 2026: [],
    })
    with pytest.raises(DualYearCaseAuditBlocked):
        classify_unresolved_case_year_roots_readonly(service, _unresolved_cases())


def test_missing_case_diagnostic_rejects_scan_budget_overrun(monkeypatch):
    import pytest
    from tools.audit_ddk_gxp_case_dual_year_readonly import (
        classify_unresolved_case_year_roots_readonly, DualYearCaseAuditBlocked,
    )
    service = _fake_metadata(monkeypatch, {
        2023: [], 2024: [], 2025: ["a", "b"], 2026: [],
    })
    with pytest.raises(DualYearCaseAuditBlocked):
        classify_unresolved_case_year_roots_readonly(
            service, _unresolved_cases(), max_entries_per_root=1)


def test_missing_case_diagnostic_refuses_unverified_case_state(monkeypatch):
    import pytest
    from tools.audit_ddk_gxp_case_dual_year_readonly import (
        classify_unresolved_case_year_roots_readonly, DualYearCaseAuditBlocked,
    )
    service = _fake_metadata(monkeypatch, {
        2023: [], 2024: [], 2025: [], 2026: [],
    })
    cases = _unresolved_cases()
    cases[0]["final_status"] = "RESOLVED"
    with pytest.raises(DualYearCaseAuditBlocked):
        classify_unresolved_case_year_roots_readonly(service, cases)
