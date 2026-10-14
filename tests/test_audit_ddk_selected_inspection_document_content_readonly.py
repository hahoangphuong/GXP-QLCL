"""Content-evidence reads only five selected files; never promotes folder binding."""
from contextlib import contextmanager
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
import zipfile

import pytest

import tools.audit_ddk_selected_inspection_document_content_readonly as owner
from backend.app.storage.smb import SmbStorageService
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
        {"name_private": "not-entered", "is_dir": True, "extension_private": ""},
    ]
    for c in entries:
        c.update({"inspection_code_token_present": False,
                  "source_site_token_present": False,
                  "alternate_site_token_present": False})
    return {
        "schema": "GXP_DDK_SINGLE_MISMATCHED_INSPECTION_FOLDER_METADATA_READONLY_V1",
        "status": "SINGLE_SOURCE_MISMATCHED_FOLDER_DIRECT_METADATA_ONLY",
        "approval_status": "NOT_APPROVED",
        "source_year_roots_checked": 1,
        "code_matching_folders_checked": 1,
        "source_year_root_entries_scanned": 130,
        "direct_child_entries_checked": 41,
        "counts": {"DIRECT_CHILD_FILES": 40, "DIRECT_CHILD_DIRS": 1},
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
            "extension_counts": {".pdf": 24, ".docx": 14, ".txt": 1, ".xyz": 1},
        },
    }
from tools.triage_ddk_inspection_private_document_candidates import make_private_document_candidate_manifest


def request():
    return {
        "schema": "GXP_DDK_CASE_INSPECTION_PHYSICAL_SOURCE_REQUEST_V1",
        "approval_status": "NOT_APPROVED",
        "source_site_legacy_id": 101,
        "observed_site_legacy_id_unverified": 202,
        "inspection_code": "KT-555-GMP",
    }


def _metadata():
    r = source_report()
    r["private_folder_metadata"].update({
        "source_year": 2024, "source_site_legacy_id": 101,
        "observed_other_site_legacy_id": 202,
        "inspection_legacy_code": "KT-555-GMP",
        "folder_leaf": "example (ID-202) (KT-555-GMP)",
    })
    r["source_year_root_entries_scanned"] = 130
    return r


def _docx(data: str) -> bytes:
    buf = BytesIO()
    xml = ('<?xml version="1.0"?><w:document '
           'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:body><w:p><w:r><w:t>' + data +
           '</w:t></w:r></w:p></w:body></w:document>')
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buf.getvalue()


def test_docx_exact_code_text_is_observation_only():
    result = owner.classify_document_bytes(
        _docx("Report KT-555-GMP (ID-101)"),
        extension=".docx", inspection_code="KT-555-GMP",
        source_site_id=101, alternate_site_id=202,
    )
    assert result["format_status"] == "TEXT_AVAILABLE"
    assert result["exact_inspection_code_in_extractable_text"] is True
    assert result["source_site_id_marker_in_extractable_text"] is True
    assert result["alternate_site_id_marker_in_extractable_text"] is False
    assert result["content_ownership_verified"] is False
    assert "Report" not in str(result)


def test_txt_does_not_infer_ownership_from_unrelated_bytes():
    result = owner.classify_document_bytes(
        b"A report with no Case identity",
        extension=".txt", inspection_code="KT-555-GMP",
        source_site_id=101, alternate_site_id=202,
    )
    assert result["format_status"] == "TEXT_AVAILABLE"
    assert result["exact_inspection_code_in_extractable_text"] is False
    assert result["content_ownership_verified"] is False


@pytest.mark.parametrize("ext,raw,status", [
    (".pdf", b"not a pdf", "FORMAT_MISMATCH"),
    (".docx", b"not a zip", "FORMAT_MISMATCH"),
    (".doc", b"legacy doc data", "UNSUPPORTED_FORMAT"),
    (".txt", b"\xff\xfe", "UNSUPPORTED_ENCODING"),
    (".rtf", b"{\\rtf1 aaa}", "UNSUPPORTED_FORMAT"),
])
def test_no_false_negative_on_unsupported_or_malformed_formats(ext,raw,status):
    result = owner.classify_document_bytes(
        raw,extension=ext,inspection_code="KT-555-GMP",
        source_site_id=101,alternate_site_id=202,
    )
    assert result["format_status"] == status
    assert result["exact_inspection_code_in_extractable_text"] is False
    assert result["content_ownership_verified"] is False


@pytest.mark.parametrize("case", ["same_site", "unknown_extension", "oversize"])
def test_pure_parser_requires_bounded_source_identity(case):
    options={"data":b"x","extension":".txt","inspection_code":"KT-555-GMP",
             "source_site_id":101,"alternate_site_id":202}
    if case=="same_site":options["alternate_site_id"]=101
    elif case=="unknown_extension":options["extension"]=".exe"
    else:options["data"]=b"x"*(owner.MAX_SINGLE_BYTES+1)
    with pytest.raises(owner.ContentSignalAuditBlocked):
        owner.classify_document_bytes(**options)


def _fake_storage(monkeypatch, prior, *, changed=False):
    storage=object.__new__(SmbStorageService)
    storage.inspection_root="fake"
    folder=prior["private_folder_metadata"]["folder_leaf"]
    root="fake/2024"
    target=root+"/"+folder
    filenames={x["name_private"] for x in prior["private_folder_metadata"]["children"]
               if not x["is_dir"]}
    storage._join_root=lambda path,value:path+"/"+value
    writes=[]
    def open_file(path,mode):
        assert mode=="rb" and path.rsplit("/",1)[-1] in filenames
        @contextmanager
        def cm():
            yield BytesIO(b"small synthetic content")
        return cm()
    def stat(path):
        return SimpleNamespace(st_size=len(b"small synthetic content"))
    def classify(*a,**k):
        fresh=deepcopy(prior)
        if changed:
            fresh["counts"]["DIRECT_CHILD_FILES"] += 1
        return fresh
    monkeypatch.setattr(owner,"smbclient",SimpleNamespace(open_file=open_file,stat=stat))
    monkeypatch.setattr(owner,"smbpath",SimpleNamespace(
        isdir=lambda path:path==target,
        isfile=lambda path:path.startswith(target+"/") and path.rsplit("/",1)[-1] in filenames
    ))
    monkeypatch.setattr(owner,"classify_exact_folder_metadata_readonly",classify)
    return storage


def test_only_source_selected_five_direct_files_read_and_not_approved(monkeypatch):
    r=_metadata()
    selected=make_private_document_candidate_manifest(r)
    storage=_fake_storage(monkeypatch,r)
    result=owner.inspect_selected_direct_children_readonly(
        storage,prior_metadata=r,sample=selected,source_request=request())
    assert result["source_bound_files_selected"]==5
    assert result["file_contents_read_count"]==5
    assert result["case_ownership_proven"] is False
    assert result["folder_mapping_approved"] is False
    assert result["database_writes"]==result["storage_writes"]==result["canonical_links_created"]==0
    assert result["approval_status"]=="NOT_APPROVED"
    assert "small synthetic" not in str(result)


def test_changed_parent_metadata_blocks_before_content_read(monkeypatch):
    r=_metadata()
    selected=make_private_document_candidate_manifest(r)
    storage=_fake_storage(monkeypatch,r,changed=True)
    with pytest.raises(owner.ContentSignalAuditBlocked):
        owner.inspect_selected_direct_children_readonly(
            storage,prior_metadata=r,sample=selected,source_request=request())


def test_tampered_sample_blocks_before_content_read(monkeypatch):
    r=_metadata()
    selected=make_private_document_candidate_manifest(r)
    selected["private_selected_document_names"][0]["filename_private"]="wrong.pdf"
    storage=_fake_storage(monkeypatch,r)
    with pytest.raises(owner.ContentSignalAuditBlocked):
        owner.inspect_selected_direct_children_readonly(
            storage,prior_metadata=r,sample=selected,source_request=request())
