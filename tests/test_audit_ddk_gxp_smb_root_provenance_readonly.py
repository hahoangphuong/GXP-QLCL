"""Root config flags are path-private and cannot authorize remapping."""
from __future__ import annotations

import pytest

from tools.audit_ddk_gxp_smb_root_provenance_readonly import (
    RootProvenanceBlocked, assess_configured_roots, unc_components,
    safe_failure_code,
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



def test_safe_diagnostic_classifies_ddkd_invalid_root_without_leaking_data():
    sensitive = r"\\sensitive-nas\private\secret-site"
    data = env(STORAGE_DKKD_ROOT="invalid:" + sensitive)
    with pytest.raises(RootProvenanceBlocked) as exc:
        assess_configured_roots(data)
    assert safe_failure_code(exc.value) == "DDKD_ROOT_UNC_INVALID"
    assert sensitive not in safe_failure_code(exc.value)


def test_safe_diagnostic_distinguishes_invalid_inspection_from_ddk_root():
    data = env(STORAGE_INSPECTION_ROOT="/unauthorized/private/archive")
    with pytest.raises(RootProvenanceBlocked) as exc:
        assess_configured_roots(data)
    assert safe_failure_code(exc.value) == "INSPECTION_ROOT_UNC_INVALID"


def test_safe_diagnostic_optional_template_root_guard():
    data = env(STORAGE_TEMPLATE_ROOT="not a UNC root")
    with pytest.raises(RootProvenanceBlocked) as exc:
        assess_configured_roots(data)
    assert safe_failure_code(exc.value) == "TEMPLATE_ROOT_UNC_INVALID"


def test_safe_diagnostic_known_evidence_guard_stages():
    assert safe_failure_code(RootProvenanceBlocked(
        "Second-level protected shape differs"
    )) == "SECOND_LEVEL_REPORT_INTEGRITY"
    assert safe_failure_code(RootProvenanceBlocked(
        "Original private root report differs"
    )) == "ROOT_SHAPE_REPORT_INTEGRITY"


def test_safe_diagnostic_does_not_echo_unknown_exception_message():
    private_marker = "sshpass/private/secret_nas"
    assert safe_failure_code(RootProvenanceBlocked(private_marker)) == "OWNER_GUARD_UNCLASSIFIED"
    assert safe_failure_code(ValueError(private_marker)) == "ValueError"


def test_whitespace_handling_consistent_with_storage_factory():
    data = env(STORAGE_DKKD_ROOT="  " + env()["STORAGE_DKKD_ROOT"] + "  ")
    assert assess_configured_roots(data)["ddk_root_leaf_matches_legacy_ddkd_directory"]


def test_literal_unc_root_comparison_does_not_approve_new_mapping():
    result = assess_configured_roots(env(
        STORAGE_DKKD_ROOT=r"\\my-server\private\unverified-archive"
    ))
    assert result["ddk_root_leaf_matches_legacy_ddkd_directory"] is False
    assert not any(isinstance(v, str) for v in result.values())


def test_repeated_backslashes_use_adapter_component_boundaries_without_rewriting_root():
    # VM evidence: live adapter accepts a UNC value whose old audit parser
    # rejected because of empty split components. Keep the raw value intact.
    from backend.app.storage.smb import SmbStorageService

    value = "\\\\my-server\\\\private\\\\records\\\\Chứng nhận ĐĐKKDD"
    data = env(STORAGE_DKKD_ROOT=value)
    assert SmbStorageService._normalize_root(None, value) == value
    assert SmbStorageService._server_from_root(None, value) == "my-server"
    report = assess_configured_roots(data)
    assert report["ddk_root_leaf_matches_legacy_ddkd_directory"] is True
    assert report["ddk_root_contains_legacy_ddkd_directory"] is True
    assert report["ddk_root_same_host_and_share_as_inspection"] is True
    assert data["STORAGE_DKKD_ROOT"] == value
    assert all(type(v) is bool for v in report.values())


@pytest.mark.parametrize("bad", [
    "\\\\host\\\\share\\\\..\\\\secret",
    "\\\\host\\\\share\\\\.\\\\secret",
    "\\\\host\\\\share//secret",
])
def test_repeated_separator_compatibility_does_not_hide_traversal_or_slashes(bad):
    with pytest.raises(RootProvenanceBlocked):
        unc_components(bad)


def test_redundant_separators_do_not_create_false_legacy_leaf_match():
    data = env(STORAGE_DKKD_ROOT="\\\\my-server\\\\private\\\\unverified-archive")
    report = assess_configured_roots(data)
    assert report["ddk_root_leaf_matches_legacy_ddkd_directory"] is False
    assert report["ddk_root_contains_legacy_ddkd_directory"] is False
    assert report["ddk_root_equals_inspection_root"] is False
