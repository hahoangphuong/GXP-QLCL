"""Public raw-coordinate primitives for authoritative Snapshot V2 db.ktra readers."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Mapping


def excel_serial_date(value: Any) -> date | None:
    """Convert an Excel serial only when the storage representation is numeric."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
    except (OverflowError, ValueError):
        return None


def snapshot_columns(
    snapshot: Mapping[str, Any],
    sheet_name: str,
    *,
    required_headers: tuple[str, ...] = (),
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return validated V2 raw coordinates without silently collapsing headers."""
    sheet = next((item for item in snapshot.get("sheets", []) if item.get("sheet_name") == sheet_name), None)
    if not isinstance(sheet, Mapping):
        raise ValueError(f"Snapshot V2 is missing {sheet_name}")
    rows = list(sheet.get("raw_rows", []))
    header = next((row for row in rows if row.get("source_row_number") == 4), None)
    if not isinstance(header, Mapping):
        raise ValueError(f"{sheet_name} header row is missing")
    cells = header.get("cells")
    if not isinstance(cells, list):
        raise ValueError(f"{sheet_name} header cells are invalid")
    coordinates: dict[str, list[int]] = {}
    for cell in cells:
        if not isinstance(cell, Mapping):
            raise ValueError(f"{sheet_name} header cell is invalid")
        value = cell.get("raw_value")
        ordinal = cell.get("column_ordinal")
        if value in (None, ""):
            continue
        if not isinstance(ordinal, int) or ordinal < 1:
            raise ValueError(f"{sheet_name} header column ordinal is invalid")
        coordinates.setdefault(str(value), []).append(ordinal)
    duplicates = sorted(name for name in required_headers if len(coordinates.get(name, [])) > 1)
    if duplicates:
        raise ValueError(f"{sheet_name} has duplicate required source headers: {', '.join(duplicates)}")
    return rows, {name: ordinals[0] for name, ordinals in coordinates.items() if len(ordinals) == 1}


def snapshot_cell_value(row: Mapping[str, Any], column: int) -> Any:
    if not isinstance(column, int) or column < 1:
        raise ValueError("Snapshot V2 source column ordinal is invalid")
    cells = row.get("cells")
    if not isinstance(cells, list):
        raise ValueError("Snapshot V2 source row cells are invalid")
    matches = [cell for cell in cells if isinstance(cell, Mapping) and cell.get("column_ordinal") == column]
    if len(matches) > 1:
        raise ValueError("Snapshot V2 source row has duplicate cell coordinates")
    return None if not matches else matches[0].get("raw_value")


def substantive_source_value(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or value.strip() not in {"", "-", "???"})


def snapshot_header_map(snapshot: Mapping[str, Any], sheet_name: str, *, required_headers: tuple[str, ...] = ()) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Resolve exact legacy headers without collapsing duplicate coordinates."""
    sheet = snapshot_sheet(snapshot, sheet_name)
    rows = list(sheet.get("raw_rows", []))
    header = next((row for row in rows if isinstance(row, Mapping) and row.get("source_row_number") == 4), None)
    if not isinstance(header, Mapping):
        raise ValueError(f"{sheet_name} header row is missing")
    cells = header.get("cells")
    if not isinstance(cells, list):
        raise ValueError(f"{sheet_name} header cells are invalid")
    coordinates: dict[str, list[int]] = {}
    for cell in cells:
        if not isinstance(cell, Mapping):
            raise ValueError(f"{sheet_name} header cell is invalid")
        value, ordinal = cell.get("raw_value"), cell.get("column_ordinal")
        if value in (None, ""):
            continue
        if not isinstance(ordinal, int) or ordinal < 1:
            raise ValueError(f"{sheet_name} header column ordinal is invalid")
        coordinates.setdefault(str(value), []).append(ordinal)
    duplicates = sorted(name for name in required_headers if len(coordinates.get(name, [])) > 1)
    if duplicates:
        raise ValueError(f"{sheet_name} has duplicate required source headers: {', '.join(duplicates)}")
    missing = sorted(name for name in required_headers if name not in coordinates)
    if missing:
        raise ValueError(f"{sheet_name} is missing required source headers: {', '.join(missing)}")
    return rows, {name: values[0] for name, values in coordinates.items() if len(values) == 1}


def snapshot_cell(snapshot_row: Mapping[str, Any], *, sheet_name: str, header: str, column_ordinal: int) -> dict[str, Any]:
    """Return lossless source-cell provenance for one resolved legacy header."""
    cells = snapshot_row.get("cells")
    if not isinstance(cells, list):
        raise ValueError("Snapshot V2 source row cells are invalid")
    matches = [cell for cell in cells if isinstance(cell, Mapping) and cell.get("column_ordinal") == column_ordinal]
    if len(matches) > 1:
        raise ValueError("Snapshot V2 source row has duplicate cell coordinates")
    cell = {} if not matches else dict(matches[0])
    return {"sheet_name": sheet_name, "source_row_number": snapshot_row.get("source_row_number"), "column_ordinal": column_ordinal, "header": header, "raw_value": cell.get("raw_value"), "raw_state": cell.get("raw_state"), "observed_type": cell.get("observed_type")}
