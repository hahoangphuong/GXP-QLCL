from __future__ import annotations

from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.session import session_scope
from backend.app.domain.phase2_import import import_snapshot, import_workbook_to_database


SNAPSHOT_FALLBACK_PATH = ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json"


def write_reconciliation_markdown(report_path: Path, reconciliation: dict[str, object]) -> None:
    lines = ["# Phase 2 Reconciliation Report", "", "## Source vs target counts", ""]
    for source_name in ["db.cty", "db.cso", "db.ktra", "db.cc", "db.dkkd", "db.Tdoi", "db.Tdoi2"]:
        lines.append(
            f"- `{source_name}`: source `{reconciliation['source_counts'][source_name]}`, "
            f"target `{reconciliation['target_counts'][source_name]}`"
        )
    lines.extend(["", "## Effective source vs target counts", ""])
    for source_name in ["db.cty", "db.cso", "db.ktra", "db.cc", "db.dkkd", "db.Tdoi", "db.Tdoi2"]:
        lines.append(
            f"- `{source_name}`: effective source `{reconciliation['effective_source_counts'][source_name]}`, "
            f"target `{reconciliation['target_counts'][source_name]}`, "
            f"excluded `{reconciliation['excluded_rows'].get(source_name, 0)}`"
        )
    lines.extend(["", "## Effective mismatches after confirmed exclusions", ""])
    if reconciliation["effective_mismatches"]:
        for key, value in reconciliation["effective_mismatches"].items():
            lines.append(
                f"- `{key}`: effective source `{value['effective_source_count']}`, "
                f"target `{value['target_count']}`, excluded `{value['excluded_count']}`"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Confirmed excluded blanked rows", ""])
    if reconciliation["excluded_rows"]:
        for key, value in reconciliation["excluded_rows"].items():
            lines.append(f"- `{key}`: excluded `{value}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Overrides", "", f"- applied overrides: `{reconciliation['applied_override_count']}`"])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    workbook_path = next((ROOT / "legacy").glob("*.xlsb"), None)
    database_path = ROOT / "artifacts" / "phase2" / "staging_readonly.db"
    report_path = ROOT / "artifacts" / "phase2" / "reconciliation.md"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        database_path.unlink()
    database_url = f"sqlite:///{database_path.as_posix()}"
    import_mode = "workbook"
    with session_scope(database_url) as session:
        try:
            if workbook_path is None:
                raise FileNotFoundError("No legacy workbook (*.xlsb) is present.")
            result = import_workbook_to_database(session, workbook_path, report_path, remediation_overrides=None)
            reconciliation = result.reconciliation
        except Exception as exc:
            if not SNAPSHOT_FALLBACK_PATH.exists():
                raise
            import_mode = f"snapshot_fallback:{type(exc).__name__}"
            snapshot = json.loads(SNAPSHOT_FALLBACK_PATH.read_text(encoding="utf-8"))
            reconciliation = import_snapshot(session, snapshot, remediation_overrides=None)
            write_reconciliation_markdown(report_path, reconciliation)
    json_path = report_path.with_suffix(".json")
    json_path.write_text(json.dumps(reconciliation, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Imported workbook snapshot into {database_url} using {import_mode}")
    print(f"Wrote reconciliation report to {report_path}")
    print(f"Wrote reconciliation json to {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
