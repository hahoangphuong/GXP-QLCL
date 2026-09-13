from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}

PROC_START_RE = re.compile(
    r"^\s*(?P<kind>Public\s+|Private\s+|Friend\s+)?(?P<ptype>Sub|Function)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b",
    re.IGNORECASE,
)
PROC_END_RE = re.compile(r"^\s*End\s+(Sub|Function)\s*$", re.IGNORECASE)
CALL_RE = re.compile(
    r"(?:\bCall\s+|\b)([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(|\s)",
    re.IGNORECASE,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "legacy_audit" / "c5e_certificate_detail_evidence_capture.json"
DEFAULT_FIXTURE_DIR = ROOT / "tests" / "fixtures" / "c5e_certificate_detail"


class EvidenceCaptureError(RuntimeError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def find_recordform_member(names: list[str]) -> str:
    candidates = [name for name in names if Path(name).name.lower() == "recordform.frm"]
    if len(candidates) != 1:
        raise EvidenceCaptureError(
            f"Expected exactly one RecordForm.frm in VBA ZIP; found {len(candidates)}: {candidates}"
        )
    return candidates[0]


def extract_vba_procedures(text: str) -> dict[str, dict[str, object]]:
    lines = normalize_newlines(text).splitlines()
    procedures: dict[str, dict[str, object]] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        # Commented legacy bodies must never be promoted into active evidence.
        stripped = line.lstrip()
        if stripped.startswith("'"):
            i += 1
            continue
        m = PROC_START_RE.match(line)
        if not m:
            i += 1
            continue
        name = m.group("name")
        start = i
        j = i + 1
        while j < len(lines) and not PROC_END_RE.match(lines[j]):
            j += 1
        if j >= len(lines):
            raise EvidenceCaptureError(f"Procedure {name!r} has no End Sub/Function.")
        body_lines = lines[start : j + 1]
        active_body = "\n".join(body_lines) + "\n"
        procedures[name.lower()] = {
            "name": name,
            "start_line": start + 1,
            "end_line": j + 1,
            "body": active_body,
            "sha256": sha256_bytes(active_body.encode("utf-8")),
        }
        i = j + 1
    return procedures


def discover_direct_helper_candidates(body: str, procedures: dict[str, dict[str, object]]) -> list[str]:
    known = {key: value["name"] for key, value in procedures.items()}
    candidates: set[str] = set()
    for match in CALL_RE.finditer(body):
        token = match.group(1)
        key = token.lower()
        if key in known and key != "input_dc_to_cc":
            candidates.add(str(known[key]))
    return sorted(candidates, key=str.lower)


def capture_vba(vba_zip: Path, fixture_dir: Path) -> dict[str, object]:
    if not vba_zip.is_file():
        raise EvidenceCaptureError(f"VBA ZIP not found: {vba_zip}")
    with zipfile.ZipFile(vba_zip, "r") as archive:
        member = find_recordform_member(archive.namelist())
        raw = archive.read(member)
    # VBA exports are commonly cp1252/ANSI; try UTF-8 first, then cp1252.
    try:
        text = raw.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
        encoding = "cp1252"

    procedures = extract_vba_procedures(text)
    target = procedures.get("input_dc_to_cc")
    if target is None:
        raise EvidenceCaptureError(
            "Active Input_DC_to_CC procedure not found in RecordForm.frm. "
            "Commented code is intentionally ignored."
        )

    helpers = discover_direct_helper_candidates(str(target["body"]), procedures)
    helper_records = []
    for helper in helpers:
        rec = procedures[helper.lower()]
        helper_records.append(
            {
                "name": rec["name"],
                "start_line": rec["start_line"],
                "end_line": rec["end_line"],
                "sha256": rec["sha256"],
            }
        )

    fixture_dir.mkdir(parents=True, exist_ok=True)
    target_fixture = fixture_dir / "Input_DC_to_CC.active.bas"
    target_fixture.write_text(str(target["body"]), encoding="utf-8", newline="\n")

    helper_dir = fixture_dir / "helpers"
    helper_dir.mkdir(parents=True, exist_ok=True)
    for helper in helpers:
        rec = procedures[helper.lower()]
        (helper_dir / f"{rec['name']}.bas").write_text(
            str(rec["body"]), encoding="utf-8", newline="\n"
        )

    return {
        "source_zip": str(vba_zip),
        "source_zip_sha256": sha256_bytes(vba_zip.read_bytes()),
        "recordform_member": member,
        "recordform_encoding": encoding,
        "recordform_sha256": sha256_bytes(raw),
        "active_procedure": {
            "name": target["name"],
            "start_line": target["start_line"],
            "end_line": target["end_line"],
            "sha256": target["sha256"],
            "fixture": target_fixture.relative_to(ROOT).as_posix()
            if ROOT in target_fixture.parents else str(target_fixture),
        },
        "direct_helper_candidates": helper_records,
        "commented_code_promoted": False,
    }


def w(tag: str) -> str:
    return f"{{{WORD_NS}}}{tag}"


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join((node.text or "") for node in paragraph.findall(".//w:t", NS)).strip()


def inspect_word_xml(xml_bytes: bytes, part_name: str) -> dict[str, object]:
    root = ET.fromstring(xml_bytes)
    bookmarks = []
    for bm in root.findall(".//w:bookmarkStart", NS):
        bookmarks.append(
            {
                "name": bm.attrib.get(w("name")),
                "id": bm.attrib.get(w("id")),
            }
        )

    tables = []
    for table_index, table in enumerate(root.findall(".//w:tbl", NS), start=1):
        rows = []
        for row_index, row in enumerate(table.findall("./w:tr", NS), start=1):
            row_bookmarks = [
                bm.attrib.get(w("name"))
                for bm in row.findall(".//w:bookmarkStart", NS)
                if bm.attrib.get(w("name"))
            ]
            cells = []
            for cell in row.findall("./w:tc", NS):
                texts = [paragraph_text(p) for p in cell.findall("./w:p", NS)]
                cells.append(" | ".join(t for t in texts if t))
            rows.append(
                {
                    "row_index": row_index,
                    "bookmarks": row_bookmarks,
                    # Truncate visible text: enough for structural review without copying full template prose.
                    "cell_text_preview": [text[:160] for text in cells],
                }
            )
        tables.append({"table_index": table_index, "rows": rows})

    return {
        "part": part_name,
        "bookmarks": bookmarks,
        "tables": tables,
    }


def capture_template(template: Path, fixture_dir: Path) -> dict[str, object]:
    if not template.is_file():
        raise EvidenceCaptureError(f"Template not found: {template}")
    suffix = template.suffix.lower()
    if suffix not in {".docx", ".dotx"}:
        raise EvidenceCaptureError("Template must be .docx or .dotx.")

    structures = []
    with zipfile.ZipFile(template, "r") as archive:
        part_names = [
            name
            for name in archive.namelist()
            if name == "word/document.xml"
            or (name.startswith("word/header") and name.endswith(".xml"))
            or (name.startswith("word/footer") and name.endswith(".xml"))
        ]
        if "word/document.xml" not in part_names:
            raise EvidenceCaptureError("Template does not contain word/document.xml.")
        for part in sorted(part_names):
            structures.append(inspect_word_xml(archive.read(part), part))

    fixture_dir.mkdir(parents=True, exist_ok=True)
    structural_fixture = fixture_dir / f"{template.stem}.structure.json"
    payload = {
        "template_filename": template.name,
        "template_sha256": sha256_bytes(template.read_bytes()),
        "parts": structures,
    }
    structural_fixture.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "template_path": str(template),
        "template_filename": template.name,
        "template_sha256": payload["template_sha256"],
        "structure_fixture": structural_fixture.relative_to(ROOT).as_posix()
        if ROOT in structural_fixture.parents else str(structural_fixture),
        "parts": structures,
    }


def discover_templates(template_root: Path) -> list[Path]:
    if not template_root.is_dir():
        raise EvidenceCaptureError(f"Template root not found: {template_root}")
    candidates = []
    for path in template_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".dotx", ".docx"}:
            continue
        name = path.name.lower()
        if "chung chi" in name and ("moi" in name or "mới" in name):
            candidates.append(path)
    return sorted(candidates)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture exact legacy evidence for C.5e Input_DC_to_CC without mutating sources."
    )
    parser.add_argument("--vba-zip", required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--template", type=Path)
    group.add_argument("--template-root", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURE_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        vba = capture_vba(args.vba_zip.resolve(), args.fixture_dir.resolve())

        if args.template is not None:
            templates = [args.template.resolve()]
        else:
            templates = discover_templates(args.template_root.resolve())
            if not templates:
                raise EvidenceCaptureError(
                    "No candidate certificate templates found under --template-root. "
                    "Use --template with the exact legacy .dotx/.docx file."
                )

        template_records = [
            capture_template(path, args.fixture_dir.resolve()) for path in templates
        ]

        report = {
            "schema_version": "c5e-certificate-detail-evidence-capture/v1",
            "status": "EVIDENCE_CAPTURED",
            "vba": vba,
            "templates": template_records,
            "invariants": {
                "source_files_modified": False,
                "commented_code_promoted": False,
                "compact_summary_used": False,
                "historical_prose_used": False,
                "unkeyed_entries_used": False,
            },
            "next_step": (
                "Review captured active VBA/helper bodies and template row/bookmark structures, "
                "then derive the Input_DC_to_CC row-level semantic contract and parity tests."
            ),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print("STATUS=EVIDENCE_CAPTURED")
        print(f"TEMPLATES={len(template_records)}")
        print(f"OUTPUT={args.output.resolve()}")
        print(f"FIXTURE_DIR={args.fixture_dir.resolve()}")
        return 0
    except (EvidenceCaptureError, zipfile.BadZipFile, ET.ParseError) as exc:
        print(f"STATUS=EVIDENCE_CAPTURE_FAILED")
        print(f"ERROR={exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
