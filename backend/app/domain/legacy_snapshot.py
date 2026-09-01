from __future__ import annotations

from pathlib import Path
from hashlib import sha256
import time
from typing import Any

from backend.app.domain.evaluation_scope import TAXONOMY_RANGE_DEFINITIONS, build_taxonomy_artifact

CORE_SHEETS = ["db.cty", "db.cso", "db.ktra", "db.cc", "db.dkkd", "db.Tdoi", "db.Tdoi2"]


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _excel_app():
    import win32com.client

    app = win32com.client.Dispatch("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    return app


def detect_header_row(rows: list[list[object]]) -> int:
    best_idx = 0
    best_score = -1
    for idx, row in enumerate(rows):
        score = sum(1 for cell in row if safe_text(cell))
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx


def read_core_sheet_rows(workbook_path: str | Path) -> dict[str, list[dict[str, str]]]:
    try:
        import pywintypes
    except ModuleNotFoundError as exc:
        raise RuntimeError("legacy_snapshot requires pywin32 on Windows-compatible tooling hosts.") from exc

    workbook_path = Path(workbook_path)
    app = _excel_app()
    wb = None
    last_error = None
    for _ in range(3):
        try:
            wb = app.Workbooks.Open(str(workbook_path.resolve()))
            break
        except pywintypes.com_error as exc:
            last_error = exc
            time.sleep(1)
    if wb is None:
        app.Quit()
        raise last_error

    try:
        snapshot: dict[str, list[dict[str, str]]] = {}
        for sheet_name in CORE_SHEETS:
            ws = wb.Worksheets(sheet_name)
            last_row = ws.UsedRange.Rows.Count
            last_col = ws.UsedRange.Columns.Count
            values = ws.Range(ws.Cells(1, 1), ws.Cells(last_row, last_col)).Value
            rows = [[cell for cell in row] for row in values]
            header_idx = detect_header_row(rows[:10])
            headers = [safe_text(cell) for cell in rows[header_idx]]
            data: list[dict[str, str]] = []
            for physical_idx, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
                if not any(safe_text(cell) for cell in row):
                    continue
                record = {
                    headers[idx]: safe_text(cell)
                    for idx, cell in enumerate(row)
                    if idx < len(headers) and safe_text(headers[idx])
                }
                record["__excel_row_number"] = str(physical_idx)
                data.append(record)
            snapshot[sheet_name] = data
        return snapshot
    finally:
        wb.Close(False)
        app.Quit()


def _range_rows(value: Any) -> list[list[object]]:
    if isinstance(value, tuple):
        if value and isinstance(value[0], tuple):
            return [list(row) for row in value]
        return [list(value)]
    return [[value]]


def read_evaluation_scope_taxonomy(workbook_path: str | Path) -> dict[str, Any]:
    """Read the authoritative DCForm named ranges from the Windows Excel owner."""
    try:
        import pywintypes
    except ModuleNotFoundError as exc:
        raise RuntimeError("legacy_snapshot requires pywin32 on Windows-compatible tooling hosts.") from exc

    workbook_path = Path(workbook_path)
    app = _excel_app()
    wb = None
    last_error = None
    for _ in range(3):
        try:
            wb = app.Workbooks.Open(str(workbook_path.resolve()))
            break
        except pywintypes.com_error as exc:
            last_error = exc
            time.sleep(1)
    if wb is None:
        app.Quit()
        raise last_error

    try:
        ranges: dict[str, dict[str, Any]] = {}
        for name, _, required in TAXONOMY_RANGE_DEFINITIONS:
            try:
                named_range = wb.Names(name).RefersToRange
            except pywintypes.com_error:
                if required:
                    raise RuntimeError(f"Required evaluation-scope named range is missing: {name}") from None
                continue
            ranges[name] = {
                "sheet_name": str(named_range.Worksheet.Name),
                "start_row": int(named_range.Row),
                "values": _range_rows(named_range.Value),
            }
        return build_taxonomy_artifact(
            workbook_name=workbook_path.name,
            workbook_sha256=sha256(workbook_path.read_bytes()).hexdigest(),
            ranges=ranges,
        )
    finally:
        wb.Close(False)
        app.Quit()
