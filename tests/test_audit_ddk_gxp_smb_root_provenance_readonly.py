"""Root config flags are path-private and cannot authorize remapping."""
from __future__ import annotations

import pytest

from tools.audit_ddk_gxp_smb_root_provenance_readonly import (
    RootProvenanceBlocked, assess_configured_roots, unc_components,
)


def env(**kwargs):
    data = {
        "STORAGE_CLASS": "synology_smb",
        "STORAGE_DKKD_ROOT": r"\\my-server\private\records\Chứng nhận ĐĐKKDD",
        "STORAGE_INSPECTION_ROOT": r"\\my-server\private\records\inspection",
        "SMB_USERNAME": "private", "SMB_PASSWORD": "private",
    }
    data.update(kwargs)
    return data


def test_expected_ddk_alias_within_same_share_emits_flags_no_names():
    report = assess_configured_roots(env())
    assert report["ddk_root_leaf_matches_legacy_ddkd_directory"] is True
    assert report["ddk_root_contains_legacy_ddkd_directory"] is True
    assert report["ddk_root_same_host_and_share_as_inspection"] is True
    assert report["ddk_root_equals_inspection_root"] is False
    assert report["ddk_root_equals_template_root"] is False
    assert r"\private" not in str(report)
    assert "my-server" not in str(report)


def test_unverified_folder_name_does_not_guess_alternate_path():
    report = assess_configured_roots(
        env(STORAGE_DKKD_ROOT=r"\\my-server\private\records\other")
    )
    assert report["ddk_root_leaf_matches_legacy_ddkd_directory"] is False
    assert report["ddk_root_contains_legacy_ddkd_directory"] is False
    assert not any(isinstance(v, str) for v in report.values())


def test_parent_root_wrong_class_reported_without_rescue():
    data = env(STORAGE_DKKD_ROOT=r"\\my-server\private\records")
    report = assess_configured_roots(data)
    assert report["ddk_root_has_subdirectory_after_unc_share"] is True
    assert report["ddk_root_leaf_matches_legacy_ddkd_directory"] is False


def test_unicode_combining_marks_are_normalized():
    data = env(STORAGE_DKKD_ROOT=r"\\my-server\private\records\Chứng nhận ĐĐKKDD")
    assert assess_configured_roots(data)["ddk_root_leaf_matches_legacy_ddkd_directory"]


@pytest.mark.parametrize("bad", [
    "/tmp/records",
    "\\\\host",
    "\\\\host\\share\\..\\secret",
    "\\\\host\\share\\part//hidden",
])
def test_unc_contract_rejects_bad_paths(bad):
    with pytest.raises(RootProvenanceBlocked):
        unc_components(bad)


def test_distinct_storage_roots_can_share_host_and_share():
    report = assess_configured_roots(env(
        STORAGE_DKKD_ROOT=r"\\another-server\private\Chứng nhận ĐĐKKDD"
    ))
    assert report["ddk_root_leaf_matches_legacy_ddkd_directory"] is True
    assert report["ddk_root_same_host_and_share_as_inspection"] is False
