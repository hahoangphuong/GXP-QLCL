import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import win32com.client
from oletools.olevba import VBA_Parser

if __package__:
    from .legacy_audit_helpers import (
        detect_file_ops,
        detect_header_row,
        detect_word_ops,
        extract_procedure_defs,
        find_application_run_targets,
        find_direct_calls,
        split_procedure_blocks,
    )
else:
    sys.path.append(str(Path(__file__).resolve().parent))
    from legacy_audit_helpers import (
        detect_file_ops,
        detect_header_row,
        detect_word_ops,
        extract_procedure_defs,
        find_application_run_targets,
        find_direct_calls,
        split_procedure_blocks,
    )


ROOT = Path(__file__).resolve().parents[1]
LEGACY_DIR = ROOT / "legacy"
OUTPUT_DIR = ROOT / "artifacts" / "legacy_audit"
CORE_SHEETS = ["db.cty", "db.cso", "db.ktra", "db.cc", "db.dkkd", "db.Tdoi", "db.Tdoi2"]


def safe_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def excel_app():
    app = win32com.client.Dispatch("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    app.AutomationSecurity = 3
    return app


def sheet_visibility(code: int) -> str:
    return {0: "hidden", -1: "visible", 2: "very_hidden"}.get(code, f"unknown:{code}")


def inspect_workbook(path: Path) -> dict:
    app = excel_app()
    wb = app.Workbooks.Open(str(path.resolve()))
    try:
        workbook = {
            "name": wb.Name,
            "path": str(path),
            "worksheets": [],
            "names": [],
        }
        for idx in range(1, wb.Worksheets.Count + 1):
            ws = wb.Worksheets(idx)
            workbook["worksheets"].append(
                {
                    "index": idx,
                    "name": ws.Name,
                    "visible": sheet_visibility(ws.Visible),
                    "used_rows": ws.UsedRange.Rows.Count,
                    "used_cols": ws.UsedRange.Columns.Count,
                }
            )
        for idx in range(1, wb.Names.Count + 1):
            name = wb.Names(idx)
            workbook["names"].append({"name": name.Name, "refers_to": name.RefersTo})

        if path.suffix.lower() == ".xlsb":
            workbook["core_sheets"] = inspect_core_sheets(wb)
        return workbook
    finally:
        wb.Close(False)
        app.Quit()


def inspect_core_sheets(wb) -> dict:
    result = {}
    for sheet_name in CORE_SHEETS:
        ws = wb.Worksheets(sheet_name)
        preview_rows = min(10, ws.UsedRange.Rows.Count)
        preview_cols = min(25, ws.UsedRange.Columns.Count)
        grid = ws.Range(ws.Cells(1, 1), ws.Cells(preview_rows, preview_cols)).Value
        rows = [[cell for cell in row] for row in grid]
        header_idx = detect_header_row(rows)
        header = [safe_text(cell) for cell in rows[header_idx]]
        data_row = rows[header_idx + 1] if header_idx + 1 < len(rows) else []
        result[sheet_name] = {
            "header_row_1_based": header_idx + 1,
            "headers": header,
            "sample_row": [safe_text(cell) for cell in data_row],
        }
    return result


def extract_vba(path: Path) -> dict:
    parser = VBA_Parser(str(path))
    modules = []
    all_proc_names = []
    source_dir = OUTPUT_DIR / "vba_sources" / path.stem
    source_dir.mkdir(parents=True, exist_ok=True)
    try:
        for _, stream_path, filename, source in parser.extract_macros():
            procedures = extract_procedure_defs(source)
            blocks = split_procedure_blocks(source)
            (source_dir / filename).write_text(source, encoding="utf-8")
            modules.append(
                {
                    "stream_path": stream_path,
                    "filename": filename,
                    "procedures": [{"name": proc.name, "kind": proc.kind} for proc in procedures],
                    "application_run_targets": find_application_run_targets(source),
                    "word_ops": detect_word_ops(source),
                    "file_ops": detect_file_ops(source),
                    "procedure_blocks": blocks,
                }
            )
            all_proc_names.extend(proc.name for proc in procedures)
        proc_names = sorted(set(all_proc_names), key=str.lower)
        for module in modules:
            blocks = module.pop("procedure_blocks")
            for proc in module["procedures"]:
                proc["direct_calls"] = find_direct_calls(blocks.get(proc["name"], ""), proc_names, proc["name"])
        return {"modules": modules}
    finally:
        parser.close()


def build_dependency_graph(vba_inventory: dict) -> list[dict]:
    edges = []
    for module in vba_inventory["modules"]:
        component = module["filename"]
        for proc in module["procedures"]:
            for target in proc["direct_calls"]:
                edges.append({"from": proc["name"], "to": target, "type": "direct_call", "component": component})
        for target in module["application_run_targets"]:
            edges.append(
                {
                    "from": component,
                    "to": target["procedure"],
                    "type": "application_run",
                    "workbook": target["workbook"] or None,
                }
            )
    return edges


def load_sheet_rows(sheet_meta: dict, workbook_path: Path) -> list[dict]:
    app = excel_app()
    wb = app.Workbooks.Open(str(workbook_path.resolve()))
    try:
        rows = []
        for sheet_name, meta in sheet_meta.items():
            ws = wb.Worksheets(sheet_name)
            header_row = meta["header_row_1_based"]
            last_row = ws.UsedRange.Rows.Count
            last_col = ws.UsedRange.Columns.Count
            values = ws.Range(ws.Cells(header_row, 1), ws.Cells(last_row, last_col)).Value
            headers = [safe_text(cell) for cell in values[0]]
            for row in values[1:]:
                rows.append(
                    {
                        "sheet": sheet_name,
                        "data": {headers[idx]: safe_text(cell) for idx, cell in enumerate(row) if safe_text(headers[idx])},
                    }
                )
        return rows
    finally:
        wb.Close(False)
        app.Quit()


def anomaly_report(workbook_meta: dict, workbook_path: Path) -> dict:
    core = workbook_meta["core_sheets"]
    rows = load_sheet_rows(core, workbook_path)
    by_sheet = defaultdict(list)
    for row in rows:
        by_sheet[row["sheet"]].append(row["data"])

    report = {"duplicate_ids": {}, "orphans": {}, "known_cleanup": {}, "counts": {}}
    for sheet, data_rows in by_sheet.items():
        ids = [row.get("ID") for row in data_rows if row.get("ID")]
        dup_ids = [item for item, count in Counter(ids).items() if count > 1]
        report["duplicate_ids"][sheet] = dup_ids
        report["counts"][sheet] = len(data_rows)

    cty_ids = {row.get("ID") for row in by_sheet["db.cty"]}
    cso_ids = {row.get("ID") for row in by_sheet["db.cso"]}
    ktra_ids = {row.get("ID") for row in by_sheet["db.ktra"]}
    cc_ids = {row.get("ID") for row in by_sheet["db.cc"]}

    report["orphans"]["db.cso.ID Cty"] = sorted(
        row.get("ID") for row in by_sheet["db.cso"] if row.get("ID Cty") and row.get("ID Cty") not in cty_ids
    )
    report["orphans"]["db.ktra.ID CƠ SỞ"] = sorted(
        row.get("ID") for row in by_sheet["db.ktra"] if row.get("ID CƠ SỞ") and row.get("ID CƠ SỞ") not in cso_ids
    )
    report["orphans"]["db.cc.ID ĐỢT KTRA"] = sorted(
        row.get("ID") for row in by_sheet["db.cc"] if row.get("ID ĐỢT KTRA") and row.get("ID ĐỢT KTRA") not in ktra_ids
    )
    report["orphans"]["db.cc.ID CƠ SỞ"] = sorted(
        row.get("ID") for row in by_sheet["db.cc"] if row.get("ID CƠ SỞ") and row.get("ID CƠ SỞ") not in cso_ids
    )
    report["orphans"]["db.dkkd.ID CC"] = sorted(
        row.get("ID") for row in by_sheet["db.dkkd"] if row.get("ID CC") and all(part.strip() not in cc_ids for part in row.get("ID CC", "").split(";"))
    )

    dkkd_385 = [row for row in by_sheet["db.dkkd"] if row.get("ID") == "385"]
    payloads = [{k: v for k, v in row.items() if k != "ID"} for row in dkkd_385]
    report["known_cleanup"]["db.dkkd.ID_385_rows"] = len(dkkd_385)
    report["known_cleanup"]["db.dkkd.ID_385_exact_duplicate"] = len({json.dumps(p, sort_keys=True, ensure_ascii=False) for p in payloads}) <= 1
    return report


def render_markdown(workbook_meta: dict, xlam_meta: dict, anomalies: dict) -> str:
    xlsb_modules = workbook_meta["vba"]["modules"]
    xlam_modules = xlam_meta["vba"]["modules"]
    lines = [
        "# Legacy Audit Report",
        "",
        "Generated by `tools/legacy_audit.py`.",
        "",
        "## Workbook inventory",
        "",
    ]
    for ws in workbook_meta["workbook"]["worksheets"]:
        lines.append(
            f"- `{ws['name']}`: `{ws['visible']}`, used range `{ws['used_rows']}x{ws['used_cols']}`"
        )
    lines.extend(
        [
            "",
            "## VBA inventory",
            "",
            f"- Workbook VBA components: `{len(xlsb_modules)}`",
            f"- Add-in VBA components: `{len(xlam_modules)}`",
            "",
            "## Core data counts",
            "",
        ]
    )
    for sheet, count in anomalies["counts"].items():
        lines.append(f"- `{sheet}`: `{count}` rows")
    lines.extend(
        [
            "",
            "## Duplicate IDs",
            "",
        ]
    )
    for sheet, dup_ids in anomalies["duplicate_ids"].items():
        lines.append(f"- `{sheet}`: {', '.join(dup_ids) if dup_ids else 'none'}")
    lines.extend(
        [
            "",
            "## Orphan checks",
            "",
        ]
    )
    for label, orphans in anomalies["orphans"].items():
        lines.append(f"- `{label}`: {', '.join(orphans[:10]) if orphans else 'none'}")
    lines.extend(
        [
            "",
            "## Known cleanup baseline",
            "",
            f"- `db.dkkd ID=385` rows: `{anomalies['known_cleanup']['db.dkkd.ID_385_rows']}`",
            f"- `db.dkkd ID=385` exact duplicate: `{anomalies['known_cleanup']['db.dkkd.ID_385_exact_duplicate']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    xlsb_path = next(LEGACY_DIR.glob("*.xlsb"))
    xlam_path = next(LEGACY_DIR.glob("*.xlam"))

    xlsb_workbook = inspect_workbook(xlsb_path)
    xlam_workbook = inspect_workbook(xlam_path)
    xlsb_vba = extract_vba(xlsb_path)
    xlam_vba = extract_vba(xlam_path)

    workbook_meta = {"workbook": xlsb_workbook, "vba": xlsb_vba, "dependency_graph": build_dependency_graph(xlsb_vba)}
    xlam_meta = {"workbook": xlam_workbook, "vba": xlam_vba, "dependency_graph": build_dependency_graph(xlam_vba)}
    anomalies = anomaly_report(xlsb_workbook, xlsb_path)

    (OUTPUT_DIR / "workbook_inventory.json").write_text(json.dumps(workbook_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "addin_inventory.json").write_text(json.dumps(xlam_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "anomalies.json").write_text(json.dumps(anomalies, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "report.md").write_text(render_markdown(workbook_meta, xlam_meta, anomalies), encoding="utf-8")
    print(f"Wrote audit artifacts to {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
