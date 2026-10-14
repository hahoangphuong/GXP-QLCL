"""Private filename-only document sampling; no NAS, DB or binary fixtures."""
from collections import Counter
from copy import deepcopy

import pytest

from tools.triage_ddk_inspection_private_document_candidates import (
    DocumentCandidateManifestBlocked,
    SCHEMA, make_private_document_candidate_manifest,
)


def source_report():
    entries = [
        {"name_private": f"file_{i:02}.pdf", "is_dir": False,
         "extension_private": ".pdf"} for i in range(24)
    ]
    entries += [
        {"name_private": f"text_{i:02}.docx", "is_dir": False,
         "extension_private": ".docx"} for i in range(14)
    ]
    entries += [
        {"name_private": "note.txt", "is_dir": False,
         "extension_private": ".txt"},
        {"name_private": "unknown.xyz", "is_dir": False,
         "extension_private": ".xyz"},
        {"name_private": "not-entered", "is_dir": True,
         "extension_private": ""},
    ]
    for c in entries:
        c.update({
            "inspection_code_token_present": False,
            "source_site_token_present": False,
            "alternate_site_token_present": False,
        })
    return {
        "schema": "GXP_DDK_SINGLE_MISMATCHED_INSPECTION_FOLDER_METADATA_READONLY_V1",
        "status": "SINGLE_SOURCE_MISMATCHED_FOLDER_DIRECT_METADATA_ONLY",
        "approval_status": "NOT_APPROVED",
        "source_year_roots_checked": 1,
        "code_matching_folders_checked": 1,
        "source_year_root_entries_scanned": 130,
        "direct_child_entries_checked": 41,
        "counts": {
            "DIRECT_CHILD_FILES": 40, "DIRECT_CHILD_DIRS": 1,
        },
        "file_binary_contents_read": False,
        "direct_child_subdirectories_entered": False,
        "folder_content_ownership_verified": False,
        "database_connected": False,
        "database_writes": 0,
        "storage_writes": 0,
        "canonical_links_created": 0,
        "private_folder_metadata": {
            "folder_leaf": "source year folder with different Site marker",
            "children": entries,
            "extension_counts": {
                ".pdf": 24, ".docx": 14, ".txt": 1, ".xyz": 1,
            },
        },
    }


def test_candidate_sample_balanced_and_never_claims_case_identity():
    prior = source_report()
    prior["private_folder_metadata"]["children"][8]["name_private"] = "Biên bản Kiểm tra.pdf"
    prior["private_folder_metadata"]["children"][26]["name_private"] = "Báo cáo.docx"
    sample = make_private_document_candidate_manifest(prior)
    assert sample["schema"] == SCHEMA
    assert sample["selected_pdf"] == 3
    assert sample["selected_text_document"] == 2
    assert sample["selected_with_role_hint"] >= 2
    assert sample["source_direct_children"] == 41
    assert sample["available_pdf_or_text_document_candidates"] == 39
    assert sample["document_contents_read"] is False
    assert sample["approval_status"] == "NOT_APPROVED"
    assert sample["folder_content_ownership_verified"] is False
    assert sample["database_writes"] == sample["storage_writes"] == sample["canonical_links_created"] == 0
    selected = sample["private_selected_document_names"]
    assert len(selected) == 5
    assert {c["filename_hint"] for c in selected} >= {
        "INSPECTION_RECORD_HINT", "REPORT_HINT",
    }
    assert all(c["document_kind"] in {"PDF", "TEXT_DOCUMENT"} for c in selected)
    public = {k: v for k, v in sample.items() if not k.startswith("private_")}
    assert "Biên bản" not in str(public) and "Kiểm tra" not in str(public)
    assert "Báo cáo" not in str(public)


@pytest.mark.parametrize("drift", [
    "wrong_schema", "extra_child", "missing_child", "binary_read",
    "unapproved", "unexpected_root", "folder_missing",
    "filename_identity_token", "duplicate_filename", "unsafe_name",
    "extension_drift", "file_dir_mismatch", "storage_write",
])
def test_source_private_manifest_rejects_population_and_identity_drift(drift):
    r = source_report()
    m = r["private_folder_metadata"]
    children = m["children"]
    if drift == "wrong_schema": r["schema"] = "SOME_OTHER_REPORT"
    elif drift == "extra_child": children.append(deepcopy(children[0]))
    elif drift == "missing_child": children.pop()
    elif drift == "binary_read": r["file_binary_contents_read"] = True
    elif drift == "unapproved": r["approval_status"] = "APPROVED"
    elif drift == "unexpected_root": r["source_year_roots_checked"] = 2
    elif drift == "folder_missing": m["folder_leaf"] = ""
    elif drift == "filename_identity_token": children[0]["inspection_code_token_present"] = True
    elif drift == "duplicate_filename": children[1]["name_private"] = children[0]["name_private"]
    elif drift == "unsafe_name": children[0]["name_private"] = "../escape.pdf"
    elif drift == "extension_drift": children[0]["extension_private"] = ".doc"
    elif drift == "file_dir_mismatch": r["counts"]["DIRECT_CHILD_DIRS"] = 2
    elif drift == "storage_write": r["storage_writes"] = 1
    with pytest.raises(DocumentCandidateManifestBlocked):
        make_private_document_candidate_manifest(r)


def test_candidates_do_not_read_one_child_directory_or_non_document_formats():
    r = source_report()
    selected = make_private_document_candidate_manifest(r)["private_selected_document_names"]
    names = {c["filename_private"] for c in selected}
    assert "not-entered" not in names
    assert "note.txt" not in names
    assert "unknown.xyz" not in names


def test_sampling_is_order_stable_for_identical_report():
    r = source_report()
    a = make_private_document_candidate_manifest(r)
    b = make_private_document_candidate_manifest(deepcopy(r))
    assert a == b


@pytest.mark.parametrize("caps", [(0, 2), (4, 2), (3, 0), (3, 3)])
def test_budget_cannot_be_widened(caps):
    with pytest.raises(DocumentCandidateManifestBlocked):
        make_private_document_candidate_manifest(source_report(), max_pdf=caps[0], max_text_document=caps[1])
