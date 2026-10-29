"""Static byte/encoding evidence, not a build or loaded-runtime attestation."""
from hashlib import sha256
import re
from xml.etree import ElementTree

from backend.app.document.inspection_qd_kt_runtime_provenance import (
    validate_runtime_artifact_bytes, QdKtRuntimeEvidenceBlocked, RUNTIME_EVIDENCE_SHA256,
)
from tools.qdkt_runtime_source_verification import _members, _extract_addin, _procedure
from tools.trace_inspection_qd_kt_vba import _decode

WORKBOOK_SHA256 = "c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d"


def capture_encoding_evidence(artifacts: dict[str, bytes]) -> dict:
    snapshots = validate_runtime_artifact_bytes(artifacts)
    exported = _members(snapshots["source_zip"])
    package = _members(snapshots["addin"])
    app_xml = package["docProps/app.xml"]
    app = ElementTree.fromstring(app_xml)
    ns = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
    modules, codepage = _extract_addin(snapshots["addin"])
    result = []
    for module, procedure in (("RecordForm.frm", "Get_Tpl"), ("TTVForm.frm", "Get_TTV2")):
        raw = exported[module]
        reviewed = _procedure(_decode(raw), procedure)
        runtime = _procedure(modules[module], procedure)
        raw_lines = raw.splitlines()
        left, right = reviewed["text"].split("\n"), runtime["text"].split("\n")
        if len(left) != len(right):
            raise QdKtRuntimeEvidenceBlocked("QDKT_ENCODING_LINE_ALIGNMENT_UNPROVEN")
        differences, current_case = [], None
        for offset, (old, observed) in enumerate(zip(left, right, strict=True)):
            case = re.match(r"\s*Case\s+(\d+)\b", old, re.I)
            if case:
                current_case = int(case.group(1))
            if old == observed:
                continue
            raw_line = raw_lines[reviewed["start_line"] - 1 + offset]
            if raw_line.decode("cp1258") != old or raw_line.decode("cp1252") != observed:
                raise QdKtRuntimeEvidenceBlocked("QDKT_ENCODING_COMPARISON_CHANGED")
            differences.append({
                "zip_line": reviewed["start_line"] + offset, "addin_line": runtime["start_line"] + offset,
                "raw_hex": raw_line.hex(), "raw_sha256": sha256(raw_line).hexdigest(),
                "cp1258_text": old, "cp1252_text": observed,
                "differing_byte_decodes": [{"offset": i, "byte_hex": f"{b:02x}",
                    "cp1258_codepoint": f"U+{ord(bytes([b]).decode('cp1258')):04X}",
                    "cp1252_codepoint": f"U+{ord(bytes([b]).decode('cp1252')):04X}"}
                    for i, b in enumerate(raw_line) if bytes([b]).decode("cp1258") != bytes([b]).decode("cp1252")],
                "reachability": "NOT_CASE_2" if procedure == "Get_Tpl" else "I2_REACHABLE_FAILURE_HANDLER_NOT_PROVEN_EXECUTED",
                "case": current_case,
            })
        if not differences or procedure == "Get_Tpl" and any(row["case"] == 2 for row in differences):
            raise QdKtRuntimeEvidenceBlocked("QDKT_ENCODING_SCOPE_CHANGED")
        result.append({"module": module, "procedure": procedure, "category": "ENCODING_AMBIGUOUS",
            "zip_raw_module_sha256": sha256(raw).hexdigest(), "zip_lines": [reviewed["start_line"], reviewed["end_line"]],
            "addin_lines": [runtime["start_line"], runtime["end_line"]], "differences": differences,
            "direct_qdkt_word_text_write": False,
            "scope": "non-i2 template/filename branches" if procedure == "Get_Tpl" else "error message in called team function; do not classify as unreachable from i=2",
            "export_codepage_attested": False, "normalization": "LF only; no Unicode or punctuation normalization"})
    return {"source_capture_pin": RUNTIME_EVIDENCE_SHA256, "addin_project_codepage": codepage,
        "package_metadata": {"app_properties_sha256": sha256(app_xml).hexdigest(),
            "application": app.findtext(ns + "Application"), "producer_app_version": app.findtext(ns + "AppVersion"),
            "custom_properties_present": "docProps/custom.xml" in package,
            "manifest_named_members": sorted(n for n in package if any(word in n.lower() for word in ("manifest", "release", "build", "version"))),
            "scope": "Office producer metadata only; not an attested VBA build, distribution or loaded Excel version"},
        "zip_decoder": "tools.trace_inspection_qd_kt_vba._decode: utf-8-sig then cp1258 then cp1252 then latin-1",
        "procedures": result, "version_binding": "UNVERIFIED_VERSION_BINDING"}


def capture_loader_evidence(workbook: bytes) -> dict:
    if type(workbook) is not bytes or sha256(workbook).hexdigest() != WORKBOOK_SHA256:
        raise QdKtRuntimeEvidenceBlocked("QDKT_WORKBOOK_BYTES_MISMATCH")
    modules, codepage = _extract_addin(workbook)
    proc = _procedure(modules["Module1.bas"], "Load_Lib")
    # Keep no network locator in this metadata; original source hash anchors it.
    lines = proc["text"].split("\n")
    refs = [{"line": proc["start_line"] + i, "text": line} for i, line in enumerate(lines)
            if "Application.Workbooks(fname)" in line or "Application.Workbooks.Open" in line]
    if len(refs) != 3:
        raise QdKtRuntimeEvidenceBlocked("QDKT_WORKBOOK_LOADER_CHANGED")
    return {"artifact": "legacy/Danh sách Kiểm tra GPs.xlsb", "sha256": WORKBOOK_SHA256, "size_bytes": len(workbook),
        "project_codepage": codepage, "module": "Module1.bas", "procedure": "Load_Lib",
        "lines": [proc["start_line"], proc["end_line"]], "procedure_utf8_lf_sha256": sha256(proc["text"].encode()).hexdigest(),
        "lookup_and_open_references": refs, "loaded_runtime_category": "RUNTIME_IDENTITY_UNVERIFIED",
        "checks_checksum_or_build_identity": False,
        "limitation": "Source observation only: an already-open same-name add-in or alternate configured path may supply the invoked runtime."}
