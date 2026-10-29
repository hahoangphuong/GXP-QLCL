"""Optional offline primary-byte extraction; never executes Excel/VBA/Word.

oletools 0.60.2 is an optional analyst tool, not an application dependency.
The normal repository audit and CI tests use the pinned capture without it.
"""
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
import re
from xml.etree import ElementTree
from zipfile import ZipFile, BadZipFile

from backend.app.document.inspection_qd_kt_runtime_provenance import (
    QdKtRuntimeEvidenceBlocked, normalized_source, compare_source_text,
    load_runtime_source_evidence, validate_runtime_artifact_bytes, validate_runtime_capture,
)
from backend.app.document.inspection_qd_kt_provenance_gate import load_qdkt_source_provenance
from backend.app.document.inspection_qd_kt_template_asset_contract import load_inspection_qd_kt_template_assets
from backend.app.document.inspection_qd_kt_dotx_binary_audit import inspect_qdkt_dotx_bytes

PROCEDURES = {
    "Module1.bas": ("TaoQDKT_KHKT", "FormatDateS"),
    "RecordForm.frm": ("CreateFile", "Get_Tpl", "Tao_QDKT_KHKT_BBKT", "GetTT_Ktra", "Get_VKN", "Replace_Bookmark", "Delete_Bookmark"),
    "TTVForm.frm": ("Get_TTV2", "Get_TTV_List3"),
    "WinAPI.bas": ("DelLastIf_Ins", "LCase_FirstChar", "Del_LastPeriod"),
}
HELPERS = PROCEDURES["WinAPI.bas"]


def _members(data: bytes) -> dict[str, bytes]:
    """Read bounded ZIP entries in memory; no extraction to filesystem."""
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [row.filename for row in entries]
            if len(entries) > 512 or len(set(names)) != len(names):
                raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_ZIP_AMBIGUOUS")
            if any("\\" in name or ":" in name or name.startswith("/") or ".." in PurePosixPath(name).parts for name in names):
                raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_ZIP_UNSAFE")
            if any(row.file_size > 16 * 1024 * 1024 or row.flag_bits & 1 for row in entries) or sum(row.file_size for row in entries) > 64 * 1024 * 1024:
                raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_ZIP_LIMIT")
            return {row.filename: archive.read(row) for row in entries if not row.is_dir()}
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_ZIP_INVALID") from exc


def _procedure(text: str, name: str) -> dict:
    lines = normalized_source(text).split("\n")
    pattern = re.compile(r"^\s*(?:(?:Public|Private|Friend)\s+)?(?:Sub|Function)\s+" + re.escape(name) + r"\b", re.I)
    starts = [i for i, line in enumerate(lines) if pattern.match(line)]
    if len(starts) != 1:
        raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_PROCEDURE_AMBIGUOUS")
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^\s*End\s+(?:Sub|Function)\s*$", lines[i], re.I)), None)
    if end is None:
        raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_PROCEDURE_INCOMPLETE")
    return {"start_line": start + 1, "end_line": end + 1, "text": "\n".join(lines[start:end + 1])}


def _extract_addin(data: bytes) -> tuple[dict[str, str], int]:
    try:
        from importlib.metadata import version
        from oletools.olevba import VBA_Parser, VBA_Project
    except ImportError as exc:
        raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_EXTRACTOR_UNAVAILABLE") from exc
    if version("oletools") != "0.60.2":
        raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_EXTRACTOR_VERSION_UNREVIEWED")
    parser = VBA_Parser("addin.xlam", data=data)
    try:
        codepages = []
        for subfile in parser.ole_subfiles:
            for root, project_path, dir_path in subfile.find_vba_projects():
                project = VBA_Project(subfile.ole_file, root, project_path, dir_path, relaxed=False)
                codepages.append(project.codepage)
        if len(codepages) != 1:
            raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_PROJECT_AMBIGUOUS")
        modules = {}
        for _, _, name, code in parser.extract_macros():
            if name.casefold() in {n.casefold() for n in modules}:
                raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_MODULE_AMBIGUOUS")
            modules[name] = normalized_source(code)
        return modules, codepages[0]
    finally:
        parser.close()


def capture_runtime_sources(artifacts: dict[str, bytes]) -> dict:
    """Internal capture stage; public verification validates bytes before calling.

    Generating this record alone never authenticates it: fresh verification must
    compare against the separately pinned reviewed capture.
    """
    from tools.trace_inspection_qd_kt_vba import _decode
    exported = _members(artifacts["source_zip"])
    package = _members(artifacts["addin"])
    if "xl/vbaProject.bin" not in package:
        raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_PROJECT_MISSING")
    modules, codepage = _extract_addin(artifacts["addin"])
    if codepage != 1252 or not set(PROCEDURES).issubset(modules):
        raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_PROJECT_UNEXPECTED")
    procedure_rows = []
    for module, names in PROCEDURES.items():
        for name in names:
            runtime = _procedure(modules[module], name)
            row = {"module": module, "procedure": name, "addin_lines": [runtime["start_line"], runtime["end_line"]],
                   "addin_procedure_utf8_lf_sha256": sha256(runtime["text"].encode()).hexdigest()}
            if module in exported:
                reviewed = _procedure(_decode(exported[module]), name)
                candidate = _procedure(exported[module].decode("cp1252"), name)
                row.update({"zip_lines": [reviewed["start_line"], reviewed["end_line"]],
                    "reviewed_decoder_comparison": compare_source_text(reviewed["text"], runtime["text"]),
                    "unattested_zip_cp1252_comparison": compare_source_text(candidate["text"], runtime["text"])})
            else:
                row["zip_evidence"] = "ARTIFACT_UNAVAILABLE_OR_EVIDENCE_INSUFFICIENT"
            procedure_rows.append(row)
    helper_rows = []
    for name in HELPERS:
        matches = [module for module, text in modules.items() if re.search(r"(?mi)^\s*(?:(?:Public|Private|Friend)\s+)?Function\s+" + name + r"\b", text)]
        if matches != ["WinAPI.bas"]:
            raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_HELPER_AMBIGUOUS")
        helper_rows.append({"name": name, "module": "WinAPI.bas", "declaration_matches": 1,
            "static_reference": "Module1.TaoQDKT_KHKT:607" if name == "DelLastIf_Ins" else "RecordForm.Tao_QDKT_KHKT_BBKT:" + ("746" if name == "LCase_FirstChar" else "747"),
            "scope": "STATIC_REFERENCE_IN_SAME_CAPTURED_PROJECT_NOT_EXECUTION_PROOF"})
    inventory = load_qdkt_source_provenance()
    zip_writer = _procedure(_decode(exported["RecordForm.frm"]), "Tao_QDKT_KHKT_BBKT")
    addin_writer = _procedure(modules["RecordForm.frm"], "Tao_QDKT_KHKT_BBKT")
    operation_rows = {}
    for name, row in sorted(inventory["fields"].items()):
        op = next(op for op in row["vba_rendered_operations"] if op["reachability_i2"] != "UNREACHABLE_I2")
        relative = op["line"] - zip_writer["start_line"]
        left, right = zip_writer["text"].split("\n")[relative], addin_writer["text"].split("\n")[relative]
        operation_rows[name] = {"zip_line": op["line"], "addin_line": addin_writer["start_line"] + relative,
            "source_line_comparison": compare_source_text(left, right), "runtime_execution_verified": False}
    templates = []
    for asset in load_inspection_qd_kt_template_assets():
        data = artifacts["template_" + asset.gxp_type]
        audit = inspect_qdkt_dotx_bytes(data, asset=asset)
        parts, all_names = [], []
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        for part, content in sorted(_members(data).items()):
            if part.startswith("word/") and part.endswith(".xml"):
                names = [node.get(ns + "name") for node in ElementTree.fromstring(content).iter(ns + "bookmarkStart")]
                parts.append({"part": part, "bookmark_count": len(names)})
                all_names.extend(names)
        if len(set(all_names)) != len(all_names) or set(all_names) != set(audit.bookmark_names):
            raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_TEMPLATE_TARGET_AMBIGUOUS")
        templates.append({"gxp_type": asset.gxp_type, "sha256": audit.actual_sha256,
            "bookmark_names": sorted(all_names), "bookmark_count": len(all_names), "all_word_xml_parts": parts,
            "runtime_template_path_binding": "UNVERIFIED_VERSION_BINDING"})
    locations = {"source_zip": "legacy/GXP-VBA code.zip", "addin": "legacy/GPs.xlam"}
    locations.update({"template_" + a.gxp_type: "legacy/Templates/" + a.filename for a in load_inspection_qd_kt_template_assets()})
    return {
        "schema_version": "qdkt-runtime-source-capture/v1",
        "artifact_inputs": {key: {"location": locations[key], "sha256": sha256(value).hexdigest()} for key, value in sorted(artifacts.items())},
        "acquisition": "USER_SUPPLIED_LOCAL_ARTIFACTS_ORIGINAL_BUILD_DISTRIBUTION_CHAIN_UNATTESTED",
        "extraction": "oletools==0.60.2 VBA_Parser + VBA_Project PROJECTCODEPAGE; static only; in-memory immutable bytes",
        "project_codepage": codepage,
        "addin_project_embedding": {"member": "xl/vbaProject.bin", "sha256": sha256(package["xl/vbaProject.bin"]).hexdigest(),
            "comparison": "BYTE_IDENTICAL_BINDING_PROVEN", "scope": "EXACT_EMBEDDED_MEMBER_OF_PINNED_ADDIN_NOT_ZIP_SOURCE_VERSION_OR_EXECUTION"},
        "zip_member_count": len(exported), "zip_contains_winapi": "WinAPI.bas" in exported,
        "zip_source_members": {name: {"raw_sha256": sha256(exported[name]).hexdigest(), "reviewed_decoder": "trace_inspection_qd_kt_vba._decode (cp1258 fallback)",
            "zip_codepage_attested": False} for name in PROCEDURES if name in exported},
        "addin_modules_utf8_lf_sha256": {name: sha256(modules[name].encode()).hexdigest() for name in PROCEDURES},
        "procedures": procedure_rows, "helpers": helper_rows, "operation_source_lines": operation_rows, "templates": templates,
        "source_to_runtime_version_binding": "UNVERIFIED_VERSION_BINDING",
        "loaded_excel_runtime_verified": False, "compiled_pcode_source_equivalence_verified": False,
        "ready_to_render": False, "word_uat": "NOT_EXECUTED",
        "limitations": ["ZIP contains exports/FRX, no WinAPI or runtime add-in: no reproducible build/distribution binding",
            "PROJECTCODEPAGE attests add-in encoding only; cp1252 interpretation of ZIP is a comparison, not an approved correction of reviewed cp1258 source",
            "Full Get_Tpl and Get_TTV2 reviewed-decoder text differs in non-i2/error-message literals; alternative cp1252 texts match, so actual semantic change is unproven",
            "LF-only source equality preserves Unicode, casing, punctuation and whitespace; it is not binary identity",
            "No evidence of the add-in actually loaded by Excel, p-code/source equivalence, live variable values, resolved Template_Path, business approval or Word output"],
    }


def verify_runtime_sources(artifacts: dict[str, bytes]) -> dict:
    snapshots = validate_runtime_artifact_bytes(artifacts)
    capture = capture_runtime_sources(snapshots)
    validate_runtime_capture(capture)
    return {"primary_bytes_verified": True, "reviewed_capture_reproduced": True,
        "source_to_runtime_version_binding": "UNVERIFIED_VERSION_BINDING", "ready_to_render": False,
        "template_bookmark_counts": {r["gxp_type"]: r["bookmark_count"] for r in capture["templates"]}}


def verify_local_runtime_sources(root) -> dict:
    from tools._qdkt_evidence_io import read_evidence, EvidenceBlocked, FILE_LIMIT
    expected = load_runtime_source_evidence()["artifact_inputs"]
    try:
        snapshots = {key: read_evidence(root, row["location"], FILE_LIMIT) for key, row in expected.items()}
    except EvidenceBlocked as exc:
        raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_ARTIFACT_UNAVAILABLE") from exc
    return verify_runtime_sources(snapshots)
