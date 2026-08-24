from __future__ import annotations

from pathlib import Path
import io
import json
import sqlite3
from contextlib import redirect_stderr, redirect_stdout

from sqlalchemy import create_engine, text

from backend.app.db.models import Base
from backend.app.runtime_schema import expected_alembic_head_revision
from tools import build_phase7_cutover_readiness as readiness
from tools import import_legacy_production as ilp


def sample_snapshot() -> dict[str, list[dict[str, str]]]:
    return {
        "db.cty": [
            {"ID": "1", "TÊN CÔNG TY": "Company A", "COMPANY NAME": "Company A", "TÊN VIẾT TẮT": "CA", "ĐỊA CHỈ TRỤ SỞ": "Addr A", "LEGAL ADDRESS": "Addr A"},
        ],
        "db.cso": [
            {"ID": "10", "ID Cty": "1", "TÊN CƠ SỞ": "Site A", "SITE NAME": "Site A", "ĐỊA CHỈ CƠ SỞ": "Site Addr", "SITE ADDRESS": "Site Addr", "TỈNH/TP": "HN", "TÊN VIẾT TẮT": "SA"},
        ],
        "db.ktra": [
            {"ID": "100", "LOẠI KT": "GMP", "ID CƠ SỞ": "10", "MÃ DC": "A", "TIÊU CHUẨN ÁP DỤNG": "WHO-GMP", "LOẠI KIỂM TRA": "Tái", "Ngày nộp": "2016-06-17 00:00:00", "Mã hồ sơ": "37/GPs", "Ngày thẩm định": "2016-08-02 00:00:00", "Người thẩm định": "Assessor", "Kết quả": "Đạt", "Ngày K.tra": "2016-08-27 00:00:00", "Q. định": "368/QĐ-QLD", "B. bản": "2016-08-27 00:00:00"},
        ],
        "db.cc": [
            {"ID": "200", "MỚI NHẤT": "-", "ID MỚI NHẤT": "", "LOẠI CC": "GMP", "ID ĐỢT KTRA": "100", "ID CƠ SỞ": "10", "MÃ DC": "A"},
        ],
        "db.dkkd": [
            {"ID": "300", "MỚI NHẤT": "-", "ID MỚI NHẤT": "", "ID CƠ SỞ": "10", "ID CTY": "1", "NGƯỜI CHỊU TRÁCH NHIỆM CHUYÊN MÔN": "Pharmacist", "ID CC": "200"},
        ],
        "db.Tdoi": [
            {"ID": "400", "PHẠM VI": "-", "MÔ TẢ": "Đổi tên", "ID CƠ SỞ": "10", "Ngày nộp": "2016-02-22 00:00:00", "ĐƠN VỊ ĐỀ NGHỊ": "Unit", "Ngày hiệu lực của TĐ": "2016-03-08 00:00:00"},
        ],
        "db.Tdoi2": [
            {"ID": "500", "ID Gốc": "400", "ID Phân loại": "", "PHÂN LOẠI": "Đổi tên", "TÌNH TRẠNG CHẤP NHẬN": "", "THÔNG TIN CŨ": "Old", "THÔNG TIN MỚI": "New", "GHI CHÚ": ""},
        ],
    }


def write_snapshot(path: Path, payload: dict[str, list[dict[str, str]]] | None = None) -> Path:
    path.write_text(json.dumps(payload or sample_snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_runtime_env(path: Path, *, password: str = "secret-password") -> Path:
    path.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "DB_MODE=local_postgres",
                "DB_NAME=gxp_qlcl",
                "DB_USER=gxp_app",
                f"DB_PASSWORD={password!r}",
                "DB_HOST=127.0.0.1",
                "DB_PORT=5432",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def prepare_runtime_db(path: Path) -> str:
    database_url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    head = expected_alembic_head_revision()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("DELETE FROM alembic_version"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"), {"version_num": head})
    return database_url


def count_rows(db_path: Path, table: str) -> int:
    con = sqlite3.connect(str(db_path))
    try:
        return int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    finally:
        con.close()


def patch_runtime(monkeypatch, database_url: str, runtime_env: Path) -> None:
    contract = ilp.RuntimeDatabaseContract(
        runtime_env_path=runtime_env,
        app_env="production",
        db_mode="local_postgres",
        db_name="gxp_qlcl",
        db_user="gxp_app",
        database_url=database_url,
        database_url_redacted="sqlite:///***",
    )
    monkeypatch.setattr(ilp, "_load_runtime_database_contract", lambda runtime_env_path: (contract, {}))
    monkeypatch.setattr(
        ilp,
        "_load_phase7_gate",
        lambda: ("ready", {"status": "pass", "reason": "ok"}, True),
    )
    monkeypatch.setattr(ilp, "_run_backup", lambda runtime_env_path: None)


def patch_phase7_artifact_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(readiness, "PHASE3_PATH", tmp_path / "phase3r.json")
    monkeypatch.setattr(readiness, "PHASE4_PATH", tmp_path / "phase4.json")
    monkeypatch.setattr(readiness, "PHASE5_PATH", tmp_path / "phase5.json")
    monkeypatch.setattr(readiness, "PHASE6_PATH", tmp_path / "phase6.json")
    monkeypatch.setattr(readiness, "PHASE3P_PATH", tmp_path / "phase3p.json")
    monkeypatch.setattr(readiness, "PHASE3S_PATH", tmp_path / "phase3s.json")


def write_phase7_closeout_artifacts(tmp_path: Path) -> None:
    (tmp_path / "phase4.json").write_text(json.dumps({"phase4_status": "closed"}), encoding="utf-8")
    (tmp_path / "phase5.json").write_text(json.dumps({"phase5_status": "closed"}), encoding="utf-8")
    (tmp_path / "phase6.json").write_text(
        json.dumps({"phase6_status": "closed", "required_outstanding": []}),
        encoding="utf-8",
    )
    (tmp_path / "phase3p.json").write_text(
        json.dumps({"conflict_count": 0, "manual_review_count": 0}),
        encoding="utf-8",
    )


def load_real_phase7_gate() -> tuple[str, dict[str, str], bool]:
    report = readiness.build_readiness()
    phase7_status = str(report.get("phase7_status", "blocked"))
    current_projection_gate = report.get("gates", {}).get(
        "current_projection_conflicts",
        {"status": "blocked", "reason": "Current projection gate is unavailable."},
    )
    return phase7_status, current_projection_gate, phase7_status == "ready"


def test_snapshot_only_apply_path_does_not_require_xlsb(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json")
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)

    report = ilp.execute_import(
        snapshot_path=snapshot_path,
        runtime_env_path=runtime_env,
        mode="dry-run",
        report_root=tmp_path / "reports",
    )

    assert report.mode == "dry-run"
    assert count_rows(db_path, "company") == 0
    assert count_rows(db_path, "legacy_id_map") == 0


def test_apply_commits_import_and_second_run_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json")
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)

    first = ilp.execute_import(snapshot_path=snapshot_path, runtime_env_path=runtime_env, mode="apply", report_root=tmp_path / "reports")
    second = ilp.execute_import(snapshot_path=snapshot_path, runtime_env_path=runtime_env, mode="apply", report_root=tmp_path / "reports")

    assert count_rows(db_path, "company") == 1
    assert count_rows(db_path, "site") == 1
    assert count_rows(db_path, "case") == 1
    assert count_rows(db_path, "legacy_id_map") >= 6
    assert first.reconciliation["inserted_counts"]["company"] == 1
    assert second.reconciliation["inserted_counts"] == {}
    assert second.reconciliation["existing_counts"]["company"] == 1
    assert all(row["balanced"] for row in second.reconciliation["source_balance"].values())


def test_apply_rolls_back_on_injected_failure(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json")
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)

    original_import_snapshot = ilp.import_snapshot

    def exploding_import_snapshot(*args, **kwargs):
        original_import_snapshot(*args, **kwargs)
        raise RuntimeError("boom")

    monkeypatch.setattr(ilp, "import_snapshot", exploding_import_snapshot)
    try:
        ilp.execute_import(snapshot_path=snapshot_path, runtime_env_path=runtime_env, mode="apply", report_root=tmp_path / "reports")
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("Expected injected failure")

    assert count_rows(db_path, "company") == 0
    assert count_rows(db_path, "legacy_id_map") == 0


def test_duplicate_legacy_key_fails_closed(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot = sample_snapshot()
    snapshot["db.cty"].append({"ID": "1", "TÊN CÔNG TY": "Company B"})
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot)
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)

    try:
        ilp.execute_import(snapshot_path=snapshot_path, runtime_env_path=runtime_env, mode="dry-run", report_root=tmp_path / "reports")
    except ilp.ImportCollisionError as exc:
        assert "Duplicate source row key" in str(exc)
    else:
        raise AssertionError("Expected duplicate key failure")


def test_orphan_fk_blocks_import(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot = sample_snapshot()
    snapshot["db.cso"][0]["ID Cty"] = "999"
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot)
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)

    try:
        ilp.execute_import(snapshot_path=snapshot_path, runtime_env_path=runtime_env, mode="dry-run", report_root=tmp_path / "reports")
    except ilp.ProductionImportError as exc:
        assert "unresolved anomalies" in str(exc)
    else:
        raise AssertionError("Expected unresolved anomaly failure")


def test_existing_runtime_collision_fails_closed(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json")
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)

    engine = create_engine(database_url, future=True)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO company (id, legacy_company_id, legal_name, is_inactive, created_at, updated_at) VALUES ('11111111-1111-1111-1111-111111111111', 1, 'Manual', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
        )

    try:
        ilp.execute_import(snapshot_path=snapshot_path, runtime_env_path=runtime_env, mode="apply", report_root=tmp_path / "reports")
    except ilp.ImportCollisionError as exc:
        assert "missing LegacyIdMap lineage" in str(exc)
    else:
        raise AssertionError("Expected collision failure")


def test_wrong_alembic_revision_blocks_apply(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json")
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)

    engine = create_engine(database_url, future=True)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM alembic_version"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('wrong-revision')"))

    try:
        ilp.execute_import(snapshot_path=snapshot_path, runtime_env_path=runtime_env, mode="apply", report_root=tmp_path / "reports")
    except ilp.ProductionImportError as exc:
        assert "Alembic revision mismatch" in str(exc)
    else:
        raise AssertionError("Expected Alembic gate failure")


def test_backup_failure_blocks_apply_before_mutation(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json")
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    monkeypatch.setattr(ilp, "_run_backup", lambda runtime_env_path: (_ for _ in ()).throw(ilp.ProductionImportError("backup failed")))

    try:
        ilp.execute_import(snapshot_path=snapshot_path, runtime_env_path=runtime_env, mode="apply", report_root=tmp_path / "reports")
    except ilp.ProductionImportError as exc:
        assert "backup failed" in str(exc)
    else:
        raise AssertionError("Expected backup gate failure")

    assert count_rows(db_path, "company") == 0


def test_missing_and_invalid_runtime_env_fail_closed(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.env"
    try:
        ilp._load_runtime_database_contract(missing_path)
    except ilp.ProductionImportError as exc:
        assert "Runtime env file not found" in str(exc)
    else:
        raise AssertionError("Expected missing runtime env failure")

    invalid_path = tmp_path / "invalid.env"
    invalid_path.write_text("APP_ENV\n", encoding="utf-8")
    try:
        ilp._load_runtime_database_contract(invalid_path)
    except ValueError as exc:
        assert "Invalid env line" in str(exc)
    else:
        raise AssertionError("Expected invalid runtime env failure")


def test_main_never_logs_passwords(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env", password="very-secret")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json")
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = ilp.main(
            [
                "--snapshot",
                str(snapshot_path),
                "--runtime-env",
                str(runtime_env),
                "--dry-run",
                "--report-root",
                str(tmp_path / "reports"),
            ]
        )
    combined = stdout.getvalue() + stderr.getvalue()
    assert code == 0
    assert "very-secret" not in combined


def test_dry_run_reports_not_cutover_ready_without_blocking_apply(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json")
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    monkeypatch.setattr(
        ilp,
        "_load_phase7_gate",
        lambda: ("blocked", {"status": "blocked", "reason": "pending decisions"}, False),
    )

    dry_run_code = ilp.main(
        [
            "--snapshot",
            str(snapshot_path),
            "--runtime-env",
            str(runtime_env),
            "--dry-run",
            "--report-root",
            str(tmp_path / "reports"),
        ]
    )
    apply_code = ilp.main(
        [
            "--snapshot",
            str(snapshot_path),
            "--runtime-env",
            str(runtime_env),
            "--apply",
            "--report-root",
            str(tmp_path / "reports"),
        ]
    )

    assert dry_run_code == 3
    assert apply_code == 0
    assert count_rows(db_path, "company") == 1


def test_dry_run_with_missing_phase7_artifacts_creates_report_without_traceback(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json")
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_phase7_artifact_paths(monkeypatch, tmp_path)
    write_phase7_closeout_artifacts(tmp_path)
    monkeypatch.setattr(ilp, "_load_phase7_gate", load_real_phase7_gate)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = ilp.main(
            [
                "--snapshot",
                str(snapshot_path),
                "--runtime-env",
                str(runtime_env),
                "--dry-run",
                "--report-root",
                str(tmp_path / "reports"),
            ]
        )

    report_dirs = sorted((tmp_path / "reports").iterdir())
    report = json.loads((report_dirs[-1] / "report.json").read_text(encoding="utf-8"))
    combined = stdout.getvalue() + stderr.getvalue()

    assert code == 3
    assert "Traceback" not in combined
    assert count_rows(db_path, "company") == 0
    assert report["validation_status"] == "pass"
    assert report["cutover_ready"] is False
    assert report["phase7_status"] == "blocked"
    assert "Report directory:" in combined


def test_import_validation_failure_is_not_masked_by_cutover_status(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot = sample_snapshot()
    snapshot["db.cso"][0]["ID Cty"] = "999"
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot)
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_phase7_artifact_paths(monkeypatch, tmp_path)
    write_phase7_closeout_artifacts(tmp_path)
    monkeypatch.setattr(ilp, "_load_phase7_gate", load_real_phase7_gate)

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        code = ilp.main(
            [
                "--snapshot",
                str(snapshot_path),
                "--runtime-env",
                str(runtime_env),
                "--dry-run",
                "--report-root",
                str(tmp_path / "reports"),
            ]
        )

    assert code == 1
    assert "unresolved anomalies" in stderr.getvalue()
