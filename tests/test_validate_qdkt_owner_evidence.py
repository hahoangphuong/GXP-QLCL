"""Offline documentary evidence is never reviewer authentication or Word UAT."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from backend.app.document.inspection_qd_kt_renderer_contract import load_renderer_decision, decision_digest
from tools.validate_qdkt_owner_evidence import validate_package, render_json, render_markdown
from tools import _qdkt_evidence_io as io


def package(tmp_path):
    decision = load_renderer_decision()
    data = decision.model_dump_json().encode()
    (tmp_path / "decision.json").write_bytes(data)
    manifest = {
        "schema_version": "qdkt-owner-evidence-package/v1",
        "decision_ref": "decision",
        "decision_sha256": decision_digest(decision),
        "templates": [{"gxp_type": t.gxp_type} for t in decision.templates],
        "approval_record_refs": [],
        "evidence": [{"ref_id": "decision", "path": "decision.json", "sha256": sha256(data).hexdigest(), "kind": "decision"}],
    }
    save(tmp_path, manifest)
    return manifest


def save(tmp_path, manifest):
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_undecided_package_cannot_authorize_or_claim_word_execution(tmp_path):
    package(tmp_path)
    report = validate_package(tmp_path / "manifest.json")
    assert "QDKT_PACKAGE_DECISION_UNDECIDED" in report["documentary_blockers"]
    assert not report["evidence_complete"]
    assert report["trusted_authorization_verified"] is False
    assert report["word_uat_verified"] is False
    assert report["ready_to_render"] is False
    assert all(row["version_matches_manifest"] is None for row in report["candidates"])
    assert {r["option"] for r in report["owner_checklists"]} == {"ADD_BOOKMARKS", "DEPRECATE_WRITES"}


@pytest.mark.parametrize("change,code", [
    ("missing_variant", "QDKT_PACKAGE_VARIANT_SET_INVALID"),
    ("duplicate_variant", "QDKT_PACKAGE_VARIANT_SET_INVALID"),
    ("digest", "QDKT_PACKAGE_DECISION_DIGEST_CONFLICT"),
    ("traversal", "QDKT_PACKAGE_PATH_UNSAFE"),
    ("duplicate_ref", "QDKT_PACKAGE_REFERENCE_DUPLICATE"),
])
def test_structural_and_identity_failures(tmp_path, change, code):
    manifest = package(tmp_path)
    if change == "missing_variant":
        manifest["templates"].pop()
    elif change == "duplicate_variant":
        manifest["templates"][1] = manifest["templates"][0]
    elif change == "digest":
        manifest["decision_sha256"] = "0" * 64
    elif change == "traversal":
        manifest["evidence"][0]["path"] = "../outside.json"
    else:
        manifest["evidence"].append(manifest["evidence"][0])
    save(tmp_path, manifest)
    assert code in validate_package(tmp_path / "manifest.json")["documentary_blockers"]


def test_duplicate_json_keys_are_rejected(tmp_path):
    (tmp_path / "manifest.json").write_bytes(b'{"schema_version":"one","schema_version":"two"}')
    assert validate_package(tmp_path / "manifest.json")["documentary_blockers"] == ["QDKT_PACKAGE_JSON_DUPLICATE_KEY"]


def test_reports_are_deterministic_and_do_not_write(tmp_path):
    package(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    first, second = (validate_package(tmp_path / "manifest.json") for _ in range(2))
    assert render_json(first) == render_json(second)
    assert render_markdown(first) == render_markdown(second)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def complete_untrusted_package(tmp_path, monkeypatch, option="DEPRECATE_WRITES"):
    """Modeled receipts only. No real owner or Word claim established by test."""
    from test_inspection_qd_kt_renderer_contract import fixture
    from backend.app.document import inspection_qd_kt_renderer_contract as contract
    from backend.app.document.inspection_qd_kt_template_asset_contract import InspectionQdKtTemplateAsset
    from backend.app.document.inspection_qd_kt_renderer_contract import word_uat_digest
    inputs = fixture(tmp_path, option)
    # Offline source registry is independently pinned in production; disposable
    # fixtures cannot match real original-template hashes. Model that root here.
    assets = []
    rows = []
    refs = []
    def add(ref_id, name, kind, data):
        (tmp_path / name).write_bytes(data)
        refs.append({"ref_id": ref_id, "path": name, "kind": kind, "sha256": sha256(data).hexdigest()})
    for t, physical in zip(inputs["decision"].templates, inputs["physical"]):
        from io import BytesIO
        from zipfile import ZipFile
        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"/></Types>')
            archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Synthetic source</w:t></w:r></w:p></w:body></w:document>')
        source = stream.getvalue()
        source_sha = sha256(source).hexdigest()
        assets.append(InspectionQdKtTemplateAsset(t.gxp_type, "source.dotx", "template", "source.dotx", source_sha))
        rows.append(t.model_copy(update={"source_sha256": source_sha}))
        add("source_" + t.gxp_type, "source_" + t.gxp_type + ".dotx", "source_template", source)
        add("candidate_" + t.gxp_type, "candidate_" + t.gxp_type + ".dotx", "candidate_template", physical.candidate_bytes)
    monkeypatch.setattr(contract, "load_inspection_qd_kt_template_assets", lambda: tuple(assets))
    decision = inputs["decision"].model_copy(update={"templates": tuple(rows)})
    digest = decision_digest(decision)
    uat_rows = []
    templates = []
    for uat in inputs["word_uat"]:
        output = ("synthetic output " + uat.gxp_type).encode()
        screenshot = ("synthetic screenshot " + uat.gxp_type).encode()
        uat = uat.model_copy(update={"contract_sha256": digest, "output_sha256": sha256(output).hexdigest(), "screenshot_refs": ("screen_" + uat.gxp_type,)})
        uat_rows.append(uat)
        add("uat_" + uat.gxp_type, "uat_" + uat.gxp_type + ".json", "word_uat", uat.model_dump_json().encode())
        add("output_" + uat.gxp_type, "output_" + uat.gxp_type + ".docx", "uat_output", output)
        add("screen_" + uat.gxp_type, "screen_" + uat.gxp_type + ".png", "uat_screenshot", screenshot)
        templates.append({"gxp_type": uat.gxp_type, "source_ref": "source_" + uat.gxp_type, "candidate_ref": "candidate_" + uat.gxp_type, "candidate_version": uat.template_version, "word_uat_ref": "uat_" + uat.gxp_type, "word_output_ref": "output_" + uat.gxp_type})
    approval_refs = []
    for record in inputs["trusted_approvals"].values():
        evidence_ref = "support_" + record.purpose
        record = record.model_copy(update={"contract_sha256": digest, "evidence_ref": evidence_ref, "subject_sha256": word_uat_digest(uat_rows) if record.purpose == "WORD_UAT" else None})
        ref_id = "record_" + record.purpose
        approval_refs.append(ref_id)
        add(ref_id, ref_id + ".json", "approval_record", record.model_dump_json().encode())
        add(evidence_ref, evidence_ref + ".txt", "supporting_document", b"Synthetic untrusted attestation")
    add("decision", "decision.json", "decision", decision.model_dump_json().encode())
    manifest = {"schema_version": "qdkt-owner-evidence-package/v1", "decision_ref": "decision", "decision_sha256": digest, "templates": templates, "approval_record_refs": approval_refs, "evidence": refs}
    save(tmp_path, manifest)
    return manifest


def edit_ref(tmp_path, manifest, ref_id, change):
    ref = next(r for r in manifest["evidence"] if r["ref_id"] == ref_id)
    path = tmp_path / ref["path"]
    content = json.loads(path.read_bytes())
    change(content)
    data = json.dumps(content).encode()
    path.write_bytes(data)
    ref["sha256"] = sha256(data).hexdigest()
    save(tmp_path, manifest)


@pytest.mark.parametrize("option", ["ADD_BOOKMARKS", "DEPRECATE_WRITES"])
def test_even_forged_complete_documentation_does_not_verify_authority_or_word(tmp_path, monkeypatch, option):
    manifest = complete_untrusted_package(tmp_path, monkeypatch, option)
    result = validate_package(tmp_path / "manifest.json")
    assert result["documentary_blockers"] == []
    assert result["evidence_complete"] is True
    assert result["trusted_authorization_verified"] is False
    assert result["word_uat_verified"] is False
    assert result["ready_to_render"] is False
    assert "QDKT_PACKAGE_AUTHORIZATION_NOT_VERIFIED" in result["trust_blockers"]
    # A valid selected decision without any documentary approvals stays blocked.
    manifest["approval_record_refs"] = []
    save(tmp_path, manifest)
    blocked = validate_package(tmp_path / "manifest.json")
    assert "QDKT_PACKAGE_APPROVAL_DOCUMENT_MISSING:LEGAL_TEMPLATE" in blocked["documentary_blockers"]
    assert not blocked["evidence_complete"]


@pytest.mark.parametrize("change,code", [
    ("synthetic", "QDKT_PACKAGE_WORD_UAT_NOT_ATTESTED:GLP"),
    ("unverified", "QDKT_PACKAGE_WORD_UAT_NOT_ATTESTED:GLP"),
    ("timezone", "QDKT_PACKAGE_WORD_UAT_TIME_INVALID"),
    ("approval_timezone", "QDKT_PACKAGE_APPROVAL_RECORD_INVALID"),
    ("subject", "QDKT_PACKAGE_UAT_SUBJECT_CONFLICT"),
    ("late_approval", "QDKT_PACKAGE_UAT_ACCEPTANCE_TIME_CONFLICT"),
    ("version", "QDKT_PACKAGE_CANDIDATE_VERSION_CONFLICT:GLP"),
    ("candidate_sha", "QDKT_PACKAGE_CANDIDATE_TEMPLATE_SHA_CONFLICT:GLP"),
    ("corrupt", "QDKT_PACKAGE_TEMPLATE_BINARY_INVALID:GLP:candidate_template"),
    ("purpose", "QDKT_PACKAGE_APPROVAL_RECORD_CONFLICT"),
    ("duplicate_uat", "QDKT_PACKAGE_WORD_UAT_SET_INCOMPLETE"),
    ("forged_flag", "QDKT_PACKAGE_APPROVAL_RECORD_INVALID"),
])
def test_documentary_integrity_conflicts(tmp_path, monkeypatch, change, code):
    manifest = complete_untrusted_package(tmp_path, monkeypatch)
    if change in {"synthetic", "unverified", "timezone"}:
        values = {"synthetic": {"evidence_origin": "SYNTHETIC"}, "unverified": {"evidence_origin": "UNVERIFIED"}, "timezone": {"executed_at": "2026-01-03T12:00:00+00:60"}}
        edit_ref(tmp_path, manifest, "uat_GLP", lambda obj: obj.update(values[change]))
    elif change in {"approval_timezone", "subject", "late_approval", "purpose", "forged_flag"}:
        values = {"approval_timezone": {"approved_at": "2026-01-03T13:00:00"}, "subject": {"subject_sha256": "0" * 64}, "late_approval": {"approved_at": "2025-01-01T00:00:00Z"}, "purpose": {"purpose": "LEGAL_TEMPLATE"}, "forged_flag": {"approved": True}}
        edit_ref(tmp_path, manifest, "record_WORD_UAT", lambda obj: obj.update(values[change]))
    elif change == "version":
        manifest["templates"][0]["candidate_version"] = "wrong"
        save(tmp_path, manifest)
    elif change == "duplicate_uat":
        manifest["templates"][1]["word_uat_ref"] = "uat_GLP"
        save(tmp_path, manifest)
    else:
        ref = next(r for r in manifest["evidence"] if r["ref_id"] == "candidate_GLP")
        (tmp_path / ref["path"]).write_bytes(b"corrupted")
        if change == "candidate_sha":
            ref["sha256"] = sha256(b"corrupted").hexdigest()
            save(tmp_path, manifest)
        elif change == "corrupt":
            # Pin malformed bytes consistently to reach the shared DOTX parser.
            ref["sha256"] = sha256(b"corrupted").hexdigest()
            edit_ref(tmp_path, manifest, "decision", lambda obj: obj["templates"][0].update({"candidate_sha256": ref["sha256"]}))
    result = validate_package(tmp_path / "manifest.json")
    assert code in result["documentary_blockers"]
    assert not result["evidence_complete"] and not result["ready_to_render"]


@pytest.mark.parametrize("bad_path", ["../secret", "/absolute", "C:/secret", "dir\\secret", "file:stream", "CON.txt", "CON .txt", "dir/../secret", "dir//file"])
def test_forbidden_paths_never_read_outside(tmp_path, bad_path):
    manifest = package(tmp_path)
    manifest["evidence"][0]["path"] = bad_path
    save(tmp_path, manifest)
    assert "QDKT_PACKAGE_PATH_UNSAFE" in validate_package(tmp_path / "manifest.json")["documentary_blockers"]


def test_symlink_and_hardlink_fail_closed(tmp_path):
    manifest = package(tmp_path)
    original = tmp_path / "decision.json"
    linked = tmp_path / "linked.json"
    # File symlinks may require Windows developer mode. A hardlink is always
    # independently checked and does not need that privilege.
    os.link(original, linked)
    manifest["evidence"][0]["path"] = linked.name
    save(tmp_path, manifest)
    assert any("FILE_TYPE_INVALID" in b for b in validate_package(tmp_path / "manifest.json")["documentary_blockers"])
    linked.unlink()
    try:
        linked.symlink_to(original)
    except OSError:
        if os.name != "nt":
            raise
        # Actual directory junction exercises the Windows reparse boundary.
        target = tmp_path / "real"
        target.mkdir()
        (target / "decision.json").write_bytes(original.read_bytes())
        subprocess.run(["cmd", "/c", "mklink", "/J", str(tmp_path / "junction"), str(target)], check=True, capture_output=True)
        manifest["evidence"][0]["path"] = "junction/decision.json"
    save(tmp_path, manifest)
    assert any("LINK_FORBIDDEN" in b or "FILE_UNAVAILABLE" in b for b in validate_package(tmp_path / "manifest.json")["documentary_blockers"])


def test_limits_corrupt_json_and_nested_duplicate_keys(tmp_path, monkeypatch):
    package(tmp_path)
    monkeypatch.setattr("tools.validate_qdkt_owner_evidence.JSON_LIMIT", 8)
    assert "QDKT_PACKAGE_FILE_TOO_LARGE" in validate_package(tmp_path / "manifest.json")["documentary_blockers"]
    monkeypatch.undo()
    (tmp_path / "manifest.json").write_bytes(b"\xffbad-json")
    assert validate_package(tmp_path / "manifest.json")["documentary_blockers"] == ["QDKT_PACKAGE_JSON_INVALID"]
    manifest = package(tmp_path)
    data = b'{"nested":{"approved":true,"approved":false}}'
    (tmp_path / "decision.json").write_bytes(data)
    manifest["evidence"][0]["sha256"] = sha256(data).hexdigest()
    save(tmp_path, manifest)
    assert "QDKT_PACKAGE_JSON_DUPLICATE_KEY" in validate_package(tmp_path / "manifest.json")["documentary_blockers"]


def test_read_snapshot_detects_in_place_change_and_does_not_reopen(tmp_path, monkeypatch):
    package(tmp_path)
    original = io.os.read
    count = []
    def changing(fd, size):
        data = original(fd, size)
        if not count:
            count.append(1)
            # Model concurrent modification observed by fstat, without writing
            # through the validator or requiring Windows sharing violation.
            observed = io.os.fstat(fd)
            class Changed:
                st_mode = observed.st_mode
                st_nlink = observed.st_nlink
                st_size = observed.st_size
                st_dev = observed.st_dev
                st_ino = observed.st_ino
                st_mtime_ns = observed.st_mtime_ns + 1
                st_ctime_ns = observed.st_ctime_ns
            monkeypatch.setattr(io.os, "fstat", lambda _: Changed())
        return data
    monkeypatch.setattr(io.os, "read", changing)
    assert "QDKT_PACKAGE_FILE_CHANGED" in validate_package(tmp_path / "manifest.json")["documentary_blockers"]


def test_cli_redacts_payloads_and_always_exits_blocked(tmp_path):
    package(tmp_path)
    result = subprocess.run([sys.executable, "-m", "tools.validate_qdkt_owner_evidence", "--manifest", str(tmp_path / "manifest.json"), "--format", "markdown"], capture_output=True, text=True)
    assert result.returncode == 2
    assert '"ready_to_render": false' in result.stdout
    assert str(tmp_path) not in result.stdout
    assert not result.stderr


def test_zip_envelope_is_bounded_before_all_story_parsing(tmp_path, monkeypatch):
    from io import BytesIO
    from zipfile import ZipFile
    manifest = complete_untrusted_package(tmp_path, monkeypatch)
    path = tmp_path / "candidate_GLP.dotx"
    stream = BytesIO(path.read_bytes())
    with ZipFile(stream, "a") as archive:
        for i in range(257):
            archive.writestr(f"extra/{i}.xml", b"")
    data = stream.getvalue()
    path.write_bytes(data)
    ref = next(r for r in manifest["evidence"] if r["ref_id"] == "candidate_GLP")
    ref["sha256"] = sha256(data).hexdigest()
    edit_ref(tmp_path, manifest, "decision", lambda obj: obj["templates"][0].update({"candidate_sha256": ref["sha256"]}))
    result = validate_package(tmp_path / "manifest.json")
    assert "QDKT_PACKAGE_TEMPLATE_BINARY_INVALID:GLP:candidate_template" in result["documentary_blockers"]


def test_no_writes_or_runtime_side_effects_and_one_acquisition_per_file(tmp_path, monkeypatch):
    manifest = package(tmp_path)
    from sqlalchemy.orm import Session
    from backend.app.document import service
    def forbidden(*args, **kwargs):
        raise AssertionError("offline validator crossed mutation/runtime boundary")
    for method in ("add", "flush", "commit", "execute", "delete"):
        monkeypatch.setattr(Session, method, forbidden)
    for name in vars(service):
        if "render" in name or "generate" in name:
            monkeypatch.setattr(service, name, forbidden)
    for method in ("write_stream", "read_stream"):
        monkeypatch.setattr(service.LocalStorageService, method, forbidden)
    for name in ("write_bytes", "write_text", "mkdir", "unlink", "rename"):
        monkeypatch.setattr(Path, name, forbidden)
    for name in ("write", "mkdir", "remove", "rename", "unlink"):
        monkeypatch.setattr(os, name, forbidden)
    from tools import validate_qdkt_owner_evidence as owner
    original = owner.read_evidence
    acquisitions = []
    def record(root, relative, limit):
        acquisitions.append(relative)
        return original(root, relative, limit)
    monkeypatch.setattr(owner, "read_evidence", record)
    result = owner.validate_package(tmp_path / "manifest.json")
    assert result["decision_sha256"] == manifest["decision_sha256"]
    assert acquisitions == ["manifest.json", "decision.json"]


def test_parser_consumes_captured_bytes_after_path_replacement(tmp_path, monkeypatch):
    manifest = package(tmp_path)
    from tools import validate_qdkt_owner_evidence as owner
    original = owner.read_evidence
    def swap_after_acquisition(root, relative, limit):
        data = original(root, relative, limit)
        if relative == "decision.json":
            (root / relative).write_bytes(b"not the captured decision")
        return data
    monkeypatch.setattr(owner, "read_evidence", swap_after_acquisition)
    result = owner.validate_package(tmp_path / "manifest.json")
    assert result["decision_sha256"] == manifest["decision_sha256"]
    assert "QDKT_PACKAGE_SCHEMA_INVALID" not in result["documentary_blockers"]


def test_reference_alias_and_missing_and_wrong_kind(tmp_path):
    manifest = package(tmp_path)
    manifest["evidence"].append({**manifest["evidence"][0], "ref_id": "alias"})
    save(tmp_path, manifest)
    assert "QDKT_PACKAGE_REFERENCE_PATH_CONFLICT" in validate_package(tmp_path / "manifest.json")["documentary_blockers"]
    manifest = package(tmp_path)
    manifest["decision_ref"] = "absent"
    save(tmp_path, manifest)
    assert "QDKT_PACKAGE_REFERENCE_KIND_OR_ID_INVALID:decision" in validate_package(tmp_path / "manifest.json")["documentary_blockers"]
    manifest = package(tmp_path)
    manifest["evidence"][0]["kind"] = "approval_record"
    save(tmp_path, manifest)
    assert "QDKT_PACKAGE_DECISION_UNAVAILABLE" in validate_package(tmp_path / "manifest.json")["documentary_blockers"]


def test_manifest_unknown_flag_and_evidence_oversize(tmp_path, monkeypatch):
    manifest = package(tmp_path)
    manifest["approved"] = True
    save(tmp_path, manifest)
    assert validate_package(tmp_path / "manifest.json")["documentary_blockers"] == ["QDKT_PACKAGE_SCHEMA_INVALID"]
    manifest = package(tmp_path)
    ref = {"ref_id": "huge", "path": "huge.bin", "kind": "supporting_document", "sha256": sha256(b"123456789").hexdigest()}
    manifest["evidence"].append(ref)
    (tmp_path / "huge.bin").write_bytes(b"123456789")
    save(tmp_path, manifest)
    monkeypatch.setattr("tools.validate_qdkt_owner_evidence.FILE_LIMIT", 8)
    assert "QDKT_PACKAGE_FILE_TOO_LARGE:huge" in validate_package(tmp_path / "manifest.json")["documentary_blockers"]


def test_linked_manifest_or_parent_is_never_followed(tmp_path):
    package(tmp_path)
    alias = tmp_path / "alias"
    real = tmp_path / "real"
    real.mkdir()
    (real / "manifest.json").write_bytes((tmp_path / "manifest.json").read_bytes())
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(real)], check=True, capture_output=True)
    else:
        alias.symlink_to(real, target_is_directory=True)
    result = validate_package(alias / "manifest.json")
    assert result["source_manifest_sha256"] is None
    assert any("LINK_FORBIDDEN" in b or "FILE_UNAVAILABLE" in b for b in result["documentary_blockers"])


def test_os_reader_anchors_or_locks_against_directory_replacement(tmp_path, monkeypatch):
    root = tmp_path / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (nested / "evidence.txt").write_bytes(b"captured bytes")
    if os.name == "nt":
        original = io.os.read
        attempts = []
        def attempt_write(fd, size):
            if not attempts:
                attempts.append(1)
                with pytest.raises(PermissionError):
                    (nested / "evidence.txt").write_bytes(b"substituted")
                with pytest.raises(PermissionError):
                    nested.rename(root / "moved")
            return original(fd, size)
        monkeypatch.setattr(io.os, "read", attempt_write)
    else:
        original = io.os.open
        # Keep supports_dir_fd capability testing valid for the wrapped open.
        monkeypatch.setattr(io.os, "supports_dir_fd", io.os.supports_dir_fd | {original})
        def swap(path, flags, **kwargs):
            fd = original(path, flags, **kwargs)
            if path == "nested":
                nested.rename(root / "moved")
                outside = tmp_path / "outside"
                outside.mkdir()
                (outside / "evidence.txt").write_bytes(b"outside bytes")
                nested.symlink_to(outside, target_is_directory=True)
            return fd
        monkeypatch.setattr(io.os, "open", swap)
        monkeypatch.setattr(io.os, "supports_dir_fd", io.os.supports_dir_fd | {swap})
    assert io.read_evidence(root, "nested/evidence.txt", 100) == b"captured bytes"
