from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.phase7_execution_evidence import (
    Phase7ExecutionEvidenceError,
    require_execution_evidence,
)
from tools.validate_phase7_cutover_checklist import (
    ALLOWED_STATUSES,
    AUTHORITATIVE_ITEM_IDS,
    OPERATIONAL_EVIDENCE_FIELDS,
    validate_rows,
)


class Phase7ExecutionItemUpdateError(RuntimeError):
    """Raised when a requested checklist update is unsafe or invalid."""


COMMON_MUTABLE_FIELDS = frozenset({"notes"})
LIST_FIELDS = frozenset({"evidence_refs", "command_refs"})


def _allowed_scalar_fields(item_id: str) -> frozenset[str]:
    fields = set(COMMON_MUTABLE_FIELDS)
    fields.update(OPERATIONAL_EVIDENCE_FIELDS.get(item_id, ()))
    return frozenset(fields)


def _parse_set(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise Phase7ExecutionItemUpdateError("--set must use FIELD=VALUE.")
        field, field_value = value.split("=", 1)
        if not field or not field_value.strip():
            raise Phase7ExecutionItemUpdateError("--set FIELD and VALUE must both be nonblank.")
        if field in parsed:
            raise Phase7ExecutionItemUpdateError(f"Duplicate --set field: {field}")
        parsed[field] = field_value
    return parsed


def _validate_requested_fields(
    *,
    item_id: str,
    scalar_updates: dict[str, str],
    evidence_refs: list[str] | None,
    command_refs: list[str] | None,
) -> None:
    allowed_scalars = _allowed_scalar_fields(item_id)
    for field in scalar_updates:
        if field in {"item_id", "status", "required_for_cutover", *LIST_FIELDS}:
            raise Phase7ExecutionItemUpdateError(f"Field is not mutable through --set: {field}")
        if field not in allowed_scalars:
            raise Phase7ExecutionItemUpdateError(f"Field is not allowed for {item_id}: {field}")
    if evidence_refs is not None and item_id not in OPERATIONAL_EVIDENCE_FIELDS:
        raise Phase7ExecutionItemUpdateError(f"evidence_refs is not allowed for {item_id}")
    if command_refs is not None and item_id != "final_phase2_import_rerun":
        raise Phase7ExecutionItemUpdateError(f"command_refs is not allowed for {item_id}")


def _validate_refs(field: str, values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    if not values or any(not value.strip() for value in values):
        raise Phase7ExecutionItemUpdateError(f"{field} values must be nonblank.")
    if len(set(values)) != len(values):
        raise Phase7ExecutionItemUpdateError(f"Duplicate {field} values are not allowed.")
    return values


def _load_checklist(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        original = path.read_bytes()
        payload = json.loads(original.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Phase7ExecutionItemUpdateError(f"Phase 7 execution checklist is invalid: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise Phase7ExecutionItemUpdateError("Phase 7 execution checklist must contain an items list.")
    return original, payload


def _find_exact_row(rows: list[Any], item_id: str) -> dict[str, Any]:
    matches = [row for row in rows if isinstance(row, dict) and row.get("item_id") == item_id]
    if len(matches) != 1:
        raise Phase7ExecutionItemUpdateError(
            f"Expected exactly one checklist row for {item_id}; found {len(matches)}."
        )
    return matches[0]


def build_updated_checklist(
    payload: dict[str, Any],
    *,
    item_id: str,
    status: str,
    scalar_updates: dict[str, str],
    evidence_refs: list[str] | None = None,
    command_refs: list[str] | None = None,
) -> dict[str, Any]:
    if item_id not in AUTHORITATIVE_ITEM_IDS:
        raise Phase7ExecutionItemUpdateError(f"Unknown authoritative item_id: {item_id}")
    if status not in ALLOWED_STATUSES:
        raise Phase7ExecutionItemUpdateError(f"Invalid status: {status}")
    evidence_refs = _validate_refs("evidence_refs", evidence_refs)
    command_refs = _validate_refs("command_refs", command_refs)
    _validate_requested_fields(
        item_id=item_id,
        scalar_updates=scalar_updates,
        evidence_refs=evidence_refs,
        command_refs=command_refs,
    )
    candidate = copy.deepcopy(payload)
    row = _find_exact_row(candidate["items"], item_id)
    row["status"] = status
    row.update(scalar_updates)
    if evidence_refs is not None:
        row["evidence_refs"] = evidence_refs
    if command_refs is not None:
        row["command_refs"] = command_refs
    errors = validate_rows(candidate["items"])
    if errors:
        raise Phase7ExecutionItemUpdateError("Checklist validation failed: " + "; ".join(errors))
    return candidate


def _backup_path(checklist_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = checklist_path.with_name(f"{checklist_path.stem}.before-{stamp}{checklist_path.suffix}")
    suffix = 1
    while candidate.exists():
        candidate = checklist_path.with_name(
            f"{checklist_path.stem}.before-{stamp}-{suffix}{checklist_path.suffix}"
        )
        suffix += 1
    return candidate


def _write_bytes_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_write(path: Path, content: bytes) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def update_execution_item(
    *,
    evidence_dir: Path,
    item_id: str,
    status: str,
    scalar_updates: dict[str, str],
    evidence_refs: list[str] | None = None,
    command_refs: list[str] | None = None,
    dry_run: bool = False,
) -> Path | None:
    paths = require_execution_evidence(evidence_dir)
    original, payload = _load_checklist(paths.checklist_path)
    candidate = build_updated_checklist(
        payload,
        item_id=item_id,
        status=status,
        scalar_updates=scalar_updates,
        evidence_refs=evidence_refs,
        command_refs=command_refs,
    )
    if dry_run:
        return None
    rendered = json.dumps(candidate, ensure_ascii=False, indent=2) + "\n"
    backup_path = _backup_path(paths.checklist_path)
    _write_bytes_exclusive(backup_path, original)
    _atomic_write(paths.checklist_path, rendered.encode("utf-8"))
    return backup_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely update one external Phase 7 execution checklist item.")
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--status", required=True, choices=sorted(ALLOWED_STATUSES))
    parser.add_argument("--set", dest="sets", action="append", default=[], metavar="FIELD=VALUE")
    parser.add_argument("--evidence-ref", action="append", default=None)
    parser.add_argument("--command-ref", action="append", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        scalar_updates = _parse_set(args.sets)
        backup_path = update_execution_item(
            evidence_dir=args.evidence_dir,
            item_id=args.item_id,
            status=args.status,
            scalar_updates=scalar_updates,
            evidence_refs=args.evidence_ref,
            command_refs=args.command_ref,
            dry_run=args.dry_run,
        )
    except (Phase7ExecutionEvidenceError, Phase7ExecutionItemUpdateError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"DRY RUN: checklist item {args.item_id} would be updated; no files were changed.")
    else:
        print(f"Checklist item {args.item_id} updated. Backup: {backup_path}")
        print("Rerun build_phase7_cutover_readiness, then validate_phase7_cutover_checklist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
