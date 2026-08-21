from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.legacy_audit_helpers import split_procedure_blocks


VBA_ROOT = ROOT / "artifacts/legacy_audit/vba_sources"
LEGACY_ROOT = ROOT / "legacy"
OUTPUT_ROOT = ROOT / "artifacts/phase5"

DIRECT_BOOKMARK_RE = re.compile(r'\.Bookmarks\("([^"]+)"\)', re.IGNORECASE)
REPLACE_BOOKMARK_RE = re.compile(r'(?:Replace_Bookmark|UpdateBookmark)\s+\w+\s*,\s*"([^"]+)"', re.IGNORECASE)
DELETE_BOOKMARK_RE = re.compile(r'Delete_Bookmark\s+\w+\s*,\s*"([^"]+)"', re.IGNORECASE)
BOOKMARK_EXISTS_RE = re.compile(r'\.Bookmarks\.Exists\("([^"]+)"\)', re.IGNORECASE)
COPY_FROM_RE = re.compile(r'\b\w+\.Bookmarks\("([^"]+)"\)\.Range\.Copy\b', re.IGNORECASE)
PASTE_TO_RE = re.compile(r'\b\w+\.Bookmarks\("([^"]+)"\)\.Range\.Paste\b', re.IGNORECASE)
TEMPLATE_LITERAL_RE = re.compile(r'"([^"\r\n]+\.(?:dotx|docx|xltx))"', re.IGNORECASE)
SAVE_DOCX_RE = re.compile(r'SaveAs\s+Filename:=.+?\.docx"|FileFormat:=16', re.IGNORECASE)
SAVE_GENERIC_RE = re.compile(r'\.(SaveAs|ExportAsFixedFormat)\b', re.IGNORECASE)
DOC_OPEN_RE = re.compile(r'Documents\.(?:Open|Add)\b', re.IGNORECASE)
WORD_APP_RE = re.compile(r'(?:GetObject|CreateObject)\(.*?"Word\.Application"', re.IGNORECASE)
EXCEL_APP_RE = re.compile(r'(?:GetObject|CreateObject)\(.*?"Excel\.Application"', re.IGNORECASE)
HELPER_PROC_NAMES = {"Get_Bookmark", "Delete_Bookmark", "Replace_Bookmark", "UpdateBookmark"}


@dataclass(frozen=True)
class ProcedureContract:
    module: str
    procedure: str
    applications: list[str]
    templates: list[str]
    bookmark_writes: list[str]
    bookmark_deletes: list[str]
    bookmark_exists_checks: list[str]
    bookmark_copy_sources: list[str]
    bookmark_paste_targets: list[str]
    output_extensions: list[str]
    opens_existing_documents: bool
    reuses_existing_document_content: bool


def normalize_list(values: list[str]) -> list[str]:
    return sorted({value.strip() for value in values if value.strip()}, key=str.lower)


def detect_applications(block: str) -> list[str]:
    apps: list[str] = []
    if WORD_APP_RE.search(block):
        apps.append("Word")
    if EXCEL_APP_RE.search(block):
        apps.append("Excel")
    return apps


def detect_output_extensions(block: str, templates: list[str]) -> list[str]:
    extensions = {Path(template).suffix.lower() for template in templates}
    if SAVE_DOCX_RE.search(block):
        extensions.add(".docx")
    if SAVE_GENERIC_RE.search(block) and not extensions:
        extensions.add("dynamic")
    return sorted(extensions)


def extract_contracts(vba_root: Path) -> list[ProcedureContract]:
    contracts: list[ProcedureContract] = []
    for path in sorted(vba_root.rglob("*")):
        if path.suffix.lower() not in {".frm", ".bas", ".cls"}:
            continue
        module_name = path.stem
        blocks = split_procedure_blocks(path.read_text(encoding="utf-8", errors="ignore"))
        for procedure_name, block in blocks.items():
            applications = detect_applications(block)
            templates = normalize_list(TEMPLATE_LITERAL_RE.findall(block))
            bookmark_writes = normalize_list(REPLACE_BOOKMARK_RE.findall(block))
            bookmark_deletes = normalize_list(DELETE_BOOKMARK_RE.findall(block))
            bookmark_exists = normalize_list(BOOKMARK_EXISTS_RE.findall(block))
            bookmark_copy_sources = normalize_list(COPY_FROM_RE.findall(block))
            bookmark_paste_targets = normalize_list(PASTE_TO_RE.findall(block))
            direct_bookmarks = normalize_list(DIRECT_BOOKMARK_RE.findall(block))
            opens_existing_documents = bool(DOC_OPEN_RE.search(block))
            reuses_existing = bool(bookmark_copy_sources or bookmark_paste_targets)
            has_signal = any(
                [
                    applications,
                    templates,
                    bookmark_writes,
                    bookmark_deletes,
                    bookmark_exists,
                    bookmark_copy_sources,
                    bookmark_paste_targets,
                    opens_existing_documents,
                ]
            )
            if not has_signal or procedure_name in HELPER_PROC_NAMES:
                continue
            for bookmark in direct_bookmarks:
                if bookmark not in bookmark_writes and f'Bookmarks("{bookmark}").Range.Text' in block:
                    bookmark_writes.append(bookmark)
            contracts.append(
                ProcedureContract(
                    module=module_name,
                    procedure=procedure_name,
                    applications=applications,
                    templates=normalize_list(templates),
                    bookmark_writes=normalize_list(bookmark_writes),
                    bookmark_deletes=bookmark_deletes,
                    bookmark_exists_checks=bookmark_exists,
                    bookmark_copy_sources=bookmark_copy_sources,
                    bookmark_paste_targets=bookmark_paste_targets,
                    output_extensions=detect_output_extensions(block, templates),
                    opens_existing_documents=opens_existing_documents,
                    reuses_existing_document_content=reuses_existing,
                )
            )
    return contracts


def build_summary(contracts: list[ProcedureContract]) -> dict[str, object]:
    template_to_procedures: dict[str, list[str]] = defaultdict(list)
    bookmark_to_procedures: dict[str, list[str]] = defaultdict(list)
    app_counts: Counter[str] = Counter()
    copy_procedures: list[str] = []
    procedures_with_templates: list[str] = []
    for contract in contracts:
        proc_id = f"{contract.module}.{contract.procedure}"
        if contract.templates:
            procedures_with_templates.append(proc_id)
        if contract.reuses_existing_document_content:
            copy_procedures.append(proc_id)
        for app in contract.applications:
            app_counts[app] += 1
        for template in contract.templates:
            template_to_procedures[template].append(proc_id)
        for bookmark in (
            contract.bookmark_writes
            + contract.bookmark_deletes
            + contract.bookmark_exists_checks
            + contract.bookmark_copy_sources
            + contract.bookmark_paste_targets
        ):
            bookmark_to_procedures[bookmark].append(proc_id)
    legacy_template_files = sorted(
        str(path.relative_to(LEGACY_ROOT))
        for path in LEGACY_ROOT.rglob("*")
        if path.suffix.lower() in {".docx", ".dotx", ".docm", ".dotm", ".xltx"}
    )
    return {
        "procedure_count": len(contracts),
        "application_counts": dict(sorted(app_counts.items())),
        "templates": [
            {"template": key, "procedures": sorted(set(value))}
            for key, value in sorted(template_to_procedures.items())
        ],
        "bookmark_registry": [
            {"bookmark": key, "procedures": sorted(set(value))}
            for key, value in sorted(bookmark_to_procedures.items())
        ],
        "copy_forward_procedures": sorted(set(copy_procedures)),
        "procedures_with_templates": sorted(set(procedures_with_templates)),
        "legacy_template_files_found": legacy_template_files,
        "excluded_legacy_branches": ["PowerPoint-backed certificate flow"],
    }


def render_markdown(summary: dict[str, object], contracts: list[ProcedureContract]) -> str:
    lines = [
        "# Phase 5 Document Contract Report",
        "",
        "## Evidence summary",
        f"- Procedures with document automation signals: {summary['procedure_count']}",
        f"- Applications observed: {json.dumps(summary['application_counts'], ensure_ascii=False)}",
        f"- Legacy template files found under `legacy/`: {len(summary['legacy_template_files_found'])}",
        "- Excluded by scope: PowerPoint-backed certificate branch",
        "",
        "## Template inventory inferred from VBA",
    ]
    templates: list[dict[str, object]] = summary["templates"]  # type: ignore[assignment]
    if templates:
        for item in templates:
            template = item["template"]
            procedures = item["procedures"]
            lines.append(f"- `{template}` <- {', '.join(procedures)}")
    else:
        lines.append("- None inferred")
    lines.extend(["", "## Copy-forward / reuse flows"])
    copy_flows: list[str] = summary["copy_forward_procedures"]  # type: ignore[assignment]
    if copy_flows:
        for proc_id in copy_flows:
            lines.append(f"- `{proc_id}`")
    else:
        lines.append("- None detected")
    lines.extend(["", "## High-signal procedures"])
    for contract in contracts:
        proc_id = f"{contract.module}.{contract.procedure}"
        if not (
            contract.templates
            or contract.bookmark_writes
            or contract.bookmark_copy_sources
            or contract.bookmark_paste_targets
        ):
            continue
        lines.append(
            f"- `{proc_id}` apps={','.join(contract.applications) or '-'} "
            f"templates={len(contract.templates)} writes={len(contract.bookmark_writes)} "
            f"copy={len(contract.bookmark_copy_sources)}/{len(contract.bookmark_paste_targets)} "
            f"outputs={','.join(contract.output_extensions) or '-'}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    contracts = extract_contracts(VBA_ROOT)
    summary = build_summary(contracts)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summary,
        "procedures": [asdict(contract) for contract in contracts],
    }
    (OUTPUT_ROOT / "document_contract.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_ROOT / "document_contract.md").write_text(
        render_markdown(summary, contracts),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
