from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import argparse
import json
import os
import secrets
import shlex
import subprocess
import sys
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import PRODUCTION_ENV_NAMES, load_app_config, resolve_database_url
from backend.app.db.session import build_session_factory
from backend.app.domain.legacy_snapshot import CORE_SHEETS
from backend.app.domain.phase2_import import (
    ImportExecutionOptions,
    ImportCollisionError,
    SchemaLengthValidationError,
    import_snapshot,
)
from backend.app.project_paths import phase_artifact_path
from backend.app.runtime_schema import expected_alembic_head_revision
from tools.build_phase7_cutover_readiness import build_readiness
from tools.env_utils import parse_env_file


DEFAULT_RUNTIME_ENV_PATH = Path("/etc/gxp/runtime.env")
DEFAULT_SNAPSHOT_PATH = phase_artifact_path("phase3c", "legacy_snapshot.json")
DEFAULT_REPORT_ROOT = phase_artifact_path("legacy-production")
DEFAULT_VALIDATION_TARGET_DB_PREFIX = "gxp_legacy_validation"
DEFAULT_REHEARSAL_TARGET_DB = "gxp_legacy_rehearsal"
DEFAULT_FINAL_TARGET_DB = "gxp_qlcl_candidate"


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
    import_mode: str
    validation_isolation: str
    runtime_env_path: str
    snapshot_path: str
    snapshot_sha256: str
    snapshot_exported_at: str | None
    source_workbook_identity: str | None
    report_dir: str
    started_at_utc: str
    completed_at_utc: str
    deployment_git_sha: str
    alembic_head_revision: str | None
    alembic_current_revision: str | None
    database_url_redacted: str
    canonical_production_database: str
    target_database: str
    validation_status: str
    cutover_ready: bool
    phase7_status: str
    current_projection_gate: dict[str, Any]
    backup_status: str
    cleanup_status: str
    error_message: str | None
    reconciliation: dict[str, Any]


def _redact_database_url(url: str) -> str:
    return _render_database_url(url, hide_password=True)


def _render_database_url(url: str | URL, *, hide_password: bool) -> str:
    parsed = make_url(url) if isinstance(url, str) else url
    if parsed.drivername.startswith("sqlite"):
        return str(parsed)
    return parsed.render_as_string(hide_password=hide_password)


def _target_database_url(database_url: str, target_database_name: str) -> str:
    url = make_url(database_url)
    if url.drivername.startswith("sqlite"):
        if not url.database:
            raise ProductionImportError("SQLite target database URL is missing a database path.")
        current_path = Path(url.database)
        target_path = current_path.with_name(f"{target_database_name}{current_path.suffix or '.db'}")
        return f"sqlite:///{target_path.as_posix()}"
    return _render_database_url(url.set(database=target_database_name), hide_password=False)


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


def _load_snapshot(snapshot_path: Path) -> tuple[dict[str, list[dict[str, str]]], str, dict[str, Any]]:
    if not snapshot_path.exists():
        raise ProductionImportError(f"Snapshot file not found: {snapshot_path}")
    payload = snapshot_path.read_bytes()
    snapshot_sha = sha256(payload).hexdigest()
    try:
        raw_snapshot = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ProductionImportError(f"Snapshot JSON is invalid: {snapshot_path}: {exc}") from exc
    if not isinstance(raw_snapshot, dict):
        raise ProductionImportError("Snapshot root must be a JSON object.")
    metadata: dict[str, Any] = {}
    if all(sheet in raw_snapshot for sheet in CORE_SHEETS):
        snapshot = raw_snapshot
    elif isinstance(raw_snapshot.get("sheets"), dict) and all(sheet in raw_snapshot["sheets"] for sheet in CORE_SHEETS):
        snapshot = raw_snapshot["sheets"]
        if isinstance(raw_snapshot.get("metadata"), dict):
            metadata = dict(raw_snapshot["metadata"])
    else:
        raise ProductionImportError("Snapshot JSON does not contain the required legacy sheets.")
    missing_sheets = [sheet for sheet in CORE_SHEETS if sheet not in snapshot]
    if missing_sheets:
        raise ProductionImportError(f"Snapshot is missing required sheets: {', '.join(missing_sheets)}.")
    for sheet in CORE_SHEETS:
        rows = snapshot[sheet]
        if not isinstance(rows, list):
            raise ProductionImportError(f"Snapshot sheet {sheet!r} must be a list of rows.")
    return snapshot, snapshot_sha, metadata


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
        f"- Import mode: `{report.import_mode}`",
        f"- Validation isolation: `{report.validation_isolation}`",
        f"- Snapshot: `{report.snapshot_path}`",
        f"- Snapshot SHA-256: `{report.snapshot_sha256}`",
        f"- Snapshot exported at: `{report.snapshot_exported_at}`",
        f"- Source workbook identity: `{report.source_workbook_identity}`",
        f"- Runtime env: `{report.runtime_env_path}`",
        f"- Canonical production database: `{report.canonical_production_database}`",
        f"- Target database: `{report.target_database}`",
        f"- Database: `{report.database_url_redacted}`",
        f"- Alembic current/head: `{report.alembic_current_revision}` / `{report.alembic_head_revision}`",
        f"- Validation status: `{report.validation_status}`",
        f"- Phase 7 status: `{report.phase7_status}`",
        f"- Cutover ready: `{str(report.cutover_ready).lower()}`",
        f"- Backup status: `{report.backup_status}`",
        f"- Cleanup status: `{report.cleanup_status}`",
        "",
    ]
    if report.error_message:
        lines.extend(
            [
                "## Validation Error",
                "",
                report.error_message,
                "",
            ]
        )
    lines.extend(
        [
            "## Source Balance",
            "",
            "| Sheet | Source | Imported | Skipped | Excluded | Unresolved | Balanced |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    source_balance = reconciliation.get("source_balance", {})
    if source_balance:
        for sheet in CORE_SHEETS:
            row = source_balance[sheet]
            lines.append(
                f"| `{sheet}` | {row['source_count']} | {row['imported_count']} | {row['skipped_count']} | "
                f"{row['intentionally_skipped_count']} | {row['unresolved_count']} | `{row['balanced']}` |"
            )
    else:
        lines.append("| `n/a` | 0 | 0 | 0 | 0 | 0 | `False` |")
    lines.extend(
        [
            "",
            "## Counts",
            "",
            f"- Inserted counts: `{json.dumps(reconciliation.get('inserted_counts', {}), ensure_ascii=False)}`",
            f"- Existing counts: `{json.dumps(reconciliation.get('existing_counts', {}), ensure_ascii=False)}`",
            f"- Skipped rows: `{json.dumps(reconciliation.get('skipped_rows', {}), ensure_ascii=False)}`",
            f"- Excluded rows: `{json.dumps(reconciliation.get('excluded_rows', {}), ensure_ascii=False)}`",
            f"- Schema length violations: `{json.dumps(reconciliation.get('schema_length_violations', []), ensure_ascii=False)}`",
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


def _schema_length_violations_payload(exc: SchemaLengthValidationError) -> list[dict[str, Any]]:
    return [
        {
            "sheet": violation.sheet,
            "source_label": violation.source_label,
            "source_row_key": violation.source_row_key,
            "target": violation.target,
            "actual_length": violation.actual_length,
            "max_length": violation.max_length,
            "classification": violation.classification,
            "sample": violation.sample,
        }
        for violation in exc.violations
    ]


def _snapshot_metadata_value(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _validation_target_database_name() -> str:
    return f"{DEFAULT_VALIDATION_TARGET_DB_PREFIX}_{secrets.token_hex(4)}"


def _postgres_admin_prefix() -> list[str]:
    override = os.environ.get("POSTGRES_ADMIN_CMD", "").strip()
    if override:
        return shlex.split(override)
    geteuid = getattr(os, "geteuid", None)
    if callable(geteuid) and geteuid() == 0:
        return ["runuser", "-u", "postgres", "--"]
    raise ProductionImportError(
        "Rebuild import that creates/drops local PostgreSQL databases must run as root or set POSTGRES_ADMIN_CMD explicitly."
    )


def _run_subprocess(command: list[str], *, env: dict[str, str] | None = None) -> None:
    completed = subprocess.run(command, cwd=str(ROOT), env=env, capture_output=True, text=True)
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip() or f"command failed: {command!r}"
        raise ProductionImportError(stderr)


def _recreate_target_database(contract: RuntimeDatabaseContract, target_database_name: str, target_database_url: str) -> None:
    if target_database_name == contract.db_name:
        raise ProductionImportError(
            f"Target database {target_database_name!r} must not match the canonical production database name {contract.db_name!r}."
        )
    if target_database_name == "":
        raise ProductionImportError("Target database name must not be blank.")

    if target_database_url.startswith("sqlite:///"):
        database_path = Path(target_database_url.removeprefix("sqlite:///"))
        if database_path.exists():
            database_path.unlink()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        return

    if contract.db_mode != "local_postgres":
        raise ProductionImportError(f"Reset-from-snapshot is only supported for local_postgres, got {contract.db_mode!r}.")

    admin_prefix = _postgres_admin_prefix()
    _run_subprocess(admin_prefix + ["dropdb", "--if-exists", target_database_name])
    _run_subprocess(admin_prefix + ["createdb", "--owner", contract.db_user, target_database_name])


def _drop_target_database(contract: RuntimeDatabaseContract, target_database_name: str, target_database_url: str) -> None:
    if target_database_url.startswith("sqlite:///"):
        database_path = Path(target_database_url.removeprefix("sqlite:///"))
        if database_path.exists():
            database_path.unlink()
        return

    if contract.db_mode != "local_postgres":
        raise ProductionImportError(f"Temporary validation cleanup is only supported for local_postgres, got {contract.db_mode!r}.")

    admin_prefix = _postgres_admin_prefix()
    _run_subprocess(admin_prefix + ["dropdb", "--if-exists", target_database_name])


def _upgrade_target_database_schema(database_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    _run_subprocess([sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", "head"], env=env)


def _concise_database_error(message: str) -> str:
    lowered = message.lower()
    if "password authentication failed" in lowered:
        return "PostgreSQL authentication failed"
    if "authentication failed" in lowered:
        return "Database authentication failed"
    if "could not connect" in lowered or "connection refused" in lowered:
        return "PostgreSQL connection failed"
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("Traceback"):
            continue
        if line.startswith("File "):
            continue
        return line
    return message.strip() or "database operation failed"


def _execute_reset_import(
    *,
    contract: RuntimeDatabaseContract,
    snapshot: dict[str, list[dict[str, str]]],
    target_database_name: str,
    execution_label: str,
) -> tuple[dict[str, Any], str | None, str | None, str]:
    target_database_url = _target_database_url(contract.database_url, target_database_name)
    _recreate_target_database(contract, target_database_name, target_database_url)
    try:
        _upgrade_target_database_schema(target_database_url)
    except ProductionImportError as exc:
        raise ProductionImportError(f"{execution_label} schema migration failed: {_concise_database_error(str(exc))}") from exc
    reconciliation, current_revision, head_revision = _run_import(
        database_url=target_database_url,
        snapshot=snapshot,
        dry_run=False,
        require_head_revision=True,
    )
    return reconciliation, current_revision, head_revision, _redact_database_url(target_database_url)


def _run_import(
    *,
    database_url: str,
    snapshot: dict[str, list[dict[str, str]]],
    dry_run: bool,
    require_head_revision: bool,
) -> tuple[dict[str, Any], str | None, str | None]:
    factory = build_session_factory(database_url)
    bind = factory.kw.get("bind")
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
        if bind is not None:
            bind.dispose()


def execute_import(
    *,
    snapshot_path: Path,
    runtime_env_path: Path,
    mode: str,
    import_mode: str = "validation",
    target_database_name: str | None = None,
    reset_from_snapshot: bool = False,
    report_root: Path = DEFAULT_REPORT_ROOT,
) -> ImportReport:
    contract, _env = _load_runtime_database_contract(runtime_env_path)
    snapshot, snapshot_sha, snapshot_metadata = _load_snapshot(snapshot_path)
    phase7_status, current_projection_gate, cutover_ready = _load_phase7_gate()
    report_dir = _build_report_dir(report_root)
    started_at = datetime.now(timezone.utc).isoformat()
    exported_at = _snapshot_metadata_value(snapshot_metadata, "exported_at")
    source_workbook_identity = (
        _snapshot_metadata_value(snapshot_metadata, "source_workbook_identity")
        or _snapshot_metadata_value(snapshot_metadata, "source_workbook")
    )
    validation_isolation = "clean_temporary_database" if import_mode == "validation" else "persistent_rebuild_database"
    cleanup_status = "not-required"
    database_url_redacted = contract.database_url_redacted
    current_revision: str | None = None
    head_revision: str | None = None
    reconciliation: dict[str, Any] = {}
    error_message: str | None = None
    primary_error: Exception | None = None
    cleanup_error_message: str | None = None
    validation_target_database_url: str | None = None

    if mode == "dry-run":
        if import_mode != "validation":
            raise ProductionImportError("Dry-run currently supports only --import-mode validation.")
        if reset_from_snapshot:
            raise ProductionImportError("--reset-from-snapshot is not valid with --dry-run.")
        effective_target_database = target_database_name or _validation_target_database_name()
        validation_target_database_url = _target_database_url(contract.database_url, effective_target_database)
        database_url_redacted = _redact_database_url(validation_target_database_url)
        execution_label = "Temporary validation"
    else:
        if import_mode not in {"rehearsal", "final"}:
            raise ProductionImportError("--apply requires --import-mode rehearsal or --import-mode final.")
        if not reset_from_snapshot:
            raise ProductionImportError("--apply with rehearsal/final import mode requires --reset-from-snapshot.")
        if target_database_name is None:
            target_database_name = (
                DEFAULT_REHEARSAL_TARGET_DB if import_mode == "rehearsal" else DEFAULT_FINAL_TARGET_DB
            )
        effective_target_database = target_database_name
        execution_label = "Rehearsal target" if import_mode == "rehearsal" else "Final candidate"

    backup_status = "not-run"
    if mode == "apply" and import_mode == "final":
        _run_backup(runtime_env_path)
        backup_status = "ok"

    try:
        if mode == "dry-run":
            reconciliation, current_revision, head_revision, database_url_redacted = _execute_reset_import(
                contract=contract,
                snapshot=snapshot,
                target_database_name=effective_target_database,
                execution_label=execution_label,
            )
        else:
            reconciliation, current_revision, head_revision, database_url_redacted = _execute_reset_import(
                contract=contract,
                snapshot=snapshot,
                target_database_name=effective_target_database,
                execution_label=execution_label,
            )
    except SchemaLengthValidationError as exc:
        primary_error = exc
        head_revision = expected_alembic_head_revision()
        reconciliation = {"schema_length_violations": _schema_length_violations_payload(exc)}
    except Exception as exc:
        primary_error = exc
    finally:
        if mode == "dry-run" and validation_target_database_url is not None:
            try:
                _drop_target_database(contract, effective_target_database, validation_target_database_url)
                cleanup_status = "ok"
            except Exception as cleanup_exc:
                cleanup_error_message = str(cleanup_exc)
                cleanup_status = f"failed: orphan temporary validation database {effective_target_database!r}: {cleanup_error_message}"

    if primary_error is None and cleanup_error_message is None:
        validation_status = "pass"
    else:
        validation_status = "failed"

    if cleanup_error_message is not None:
        cleanup_fragment = f"Validation cleanup failed for temporary database {effective_target_database!r}: {cleanup_error_message}"
        if primary_error is None:
            error_message = cleanup_fragment
        else:
            error_message = f"{primary_error} {cleanup_fragment}"
    elif primary_error is not None:
        error_message = str(primary_error)

    report = ImportReport(
        mode=mode,
        import_mode=import_mode,
        validation_isolation=validation_isolation,
        runtime_env_path=str(runtime_env_path),
        snapshot_path=str(snapshot_path),
        snapshot_sha256=snapshot_sha,
        snapshot_exported_at=exported_at,
        source_workbook_identity=source_workbook_identity,
        report_dir=str(report_dir),
        started_at_utc=started_at,
        completed_at_utc=datetime.now(timezone.utc).isoformat(),
        deployment_git_sha=_git_sha(),
        alembic_head_revision=head_revision,
        alembic_current_revision=current_revision,
        database_url_redacted=database_url_redacted,
        canonical_production_database=contract.db_name,
        target_database=effective_target_database,
        validation_status=validation_status,
        cutover_ready=cutover_ready,
        phase7_status=phase7_status,
        current_projection_gate=current_projection_gate,
        backup_status=backup_status,
        cleanup_status=cleanup_status,
        error_message=error_message,
        reconciliation=reconciliation,
    )
    _write_report(report_dir, report)
    if primary_error is None and cleanup_error_message is None:
        return report
    if primary_error is None:
        raise ProductionImportError(error_message)
    if isinstance(primary_error, SchemaLengthValidationError):
        raise ProductionImportError(error_message) from primary_error
    if cleanup_error_message is None:
        raise primary_error
    if isinstance(primary_error, ImportCollisionError):
        raise ImportCollisionError(error_message) from primary_error
    if isinstance(primary_error, ProductionImportError):
        raise ProductionImportError(error_message) from primary_error
    raise type(primary_error)(error_message) from primary_error


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
    parser.add_argument(
        "--import-mode",
        choices=("validation", "rehearsal", "final"),
        default="validation",
        help="validation performs a transactional dry-run against the configured runtime database; "
        "rehearsal/final rebuild an explicit non-production target database from the snapshot.",
    )
    parser.add_argument(
        "--target-db",
        help="Explicit rebuild target database name for rehearsal/final apply modes. "
        f"Defaults to {DEFAULT_REHEARSAL_TARGET_DB!r} for rehearsal and {DEFAULT_FINAL_TARGET_DB!r} for final.",
    )
    parser.add_argument(
        "--reset-from-snapshot",
        action="store_true",
        help="Required for rehearsal/final apply. Recreates the target database, upgrades schema head, then imports the full snapshot.",
    )
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
            import_mode=args.import_mode,
            target_database_name=args.target_db,
            reset_from_snapshot=args.reset_from_snapshot,
            report_root=args.report_root,
        )
    except (ProductionImportError, ImportCollisionError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Legacy import {report.mode} completed.")
    print(f"Import mode: {report.import_mode}")
    print(f"Report directory: {report.report_dir}")
    print(f"Snapshot SHA-256: {report.snapshot_sha256}")
    if report.snapshot_exported_at:
        print(f"Snapshot exported at: {report.snapshot_exported_at}")
    if report.source_workbook_identity:
        print(f"Source workbook identity: {report.source_workbook_identity}")
    print(f"Target database: {report.target_database}")
    print(f"Database: {report.database_url_redacted}")
    print(f"Phase 7 status: {report.phase7_status}")
    if not report.cutover_ready:
        print("NOT CUTOVER-READY: Phase 7 gate is not ready.", file=sys.stderr)
        return 3 if report.mode == "dry-run" else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
