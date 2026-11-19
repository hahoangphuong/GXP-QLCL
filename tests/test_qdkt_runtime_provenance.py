"""Runtime bytes, source text and legal/render approval are separate evidence."""
import json

import pytest

from backend.app.document.inspection_qd_kt_vba_bookmark_series import (
    QdKtVbaBookmarkContractError, reconcile_qdkt_i2_bookmarks,
    resolve_vba_bookmark_targets,
)


def test_foreign_gxp_object_cannot_select_an_authority_branch():
    class ForeignGxp:
        def __hash__(self): return hash("GMP")
        def __eq__(self, other): return True
    with pytest.raises(QdKtVbaBookmarkContractError, match="QDKT_GXP_TYPE_UNSUPPORTED"):
        reconcile_qdkt_i2_bookmarks(ForeignGxp(), ["VKN1", "VKN2"])


@pytest.mark.parametrize("names", [["TT1x", "TT1x"], [["TT1x"]], "TT1x"])
def test_ambiguous_or_malformed_physical_names_fail_at_target_owner(names):
    with pytest.raises(QdKtVbaBookmarkContractError, match="QDKT_PHYSICAL_BOOKMARK_SET_INVALID"):
        reconcile_qdkt_i2_bookmarks("GMP", names)


@pytest.mark.parametrize("index", [True, 1.0])
def test_non_integer_numbered_bounds_are_not_source_contract(index):
    with pytest.raises(QdKtVbaBookmarkContractError, match="QDKT_BOOKMARK_BOUNDS_INVALID"):
        resolve_vba_bookmark_targets("Tencoso", ["Tencoso1"], first_index=index, last_index=3)


@pytest.mark.parametrize("change", ["binary_hash", "binding", "operation", "helper", "template"])
def test_runtime_capture_cannot_self_attest_through_metadata(tmp_path, change):
    from backend.app.document.inspection_qd_kt_runtime_provenance import (
        load_runtime_source_evidence, QdKtRuntimeEvidenceBlocked,
    )
    evidence = load_runtime_source_evidence()
    if change == "binary_hash": evidence["artifact_inputs"]["addin"]["sha256"] = "0" * 64
    elif change == "binding": evidence["source_to_runtime_version_binding"] = "BYTE_IDENTICAL_BINDING_PROVEN"
    elif change == "operation": evidence["operation_source_lines"]["QDKT"]["runtime_execution_verified"] = True
    elif change == "helper": evidence["helpers"][0]["module"] = "foreign.bas"
    else: evidence["templates"][0]["bookmark_names"] = evidence["templates"][-1]["bookmark_names"]
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(QdKtRuntimeEvidenceBlocked, match="QDKT_RUNTIME_CAPTURE_DRIFT"):
        load_runtime_source_evidence(path)


@pytest.mark.parametrize("artifact", ["source_zip", "addin", "template_GLP", "template_GMP", "template_GMPbb", "template_GSP"])
def test_substituted_bytes_cannot_be_verified_from_correct_metadata(monkeypatch, artifact):
    from backend.app.document.inspection_qd_kt_runtime_provenance import load_runtime_source_evidence, QdKtRuntimeEvidenceBlocked, validate_runtime_artifact_snapshot
    from tools import qdkt_runtime_source_verification as verifier
    expected = load_runtime_source_evidence()["artifact_inputs"]
    # Matching metadata is deliberately NOT accepted as binary input.
    blobs = {key: b"foreign bytes" for key in expected}
    blobs[artifact] = json.dumps(expected[artifact]).encode()
    with pytest.raises(QdKtRuntimeEvidenceBlocked, match="QDKT_RUNTIME_ARTIFACT_BYTES_MISMATCH"):
        validate_runtime_artifact_snapshot(artifact, blobs[artifact])
    def forbidden(*args, **kwargs): raise AssertionError("extraction preceded byte verification")
    monkeypatch.setattr(verifier, "capture_runtime_sources", forbidden)
    with pytest.raises(QdKtRuntimeEvidenceBlocked, match="QDKT_RUNTIME_ARTIFACT_BYTES_MISMATCH"):
        verifier.verify_runtime_sources(blobs)


@pytest.mark.parametrize("other", ["Cơ sở. ", "cơ sở.", "Co\u031b so\u031b\u0309.", "Cơ sở", "Cơ sở;", "Cơ sở.\n"])
def test_source_equivalence_never_erases_unicode_casing_or_punctuation(other):
    from backend.app.document.inspection_qd_kt_runtime_provenance import compare_source_text
    result = compare_source_text("Cơ sở.", other)
    assert result["comparison"] == "IMPLEMENTATION_DIFFERS"
    assert result["version_binding_verified"] is False


def test_only_line_ending_normalization_is_source_equivalence_not_version_proof():
    from backend.app.document.inspection_qd_kt_runtime_provenance import compare_source_text
    result = compare_source_text("Cơ sở.\r\nX\rY", "Cơ sở.\nX\nY")
    assert result["comparison"] == "CONTENT_EQUIVALENT_VERSION_UNPROVEN"
    assert result["version_binding_verified"] is False


def test_all_14_source_pairs_are_captured_without_promoting_operations():
    from backend.app.document.inspection_qd_kt_transformation_audit import build_qdkt_transformation_audit
    report = build_qdkt_transformation_audit()
    capture = report["runtime_source_provenance"]["capture"]
    assert capture["zip_contains_winapi"] is False
    assert capture["zip_member_count"] == 51 and capture["project_codepage"] == 1252
    assert capture["source_to_runtime_version_binding"] == "UNVERIFIED_VERSION_BINDING"
    assert len(capture["procedures"]) == 14 and len(capture["operation_source_lines"]) == 14
    for row in report["fields"]:
        ref = row["runtime_source_reference"]
        assert ref["source_line_comparison"]["comparison"] == "CONTENT_EQUIVALENT_VERSION_UNPROVEN"
        assert ref["addin_line"] == ref["zip_line"] - 7
        assert row["status"] != "VERIFIED" and ref["runtime_execution_verified"] is False
    assert {r["gxp_type"]: r["bookmark_count"] for r in capture["templates"]} == {"GLP": 22, "GMP": 22, "GMPbb": 14, "GSP": 11}
    assert report["status_counts"] == {"VERIFIED": 0, "PARTIAL": 6, "BLOCKED": 4, "CONTRADICTED": 4}


def test_procedure_extraction_rejects_duplicate_reference_and_preserves_lf():
    from tools.qdkt_runtime_source_verification import _procedure
    from backend.app.document.inspection_qd_kt_runtime_provenance import QdKtRuntimeEvidenceBlocked
    text = 'Public Function Example()\r\n Example = "Cơ sở."\r\nEnd Function'
    assert _procedure(text, "Example")["text"] == text.replace("\r\n", "\n")
    with pytest.raises(QdKtRuntimeEvidenceBlocked, match="QDKT_RUNTIME_PROCEDURE_AMBIGUOUS"):
        _procedure(text + "\n" + text, "Example")


def test_fresh_verifier_cannot_fall_back_to_static_capture(monkeypatch, capsys):
    from tools.audit_qdkt_source_transformations import main
    from tools import qdkt_runtime_source_verification as verifier
    from backend.app.document.inspection_qd_kt_runtime_provenance import QdKtRuntimeEvidenceBlocked
    def unavailable(*args): raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_ARTIFACT_UNAVAILABLE")
    monkeypatch.setattr(verifier, "verify_local_runtime_sources", unavailable)
    assert main(["--verify-local-artifacts"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["audit_blockers"] == ["QDKT_RUNTIME_ARTIFACT_UNAVAILABLE"]
    assert result["ready_to_render"] is False and "runtime_source_provenance" not in result


@pytest.mark.parametrize("value", ["Cơ sở.\r\nĐịa chỉ;", "Co\u031b so\u031b\u0309.", "aBC.  "])
def test_repeated_values_preserve_unicode_linebreaks_casing_and_punctuation(value):
    from backend.app.document.inspection_qd_kt_vba_bookmark_series import plan_repeated_bookmark_value
    op = reconcile_qdkt_i2_bookmarks("GMP", ["Tencoso1", "Tencoso3"])["Tencoso"]
    assert plan_repeated_bookmark_value(op, value) == (("Tencoso1", value), ("Tencoso3", value))


def test_foreign_template_names_do_not_make_unreachable_authority_branch_reachable():
    rows = reconcile_qdkt_i2_bookmarks("GMPbb", ["VKN1", "VKN2", "VKNx", "TT1x"])
    assert rows["VKN"].effective_targets == rows["VKNx"].effective_targets == ()
    assert rows["VKN"].branch_reachable is rows["VKNx"].branch_reachable is False


def test_duplicate_archive_entries_are_not_accepted_as_source_evidence():
    from io import BytesIO
    from zipfile import ZipFile
    from tools.qdkt_runtime_source_verification import _members
    from backend.app.document.inspection_qd_kt_runtime_provenance import QdKtRuntimeEvidenceBlocked
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("WinAPI.bas", "first")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("WinAPI.bas", "second")
    with pytest.raises(QdKtRuntimeEvidenceBlocked, match="QDKT_RUNTIME_ZIP_AMBIGUOUS"):
        _members(stream.getvalue())
