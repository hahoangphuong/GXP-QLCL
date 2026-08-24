from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import PRODUCTION_ENV_NAMES, load_app_config, resolve_database_url
from backend.app.db.session import build_session_factory
from backend.app.domain.legacy_snapshot import CORE_SHEETS
from backend.app.domain.phase2_import import ImportExecutionOptions, ImportCollisionError, import_snapshot
from backend.app.project_paths import phase_artifact_path
from backend.app.runtime_schema import expected_alembic_head_revision
from tools.build_phase7_cutover_readiness import build_readiness
from tools.env_utils import parse_env_file


DEFAULT_RUNTIME_ENV_PATH = Path("/etc/gxp/runtime.env")
DEFAULT_SNAPSHOT_PATH = phase_artifact_path("phase3c", "legacy_snapshot.json")
DEFAULT_REPORT_ROOT = phase_artifact_path("legacy-production")


class ProductionImportError(RuntimeError):
    """Raised when production import orchestration must fail closed."""


@dataclass(frozen=True)
class RuntimeDatabaseContract:
    runtime_env_path: Path
    app_env: str
    db_mode: str
    db_name: str
    db_user: str
    database_url: str
    database_url_redacted: str


@dataclass(frozen=True)
class ImportReport:
    mode: str
    runtime_env_path: str
    snapshot_path: str
    snapshot_sha256: str
    report_dir: str
    started_at_utc: str
    completed_at_utc: str
    deployment_git_sha: str
    alembic_head_revision: str | None
    alembic_current_revision: str | None
    database_url_redacted: str
    validation_status: str
    cutover_ready: bool
    phase7_status: str
    current_projection_gate: dict[str, Any]
    backup_status: str
    reconciliation: dict[str, Any]


def _redact_database_url(url: str) -> str:
    if "://" not in url or "@" not in url:
        return url
    scheme, remainder = url.split("://", 1)
    credentials, suffix = remainder.split("@", 1)
    if ":" not in credentials:
        return f"{scheme}://***@{suffix}"
    user, _password = credentials.split(":", 1)
    return f"{scheme}://{user}:***@{suffix}"


def _load_runtime_database_contract(runtime_env_path: Path) -> tuple[RuntimeDatabaseContract, dict[str, str]]:
    if not runtime_env_path.exists():
        raise ProductionImportError(f"Runtime env file not found: {runtime_env_path}")
    env = parse_env_file(runtime_env_path)
    config = load_app_config(env)
    database_url = resolve_database_url(env).strip()
    if config.app_env.strip().lower() not in PRODUCTION_ENV_NAMES:
        raise ProductionImportError(f"APP_ENV must be production for legacy production import, got {config.app_env!r}.")
    if config.db_mode != "local_postgres":
        raise ProductionImportError(f"DB_MODE must be local_postgres, got {config.db_mode!r}.")
    db_name = env.get("DB_NAME", "").strip()
    db_user = env.get("DB_USER", "").strip()
    if db_name != "gxp_qlcl":
        raise ProductionImportError(f"DB_NAME must be canonical production database gxp_qlcl, got {db_name!r}.")
    if db_user != "gxp_app":
        raise ProductionImportError(f"DB_USER must be canonical production user gxp_app, got {db_user!r}.")
    if not database_url:
        raise ProductionImportError("Resolved DATABASE_URL is blank.")
    if database_url.startswith("sqlite:"):
        raise ProductionImportError("Resolved DATABASE_URL must not be sqlite for production import.")
    return (
        RuntimeDatabaseContract(
            runtime_env_path=runtime_env_path,
            app_env=config.app_env,
            db_mode=config.db_mode,
            db_name=db_name,
            db_user=db_user,
            database_url=database_url,
            database_url_redacted=_redact_database_url(database_url),
        ),
        env,
    )


def _load_snapshot(snapshot_path: Path) -> tuple[dict[str, list[dict[str, str]]], str]:
    if not snapshot_path.exists():
        raise ProductionImportError(f"Snapshot file not found: {snapshot_path}")
    payload = snapshot_path.read_bytes()
    snapshot_sha = sha256(payload).hexdigest()
    try:
        snapshot = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ProductionImportError(f"Snapshot JSON is invalid: {snapshot_path}: {exc}") from exc
    if not isinstance(snapshot, dict):
        raise ProductionImportError("Snapshot root must be a JSON object.")
    missing_sheets = [sheet for sheet in CORE_SHEETS if sheet not in snapshot]
    if missing_sheets:
        raise ProductionImportError(f"Snapshot is missing required sheets: {', '.join(missing_sheets)}.")
    for sheet in CORE_SHEETS:
        rows = snapshot[sheet]
        if not isinstance(rows, list):
            raise ProductionImportError(f"Snapshot sheet {sheet!r} must be a list of rows.")
    return snapshot, snapshot_sha


def _current_alembic_revision(session: Any) -> str | None:
    try:
        result = session.execute(text("SELECT version_num FROM alembic_version"))
    except Exception as exc:
        raise ProductionImportError(f"Failed to query alembic_version: {exc}") from exc
    rows = [str(row[0]).strip() for row in result if row and row[0]]
    if not rows:
        return None
    if len(rows) != 1:
        raise ProductionImportError(f"Expected exactly one alembic revision row, found {rows!r}.")
    return rows[0]


def _run_backup(runtime_env_path: Path) -> None:
    command = ["bash", str(ROOT / "infra" / "vm" / "backup_postgres.sh")]
    env = os.environ.copy()
    env["VM_RUNTIME_ENV_FILE"] = str(runtime_env_path)
    completed = subprocess.run(command, cwd=str(ROOT), env=env, capture_output=True, text=True)
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip() or "backup command failed"
        raise ProductionImportError(f"PostgreSQL backup gate failed: {stderr}")


def _load_phase7_gate() -> tuple[str, dict[str, Any], bool]:
    report = build_readiness()
    phase7_status = str(report.get("phase7_status", "blocked"))
    current_projection_gate = report.get("gates", {}).get(
        "current_projection_conflicts",
        {"status": "blocked", "reason": "Current projection gate is unavailable."},
    )
    cutover_ready = phase7_status == "ready"
    return phase7_status, current_projection_gate, cutover_ready


def _build_report_dir(root: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    report_dir = root / timestamp
    report_dir.mkdir(parents=True, exist_ok=False)
    return report_dir


def _render_report_markdown(report: ImportReport) -> str:
    reconciliation = report.reconciliation
    lines = [
        "# Legacy Production Import",
        "",
        f"- Mode: `{report.mode}`",
        f"- Snapshot: `{report.snapshot_path}`",
        f"- Snapshot SHA-256: `{report.snapshot_sha256}`",
        f"- Runtime env: `{report.runtime_env_path}`",
        f"- Database: `{report.database_url_redacted}`",
        f"- Alembic current/head: `{report.alembic_current_revision}` / `{report.alembic_head_revision}`",
        f"- Validation status: `{report.validation_status}`",
        f"- Phase 7 status: `{report.phase7_status}`",
        f"- Cutover ready: `{str(report.cutover_ready).lower()}`",
        f"- Backup status: `{report.backup_status}`",
        "",
        "## Source Balance",
        "",
        "| Sheet | Source | Imported | Skipped | Excluded | Unresolved | Balanced |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for sheet in CORE_SHEETS:
        row = reconciliation["source_balance"][sheet]
        lines.append(
            f"| `{sheet}` | {row['source_count']} | {row['imported_count']} | {row['skipped_count']} | "
            f"{row['intentionally_skipped_count']} | {row['unresolved_count']} | `{row['balanced']}` |"
        )
    lines.extend(
        [
            "",
            "## Counts",
            "",
            f"- Inserted counts: `{json.dumps(reconciliation.get('inserted_counts', {}), ensure_ascii=False)}`",
            f"- Existing counts: `{json.dumps(reconciliation.get('existing_counts', {}), ensure_ascii=False)}`",
            f"- Skipped rows: `{json.dumps(reconciliation.get('skipped_rows', {}), ensure_ascii=False)}`",
            f"- Excluded rows: `{json.dumps(reconciliation.get('excluded_rows', {}), ensure_ascii=False)}`",
            f"- Current projection gate: `{current_projection_status(report.current_projection_gate)}`",
        ]
    )
    return "\n".join(lines) + "\n"


def current_projection_status(payload: dict[str, Any]) -> str:
    return f"{payload.get('status', 'blocked')}: {payload.get('reason', '')}".strip()


def _write_report(report_dir: Path, report: ImportReport) -> None:
    (report_dir / "report.json").write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (report_dir / "report.md").write_text(_render_report_markdown(report), encoding="utf-8")


def _run_import(
    *,
    database_url: str,
    snapshot: dict[str, list[dict[str, str]]],
    dry_run: bool,
    require_head_revision: bool,
) -> tuple[dict[str, Any], str | None, str | None]:
    factory = build_session_factory(database_url)
    session = factory()
    try:
        current_revision = _current_alembic_revision(session)
        head_revision = expected_alembic_head_revision()
        if require_head_revision and current_revision != head_revision:
            raise ProductionImportError(
                f"Alembic revision mismatch: current={current_revision!r}, head={head_revision!r}."
            )
        reconciliation = import_snapshot(
            session,
            snapshot,
            remediation_overrides=None,
            options=ImportExecutionOptions(
                ensure_schema=False,
                reset_existing_data=False,
                allow_existing_records=True,
                persist_audit_event=True,
            ),
        )
        open_anomalies = [
            row for row in reconciliation.get("anomaly_rows", [])
            if row.get("status") not in {"excluded_confirmed_blanked", "overridden"}
        ]
        if open_anomalies:
            raise ProductionImportError(
                f"Import produced unresolved anomalies: {len(open_anomalies)} row(s)."
            )
        if dry_run:
            session.rollback()
        else:
            session.commit()
        return reconciliation, current_revision, head_revision
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def execute_import(
    *,
    snapshot_path: Path,
    runtime_env_path: Path,
    mode: str,
    report_root: Path = DEFAULT_REPORT_ROOT,
) -> ImportReport:
    contract, _env = _load_runtime_database_contract(runtime_env_path)
    snapshot, snapshot_sha = _load_snapshot(snapshot_path)
    phase7_status, current_projection_gate, cutover_ready = _load_phase7_gate()
    report_dir = _build_report_dir(report_root)
    started_at = datetime.now(timezone.utc).isoformat()

    backup_status = "not-run"
    if mode == "apply":
        _run_backup(runtime_env_path)
        backup_status = "ok"

    reconciliation, current_revision, head_revision = _run_import(
        database_url=contract.database_url,
        snapshot=snapshot,
        dry_run=mode == "dry-run",
        require_head_revision=True,
    )

    validation_status = "pass"
    report = ImportReport(
        mode=mode,
        runtime_env_path=str(runtime_env_path),
        snapshot_path=str(snapshot_path),
        snapshot_sha256=snapshot_sha,
        report_dir=str(report_dir),
        started_at_utc=started_at,
        completed_at_utc=datetime.now(timezone.utc).isoformat(),
        deployment_git_sha=_git_sha(),
        alembic_head_revision=head_revision,
        alembic_current_revision=current_revision,
        database_url_redacted=contract.database_url_redacted,
        validation_status=validation_status,
        cutover_ready=cutover_ready,
        phase7_status=phase7_status,
        current_projection_gate=current_projection_gate,
        backup_status=backup_status,
        reconciliation=reconciliation,
    )
    _write_report(report_dir, report)
    return report


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Production-safe legacy snapshot import CLI.")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT_PATH)
    parser.add_argument("--runtime-env", type=Path, default=DEFAULT_RUNTIME_ENV_PATH)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    mode = "apply" if args.apply else "dry-run"
    try:
        report = execute_import(
            snapshot_path=args.snapshot,
            runtime_env_path=args.runtime_env,
            mode=mode,
            report_root=args.report_root,
        )
    except (ProductionImportError, ImportCollisionError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Legacy import {report.mode} completed.")
    print(f"Report directory: {report.report_dir}")
    print(f"Snapshot SHA-256: {report.snapshot_sha256}")
    print(f"Database: {report.database_url_redacted}")
    print(f"Phase 7 status: {report.phase7_status}")
    if not report.cutover_ready:
        print("NOT CUTOVER-READY: Phase 7 gate is not ready.", file=sys.stderr)
        return 3 if report.mode == "dry-run" else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
