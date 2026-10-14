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
