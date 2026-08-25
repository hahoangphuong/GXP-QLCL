from __future__ import annotations

from pathlib import Path
import io
import json
import sqlite3
from contextlib import redirect_stderr, redirect_stdout

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from backend.app.db.models import Base, MigrationAnomaly
from backend.app.runtime_schema import expected_alembic_head_revision
from tools import build_phase7_cutover_readiness as readiness
from tools import import_legacy_production as ilp


def legacy_row_set(
    *,
    company_id: str,
    company_name: str,
    site_id: str,
    site_name: str,
    inspection_id: str,
    certificate_id: str,
    business_id: str,
    change_request_id: str,
    change_detail_id: str,
    company_short_name: str | None = None,
    company_site_link_id: str | None = None,
) -> dict[str, list[dict[str, str]]]:
    company_site_link_id = company_site_link_id or company_id
    return {
        "db.cty": [
            {
                "ID": company_id,
                "TÊN CÔNG TY": company_name,
                "COMPANY NAME": company_name,
                "TÊN VIẾT TẮT": company_short_name or company_name[:3].upper(),
                "ĐỊA CHỈ TRỤ SỞ": f"Addr {company_id}",
                "LEGAL ADDRESS": f"Addr {company_id}",
            },
        ],
        "db.cso": [
            {
                "ID": site_id,
                "ID Cty": company_site_link_id,
                "TÊN CƠ SỞ": site_name,
                "SITE NAME": site_name,
                "ĐỊA CHỈ CƠ SỞ": f"Site Addr {site_id}",
                "SITE ADDRESS": f"Site Addr {site_id}",
                "TỈNH/TP": "HN",
                "TÊN VIẾT TẮT": site_name[:3].upper(),
            },
        ],
        "db.ktra": [
            {
                "ID": inspection_id,
                "LOẠI KT": "GMP",
                "ID CƠ SỞ": site_id,
                "MÃ DC": f"A{inspection_id}",
                "TIÊU CHUẨN ÁP DỤNG": "WHO-GMP",
                "LOẠI KIỂM TRA": "Tái",
                "Ngày nộp": "2016-06-17 00:00:00",
                "Mã hồ sơ": f"HS-{inspection_id}",
                "Ngày thẩm định": "2016-08-02 00:00:00",
                "Người thẩm định": "Assessor",
                "Kết quả": "Đạt",
                "Ngày K.tra": "2016-08-27 00:00:00",
                "Q. định": f"QD-{inspection_id}",
                "B. bản": "2016-08-27 00:00:00",
            },
        ],
        "db.cc": [
            {
                "ID": certificate_id,
                "MỚI NHẤT": "-",
                "ID MỚI NHẤT": "",
                "LOẠI CC": "GMP",
                "ID ĐỢT KTRA": inspection_id,
                "ID CƠ SỞ": site_id,
                "MÃ DC": f"A{certificate_id}",
            },
        ],
        "db.dkkd": [
            {
                "ID": business_id,
                "MỚI NHẤT": "-",
                "ID MỚI NHẤT": "",
                "ID CƠ SỞ": site_id,
                "ID CTY": company_site_link_id,
                "NGƯỜI CHỊU TRÁCH NHIỆM CHUYÊN MÔN": "Pharmacist",
                "ID CC": certificate_id,
            },
        ],
        "db.Tdoi": [
            {
                "ID": change_request_id,
                "PHẠM VI": "-",
                "MÔ TẢ": f"Đổi tên {site_name}",
                "ID CƠ SỞ": site_id,
                "Ngày nộp": "2016-02-22 00:00:00",
                "ĐƠN VỊ ĐỀ NGHỊ": "Unit",
                "Ngày hiệu lực của TĐ": "2016-03-08 00:00:00",
            },
        ],
        "db.Tdoi2": [
            {
                "ID": change_detail_id,
                "ID Gốc": change_request_id,
                "ID Phân loại": "",
                "PHÂN LOẠI": "Đổi tên",
                "TÌNH TRẠNG CHẤP NHẬN": "",
                "THÔNG TIN CŨ": "Old",
                "THÔNG TIN MỚI": "New",
                "GHI CHÚ": "",
            },
        ],
    }


def sample_snapshot() -> dict[str, list[dict[str, str]]]:
    return legacy_row_set(
        company_id="1",
        company_name="Company A",
        site_id="10",
        site_name="Site A",
        inspection_id="100",
        certificate_id="200",
        business_id="300",
        change_request_id="400",
        change_detail_id="500",
        company_short_name="CA",
    )


def merge_snapshot_sets(*row_sets: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
    merged = {sheet: [] for sheet in sample_snapshot()}
    for row_set in row_sets:
        for sheet, rows in row_set.items():
            merged[sheet].extend(rows)
    return merged


def snapshot_wrapper(
    payload: dict[str, list[dict[str, str]]],
    *,
    exported_at: str = "2026-08-24T00:00:00Z",
    source_workbook_identity: str = "Danh sách Kiểm tra GPs.xlsb",
) -> dict[str, object]:
    return {
        "metadata": {
            "exported_at": exported_at,
            "source_workbook_identity": source_workbook_identity,
        },
        "sheets": payload,
    }


def write_snapshot(path: Path, payload: dict[str, object] | dict[str, list[dict[str, str]]] | None = None) -> Path:
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
    engine.dispose()
    return database_url


def count_rows(db_path: Path, table: str) -> int:
    con = sqlite3.connect(str(db_path))
    try:
        return int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    finally:
        con.close()


def query_scalar(db_path: Path, sql: str, params: tuple[object, ...] = ()) -> object | None:
    con = sqlite3.connect(str(db_path))
    try:
        row = con.execute(sql, params).fetchone()
        return None if row is None else row[0]
    finally:
        con.close()


def sqlite_path_from_url(database_url: str) -> Path:
    assert database_url.startswith("sqlite:///")
    return Path(database_url.removeprefix("sqlite:///"))


def balanced_reconciliation() -> dict[str, object]:
    source_balance = {}
    for sheet in ilp.CORE_SHEETS:
        source_balance[sheet] = {
            "source_count": 0,
            "imported_count": 0,
            "skipped_count": 0,
            "intentionally_skipped_count": 0,
            "unresolved_count": 0,
            "balanced": True,
        }
    return {
        "source_balance": source_balance,
        "inserted_counts": {},
        "existing_counts": {},
        "skipped_rows": {},
        "excluded_rows": {},
        "schema_length_violations": [],
        "anomaly_rows": [],
    }


def validation_db_path(prod_database_url: str, target_database_name: str) -> Path:
    return sqlite_path_from_url(ilp._target_database_url(prod_database_url, target_database_name))


def patch_runtime(monkeypatch, database_url: str, runtime_env: Path) -> None:
    contract = ilp.RuntimeDatabaseContract(
        runtime_env_path=runtime_env,
        app_env="production",
        db_mode="local_postgres",
        db_name="gxp_qlcl",
        db_user="gxp_app",
        database_url=database_url,
        database_url_redacted=ilp._redact_database_url(database_url),
    )
    monkeypatch.setattr(ilp, "_load_runtime_database_contract", lambda runtime_env_path: (contract, {}))
    monkeypatch.setattr(
        ilp,
        "_load_phase7_gate",
        lambda: ("ready", {"status": "pass", "reason": "ok"}, True),
    )
    monkeypatch.setattr(ilp, "_run_backup", lambda runtime_env_path: None)


def patch_target_schema_upgrade(monkeypatch) -> None:
    def fake_upgrade(database_url: str) -> None:
        prepare_runtime_db(sqlite_path_from_url(database_url))

    monkeypatch.setattr(ilp, "_upgrade_target_database_schema", fake_upgrade)


def postgres_database_url(*, password: str, database: str = "gxp_qlcl") -> str:
    return URL.create(
        "postgresql+psycopg",
        username="gxp_app",
        password=password,
        host="127.0.0.1",
        port=5432,
        database=database,
    ).render_as_string(hide_password=False)


def rehearsal_apply(
    *,
    snapshot_path: Path,
    runtime_env_path: Path,
    report_root: Path,
    target_db: str = ilp.DEFAULT_REHEARSAL_TARGET_DB,
) -> ilp.ImportReport:
    return ilp.execute_import(
        snapshot_path=snapshot_path,
        runtime_env_path=runtime_env_path,
        mode="apply",
        import_mode="rehearsal",
        target_database_name=target_db,
        reset_from_snapshot=True,
        report_root=report_root,
    )


def final_apply(
    *,
    snapshot_path: Path,
    runtime_env_path: Path,
    report_root: Path,
    target_db: str = ilp.DEFAULT_FINAL_TARGET_DB,
) -> ilp.ImportReport:
    return ilp.execute_import(
        snapshot_path=snapshot_path,
        runtime_env_path=runtime_env_path,
        mode="apply",
        import_mode="final",
        target_database_name=target_db,
        reset_from_snapshot=True,
        report_root=report_root,
    )


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
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)

    report = ilp.execute_import(
        snapshot_path=snapshot_path,
        runtime_env_path=runtime_env,
        mode="dry-run",
        report_root=tmp_path / "reports",
    )

    assert report.mode == "dry-run"
    assert report.validation_isolation == "clean_temporary_database"
    assert report.canonical_production_database == "gxp_qlcl"
    assert report.cleanup_status == "ok"
    assert count_rows(db_path, "company") == 0
    assert count_rows(db_path, "legacy_id_map") == 0
    assert not validation_db_path(database_url, report.target_database).exists()


def test_target_database_url_preserves_real_postgres_password() -> None:
    database_url = postgres_database_url(password="s3cr3t", database="source")

    target_database_url = ilp._target_database_url(database_url, "target")

    assert "***" not in target_database_url
    parsed = make_url(target_database_url)
    assert parsed.username == "gxp_app"
    assert parsed.password == "s3cr3t"
    assert parsed.database == "target"


def test_target_database_url_round_trips_reserved_password_characters() -> None:
    password = "p@ss:/%# word"
    database_url = postgres_database_url(password=password, database="source")

    target_database_url = ilp._target_database_url(database_url, "target")

    assert "***" not in target_database_url
    parsed = make_url(target_database_url)
    assert parsed.password == password
    assert parsed.database == "target"


def test_redacted_database_url_hides_raw_password() -> None:
    password = "p@ss:/%# word"
    database_url = postgres_database_url(password=password, database="source")

    redacted = ilp._redact_database_url(database_url)

    assert password not in redacted
    assert ":***@" in redacted
    assert redacted.endswith("/source")


def test_upgrade_target_database_schema_passes_executable_url_to_alembic(monkeypatch) -> None:
    password = "s3cr3t"
    target_database_url = ilp._target_database_url(
        postgres_database_url(password=password, database="source"),
        "gxp_legacy_validation_demo",
    )
    captured: dict[str, str] = {}

    def fake_run_subprocess(command, *, env=None):
        captured["command"] = " ".join(command)
        captured["database_url"] = "" if env is None else env["DATABASE_URL"]

    monkeypatch.setattr(ilp, "_run_subprocess", fake_run_subprocess)

    ilp._upgrade_target_database_schema(target_database_url)

    assert "alembic" in captured["command"]
    assert "***" not in captured["database_url"]
    assert make_url(captured["database_url"]).password == password
    assert make_url(captured["database_url"]).database == "gxp_legacy_validation_demo"


def test_validation_uses_clean_temporary_database_and_ignores_existing_production_anomaly_state(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    prod_db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(prod_db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)

    snapshot_v1 = sample_snapshot()
    snapshot_v2 = sample_snapshot()
    snapshot_v2["db.ktra"][0]["Kết quả"] = "Không đạt"
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot_v2.json", snapshot_wrapper(snapshot_v2))

    detail_v1 = json.dumps(
        {
            "source_sheet": "db.ktra",
            "source_row_key": "row:1169",
            "legacy_row_id": "1169",
            "reason": "conflicting_existing_detail",
            "required_field": "legacy_case_id",
            "raw_fk_value": "100",
            "override_value": "",
            "status": "open",
            "detail": {"legacy_result": snapshot_v1["db.ktra"][0]["Kết quả"]},
        },
        ensure_ascii=False,
    )

    engine = create_engine(database_url, future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO company (id, legacy_company_id, legal_name, is_inactive, created_at, updated_at) "
                "VALUES ('11111111-1111-1111-1111-111111111111', 999, 'Production Keep', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO migration_anomaly "
                "(id, source_sheet, source_row_key, legacy_row_id, reason, required_field, raw_fk_value, override_value, status, detail_json, created_at, updated_at) "
                "VALUES "
                "('22222222-2222-2222-2222-222222222222', :source_sheet, :source_row_key, :legacy_row_id, :reason, :required_field, :raw_fk_value, :override_value, :status, :detail_json, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "source_sheet": "db.ktra",
                "source_row_key": "row:1169",
                "legacy_row_id": "1169",
                "reason": "conflicting_existing_detail",
                "required_field": "legacy_case_id",
                "raw_fk_value": "100",
                "override_value": None,
                "status": "open",
                "detail_json": detail_v1,
            },
        )
    engine.dispose()

    original_import_snapshot = ilp.import_snapshot

    def fake_import_snapshot(session, snapshot, remediation_overrides=None, options=None):
        payload = {
            "source_sheet": "db.ktra",
            "source_row_key": "row:1169",
            "legacy_row_id": "1169",
            "reason": "conflicting_existing_detail",
            "required_field": "legacy_case_id",
            "raw_fk_value": "100",
            "override_value": "",
            "status": "open",
            "detail": {"legacy_result": snapshot["db.ktra"][0]["Kết quả"]},
        }
        session.add(
            MigrationAnomaly(
                source_sheet=payload["source_sheet"],
                source_row_key=payload["source_row_key"],
                legacy_row_id=payload["legacy_row_id"],
                reason=payload["reason"],
                required_field=payload["required_field"],
                raw_fk_value=payload["raw_fk_value"],
                override_value=None,
                status=payload["status"],
                detail_json=json.dumps(payload, ensure_ascii=False),
            )
        )
        session.flush()
        return balanced_reconciliation()

    monkeypatch.setattr(ilp, "import_snapshot", fake_import_snapshot)

    report = ilp.execute_import(
        snapshot_path=snapshot_path,
        runtime_env_path=runtime_env,
        mode="dry-run",
        import_mode="validation",
        report_root=tmp_path / "reports",
    )

    assert report.validation_status == "pass"
    assert report.validation_isolation == "clean_temporary_database"
    assert report.cleanup_status == "ok"
    assert query_scalar(prod_db_path, "SELECT COUNT(*) FROM migration_anomaly") == 1
    assert query_scalar(prod_db_path, "SELECT detail_json FROM migration_anomaly") == detail_v1
    assert query_scalar(prod_db_path, "SELECT COUNT(*) FROM company WHERE legacy_company_id = 999") == 1
    assert not validation_db_path(database_url, report.target_database).exists()
    monkeypatch.setattr(ilp, "import_snapshot", original_import_snapshot)


def test_validation_uses_executable_url_and_redacts_reports(tmp_path: Path, monkeypatch) -> None:
    password = "p@ss:/%# word"
    runtime_env = write_runtime_env(tmp_path / "runtime.env", password=password)
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    database_url = postgres_database_url(password=password)
    patch_runtime(monkeypatch, database_url, runtime_env)
    captured_urls: list[str] = []

    monkeypatch.setattr(ilp, "_recreate_target_database", lambda *args, **kwargs: None)
    monkeypatch.setattr(ilp, "_drop_target_database", lambda *args, **kwargs: None)
    monkeypatch.setattr(ilp, "_upgrade_target_database_schema", lambda url: captured_urls.append(url))

    def fake_run_import(*, database_url: str, snapshot, dry_run: bool, require_head_revision: bool):
        captured_urls.append(database_url)
        head = expected_alembic_head_revision()
        return balanced_reconciliation(), head, head

    monkeypatch.setattr(ilp, "_run_import", fake_run_import)

    report = ilp.execute_import(
        snapshot_path=snapshot_path,
        runtime_env_path=runtime_env,
        mode="dry-run",
        import_mode="validation",
        report_root=tmp_path / "reports",
    )

    assert report.validation_status == "pass"
    assert report.database_url_redacted == ilp._redact_database_url(captured_urls[-1])
    assert password not in report.database_url_redacted
    assert ":***@" in report.database_url_redacted
    assert len(captured_urls) == 2
    for captured_url in captured_urls:
        parsed = make_url(captured_url)
        assert parsed.password == password
        assert parsed.database == report.target_database
        assert "***" not in captured_url

    report_dir = Path(report.report_dir)
    report_json = (report_dir / "report.json").read_text(encoding="utf-8")
    report_md = (report_dir / "report.md").read_text(encoding="utf-8")
    assert password not in report_json
    assert password not in report_md
    assert report.database_url_redacted in report_json
    assert report.database_url_redacted in report_md


def test_apply_modes_use_executable_target_urls_without_secret_leaks(tmp_path: Path, monkeypatch) -> None:
    password = "p@ss:/%# word"
    runtime_env = write_runtime_env(tmp_path / "runtime.env", password=password)
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    database_url = postgres_database_url(password=password)
    patch_runtime(monkeypatch, database_url, runtime_env)

    mode_targets = {
        "rehearsal": ilp.DEFAULT_REHEARSAL_TARGET_DB,
        "final": ilp.DEFAULT_FINAL_TARGET_DB,
    }
    captured_by_mode: dict[str, list[str]] = {}
    backup_calls: list[str] = []

    monkeypatch.setattr(ilp, "_recreate_target_database", lambda *args, **kwargs: None)

    def fake_upgrade(database_url: str) -> None:
        captured_by_mode.setdefault(current_mode[0], []).append(database_url)

    def fake_run_import(*, database_url: str, snapshot, dry_run: bool, require_head_revision: bool):
        captured_by_mode.setdefault(current_mode[0], []).append(database_url)
        head = expected_alembic_head_revision()
        return balanced_reconciliation(), head, head

    monkeypatch.setattr(ilp, "_upgrade_target_database_schema", fake_upgrade)
    monkeypatch.setattr(ilp, "_run_import", fake_run_import)
    monkeypatch.setattr(ilp, "_run_backup", lambda runtime_env_path: backup_calls.append(str(runtime_env_path)))

    for import_mode, expected_target in mode_targets.items():
        current_mode = [import_mode]
        report = ilp.execute_import(
            snapshot_path=snapshot_path,
            runtime_env_path=runtime_env,
            mode="apply",
            import_mode=import_mode,
            reset_from_snapshot=True,
            report_root=tmp_path / "reports",
        )
        assert report.target_database == expected_target
        assert password not in report.database_url_redacted
        assert ":***@" in report.database_url_redacted
        for captured_url in captured_by_mode[import_mode]:
            parsed = make_url(captured_url)
            assert parsed.password == password
            assert parsed.database == expected_target
            assert "***" not in captured_url
        report_dir = Path(report.report_dir)
        assert password not in (report_dir / "report.json").read_text(encoding="utf-8")
        assert password not in (report_dir / "report.md").read_text(encoding="utf-8")

    assert backup_calls == [str(runtime_env)]


def test_validation_drops_temporary_database_when_importer_fails(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    prod_db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(prod_db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)
    monkeypatch.setattr(ilp, "import_snapshot", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    try:
        ilp.execute_import(
            snapshot_path=snapshot_path,
            runtime_env_path=runtime_env,
            mode="dry-run",
            import_mode="validation",
            report_root=tmp_path / "reports",
        )
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("Expected importer failure")

    report_dirs = sorted((tmp_path / "reports").iterdir())
    report = json.loads((report_dirs[-1] / "report.json").read_text(encoding="utf-8"))
    assert report["cleanup_status"] == "ok"
    assert not validation_db_path(database_url, report["target_database"]).exists()


def test_validation_drops_temporary_database_when_reconciliation_fails(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    prod_db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(prod_db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)

    def unresolved_import(*args, **kwargs):
        payload = balanced_reconciliation()
        payload["source_balance"] = {
            "db.cty": {"source_count": 1, "imported_count": 1, "skipped_count": 0, "intentionally_skipped_count": 0, "unresolved_count": 0, "balanced": True},
            "db.cso": {"source_count": 1, "imported_count": 1, "skipped_count": 0, "intentionally_skipped_count": 0, "unresolved_count": 0, "balanced": True},
            "db.ktra": {"source_count": 3, "imported_count": 0, "skipped_count": 3, "intentionally_skipped_count": 0, "unresolved_count": 3, "balanced": True},
            "db.cc": {"source_count": 0, "imported_count": 0, "skipped_count": 0, "intentionally_skipped_count": 0, "unresolved_count": 0, "balanced": True},
            "db.dkkd": {"source_count": 0, "imported_count": 0, "skipped_count": 0, "intentionally_skipped_count": 0, "unresolved_count": 0, "balanced": True},
            "db.Tdoi": {"source_count": 0, "imported_count": 0, "skipped_count": 0, "intentionally_skipped_count": 0, "unresolved_count": 0, "balanced": True},
            "db.Tdoi2": {"source_count": 0, "imported_count": 0, "skipped_count": 0, "intentionally_skipped_count": 0, "unresolved_count": 0, "balanced": True},
        }
        payload["skipped_rows"] = {"db.ktra": 3}
        payload["excluded_rows"] = {}
        payload["inserted_counts"] = {"company": 1, "site": 1}
        payload["existing_counts"] = {"company": 0}
        payload["schema_length_violations"] = []
        payload["anomaly_rows"] = [
            {
                "source_sheet": "db.ktra",
                "source_row_key": "row:10",
                "legacy_row_id": None,
                "reason": "missing_site_fk",
                "required_field": "ID Cơ Sở",
                "raw_fk_value": "999",
                "status": "open",
            },
            {
                "source_sheet": "db.ktra",
                "source_row_key": "row:11",
                "legacy_row_id": None,
                "reason": "missing_site_fk",
                "required_field": "ID Cơ Sở",
                "raw_fk_value": "999",
                "status": "open",
            },
            {
                "source_sheet": "db.ktra",
                "source_row_key": "100",
                "legacy_row_id": "100",
                "reason": "missing_company_fk",
                "required_field": "ID CTY",
                "raw_fk_value": "888",
                "status": "open",
            },
        ]
        return payload

    monkeypatch.setattr(ilp, "import_snapshot", unresolved_import)

    try:
        ilp.execute_import(
            snapshot_path=snapshot_path,
            runtime_env_path=runtime_env,
            mode="dry-run",
            import_mode="validation",
            report_root=tmp_path / "reports",
        )
    except ilp.ProductionImportError as exc:
        assert "unresolved anomalies" in str(exc)
        assert Path(exc.report_json_path).name == "report.json"
    else:
        raise AssertionError("Expected reconciliation failure")

    report_dirs = sorted((tmp_path / "reports").iterdir())
    report = json.loads((report_dirs[-1] / "report.json").read_text(encoding="utf-8"))
    report_md = (report_dirs[-1] / "report.md").read_text(encoding="utf-8")
    assert report["validation_status"] == "failed"
    assert report["cleanup_status"] == "ok"
    assert report["reconciliation"]["anomaly_rows"] == unresolved_import()["anomaly_rows"]
    assert report["reconciliation"]["source_balance"]["db.ktra"]["unresolved_count"] == 3
    assert report["reconciliation"]["skipped_rows"] == {"db.ktra": 3}
    assert report["reconciliation"]["excluded_rows"] == {}
    assert report["reconciliation"]["inserted_counts"] == {"company": 1, "site": 1}
    assert report["reconciliation"]["existing_counts"] == {"company": 0}
    assert report["reconciliation"]["schema_length_violations"] == []
    assert report["reconciliation"]["unresolved_anomaly_count"] == 3
    assert report["reconciliation"]["unresolved_anomalies_by_sheet"] == {"db.ktra": 3}
    assert report["reconciliation"]["unresolved_anomalies_by_reason"] == {
        "missing_company_fk": 1,
        "missing_site_fk": 2,
    }
    assert report["reconciliation"]["unresolved_anomalies_by_required_field"] == {
        "ID CTY": 1,
        "ID Cơ Sở": 2,
    }
    assert report["reconciliation"]["unresolved_anomaly_groups"] == [
        {
            "source_sheet": "db.ktra",
            "reason": "missing_site_fk",
            "required_field": "ID Cơ Sở",
            "count": 2,
            "sample_source_row_keys": ["row:10", "row:11"],
        },
        {
            "source_sheet": "db.ktra",
            "reason": "missing_company_fk",
            "required_field": "ID CTY",
            "count": 1,
            "sample_source_row_keys": ["100"],
        },
    ]
    assert "## Unresolved Anomalies" in report_md
    assert "| `db.ktra` | `missing_site_fk` | `ID Cơ Sở` | 2 | `row:10`, `row:11` |" in report_md
    assert "| `db.ktra` | `missing_company_fk` | `ID CTY` | 1 | `100` |" in report_md
    assert not validation_db_path(database_url, report["target_database"]).exists()
    assert count_rows(prod_db_path, "company") == 0


def test_validation_cleanup_failure_reports_orphan_without_masking_primary_error(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    prod_db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(prod_db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)
    monkeypatch.setattr(ilp, "import_snapshot", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("primary boom")))
    monkeypatch.setattr(ilp, "_drop_target_database", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("cleanup boom")))

    try:
        ilp.execute_import(
            snapshot_path=snapshot_path,
            runtime_env_path=runtime_env,
            mode="dry-run",
            import_mode="validation",
            report_root=tmp_path / "reports",
        )
    except RuntimeError as exc:
        assert "primary boom" in str(exc)
        assert "cleanup boom" in str(exc)
    else:
        raise AssertionError("Expected combined failure")

    report_dirs = sorted((tmp_path / "reports").iterdir())
    report = json.loads((report_dirs[-1] / "report.json").read_text(encoding="utf-8"))
    assert report["cleanup_status"].startswith("failed:")
    assert "primary boom" in report["error_message"]
    assert "cleanup boom" in report["error_message"]


def test_validation_wraps_alembic_auth_failure_without_url_leak(tmp_path: Path, monkeypatch) -> None:
    password = "top-secret"
    runtime_env = write_runtime_env(tmp_path / "runtime.env", password=password)
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    database_url = postgres_database_url(password=password)
    patch_runtime(monkeypatch, database_url, runtime_env)
    monkeypatch.setattr(ilp, "_recreate_target_database", lambda *args, **kwargs: None)
    monkeypatch.setattr(ilp, "_drop_target_database", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        ilp,
        "_upgrade_target_database_schema",
        lambda database_url: (_ for _ in ()).throw(
            ilp.ProductionImportError(
                "Traceback...\n"
                "sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed\n"
                'FATAL: password authentication failed for user "gxp_app"'
            )
        ),
    )

    try:
        ilp.execute_import(
            snapshot_path=snapshot_path,
            runtime_env_path=runtime_env,
            mode="dry-run",
            import_mode="validation",
            report_root=tmp_path / "reports",
        )
    except ilp.ProductionImportError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected schema migration failure")

    assert message == "Temporary validation schema migration failed: PostgreSQL authentication failed"
    assert password not in message
    assert "***" not in message


def test_rehearsal_reset_import_rebuilds_target_and_same_snapshot_rerun_is_stable(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    prod_db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(prod_db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)

    first = rehearsal_apply(snapshot_path=snapshot_path, runtime_env_path=runtime_env, report_root=tmp_path / "reports")
    second = rehearsal_apply(snapshot_path=snapshot_path, runtime_env_path=runtime_env, report_root=tmp_path / "reports")

    rehearsal_db_path = tmp_path / f"{ilp.DEFAULT_REHEARSAL_TARGET_DB}.db"
    assert count_rows(prod_db_path, "company") == 0
    assert count_rows(rehearsal_db_path, "company") == 1
    assert count_rows(rehearsal_db_path, "site") == 1
    assert count_rows(rehearsal_db_path, "case") == 1
    assert count_rows(rehearsal_db_path, "legacy_id_map") >= 6
    assert first.import_mode == "rehearsal"
    assert first.snapshot_exported_at == "2026-08-24T00:00:00Z"
    assert first.source_workbook_identity == "Danh sách Kiểm tra GPs.xlsb"
    assert first.target_database == ilp.DEFAULT_REHEARSAL_TARGET_DB
    assert first.reconciliation["inserted_counts"]["company"] == 1
    assert second.reconciliation["inserted_counts"]["company"] == 1
    assert all(row["balanced"] for row in second.reconciliation["source_balance"].values())
    assert query_scalar(rehearsal_db_path, "SELECT legal_name FROM company WHERE legacy_company_id = 1") == "Company A"


def test_rehearsal_refresh_from_newer_snapshot_rebuilds_clean_target(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    v1_snapshot = merge_snapshot_sets(
        legacy_row_set(
            company_id="1",
            company_name="Company Alpha",
            site_id="10",
            site_name="Site Alpha",
            inspection_id="100",
            certificate_id="200",
            business_id="300",
            change_request_id="400",
            change_detail_id="500",
        ),
        legacy_row_set(
            company_id="2",
            company_name="Company Beta",
            site_id="20",
            site_name="Site Beta",
            inspection_id="101",
            certificate_id="201",
            business_id="301",
            change_request_id="401",
            change_detail_id="501",
        ),
    )
    v2_snapshot = merge_snapshot_sets(
        legacy_row_set(
            company_id="2",
            company_name="Company Beta Updated",
            site_id="20",
            site_name="Site Beta",
            inspection_id="101",
            certificate_id="201",
            business_id="301",
            change_request_id="401",
            change_detail_id="501",
            company_site_link_id="3",
        ),
        legacy_row_set(
            company_id="3",
            company_name="Company Gamma",
            site_id="30",
            site_name="Site Gamma",
            inspection_id="102",
            certificate_id="202",
            business_id="302",
            change_request_id="402",
            change_detail_id="502",
        ),
    )
    v1_path = write_snapshot(tmp_path / "legacy_snapshot_v1.json", snapshot_wrapper(v1_snapshot, exported_at="2026-08-24T08:00:00Z"))
    v2_path = write_snapshot(tmp_path / "legacy_snapshot_v2.json", snapshot_wrapper(v2_snapshot, exported_at="2026-08-24T09:00:00Z"))
    prod_db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(prod_db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)

    rehearsal_apply(snapshot_path=v1_path, runtime_env_path=runtime_env, report_root=tmp_path / "reports")
    second = rehearsal_apply(snapshot_path=v2_path, runtime_env_path=runtime_env, report_root=tmp_path / "reports")

    rehearsal_db_path = tmp_path / f"{ilp.DEFAULT_REHEARSAL_TARGET_DB}.db"
    assert count_rows(rehearsal_db_path, "company") == 2
    assert count_rows(rehearsal_db_path, "site") == 2
    assert count_rows(rehearsal_db_path, "case") == 2
    assert query_scalar(rehearsal_db_path, "SELECT COUNT(*) FROM company WHERE legacy_company_id = 1") == 0
    assert query_scalar(rehearsal_db_path, "SELECT legal_name FROM company WHERE legacy_company_id = 2") == "Company Beta Updated"
    assert query_scalar(
        rehearsal_db_path,
        """
        SELECT company.legacy_company_id
        FROM site
        JOIN company ON company.id = site.company_id
        WHERE site.legacy_site_id = ?
        """,
        (20,),
    ) == 3
    assert query_scalar(rehearsal_db_path, "SELECT COUNT(*) FROM site WHERE legacy_site_id = 10") == 0
    assert query_scalar(rehearsal_db_path, "SELECT COUNT(*) FROM site WHERE legacy_site_id = 30") == 1
    assert second.snapshot_exported_at == "2026-08-24T09:00:00Z"


def test_rehearsal_reset_import_rolls_back_on_injected_failure(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    prod_db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(prod_db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)

    original_import_snapshot = ilp.import_snapshot

    def exploding_import_snapshot(*args, **kwargs):
        original_import_snapshot(*args, **kwargs)
        raise RuntimeError("boom")

    monkeypatch.setattr(ilp, "import_snapshot", exploding_import_snapshot)
    try:
        rehearsal_apply(snapshot_path=snapshot_path, runtime_env_path=runtime_env, report_root=tmp_path / "reports")
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("Expected injected failure")

    rehearsal_db_path = tmp_path / f"{ilp.DEFAULT_REHEARSAL_TARGET_DB}.db"
    assert count_rows(prod_db_path, "company") == 0
    assert count_rows(rehearsal_db_path, "company") == 0
    assert count_rows(rehearsal_db_path, "legacy_id_map") == 0


def test_duplicate_legacy_key_fails_closed(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot = sample_snapshot()
    snapshot["db.cty"].append({"ID": "1", "TÊN CÔNG TY": "Company B"})
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(snapshot))
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)

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
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(snapshot))
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)

    try:
        ilp.execute_import(snapshot_path=snapshot_path, runtime_env_path=runtime_env, mode="dry-run", report_root=tmp_path / "reports")
    except ilp.ProductionImportError as exc:
        assert "unresolved anomalies" in str(exc)
    else:
        raise AssertionError("Expected unresolved anomaly failure")


def test_validation_isolation_rebuild_keeps_confirmed_blanked_rows_excluded(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot = sample_snapshot()
    snapshot["db.ktra"][0]["ID CƠ SỞ"] = ""
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(snapshot))
    prod_db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(prod_db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)

    confirmed_blanked_path = tmp_path / "confirmed_blanked_rows.json"
    confirmed_blanked_path.write_text(
        json.dumps(
            {
                "rows": [
                    {"source_sheet": "db.ktra", "source_row_key": "100"},
                    {"source_sheet": "db.cc", "source_row_key": "200"},
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ilp, "ROOT", Path.cwd())
    from backend.app.domain import phase2_import as phase2_import_module
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", confirmed_blanked_path)

    report = ilp.execute_import(
        snapshot_path=snapshot_path,
        runtime_env_path=runtime_env,
        mode="dry-run",
        import_mode="validation",
        report_root=tmp_path / "reports",
    )

    assert report.validation_status == "pass"
    assert report.reconciliation["unresolved_anomaly_count"] == 0
    assert report.reconciliation["excluded_rows"] == {"db.ktra": 1, "db.cc": 1}
    assert report.reconciliation["source_balance"]["db.ktra"]["unresolved_count"] == 0


def test_apply_rejects_target_database_matching_production_db(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)

    try:
        ilp.execute_import(
            snapshot_path=snapshot_path,
            runtime_env_path=runtime_env,
            mode="apply",
            import_mode="rehearsal",
            target_database_name="gxp_qlcl",
            reset_from_snapshot=True,
            report_root=tmp_path / "reports",
        )
    except ilp.ProductionImportError as exc:
        assert "must not match the canonical production database name" in str(exc)
    else:
        raise AssertionError("Expected target database guard failure")


def test_validation_ignores_canonical_production_alembic_revision_and_upgrades_clean_temporary_database(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    prod_db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(prod_db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)

    engine = create_engine(database_url, future=True)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM alembic_version"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('wrong-revision')"))

    report = ilp.execute_import(
        snapshot_path=snapshot_path,
        runtime_env_path=runtime_env,
        mode="dry-run",
        report_root=tmp_path / "reports",
    )

    assert report.validation_status == "pass"
    assert report.validation_isolation == "clean_temporary_database"
    assert report.cleanup_status == "ok"
    assert query_scalar(prod_db_path, "SELECT version_num FROM alembic_version") == "wrong-revision"
    assert not validation_db_path(database_url, report.target_database).exists()


def test_final_backup_failure_blocks_apply_before_mutation(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)
    monkeypatch.setattr(ilp, "_run_backup", lambda runtime_env_path: (_ for _ in ()).throw(ilp.ProductionImportError("backup failed")))

    try:
        final_apply(snapshot_path=snapshot_path, runtime_env_path=runtime_env, report_root=tmp_path / "reports")
    except ilp.ProductionImportError as exc:
        assert "backup failed" in str(exc)
    else:
        raise AssertionError("Expected backup gate failure")

    assert count_rows(db_path, "company") == 0
    assert not (tmp_path / f"{ilp.DEFAULT_FINAL_TARGET_DB}.db").exists()


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
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)
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
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    prod_db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(prod_db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)
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
            "--import-mode",
            "rehearsal",
            "--reset-from-snapshot",
            "--report-root",
            str(tmp_path / "reports"),
        ]
    )

    assert dry_run_code == 3
    assert apply_code == 0
    assert count_rows(prod_db_path, "company") == 0
    assert count_rows(tmp_path / f"{ilp.DEFAULT_REHEARSAL_TARGET_DB}.db", "company") == 1


def test_dry_run_with_missing_phase7_artifacts_creates_report_without_traceback(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)
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
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(snapshot))
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)
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
    assert "See report:" in stderr.getvalue()


def test_main_reports_schema_length_preflight_failures_without_raw_db_traceback(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot = sample_snapshot()
    snapshot["db.ktra"][0]["Mã hồ sơ"] = "D" * 129
    snapshot["db.Tdoi2"][0]["PHÂN LOẠI"] = "P" * 260
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(snapshot))
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)
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

    assert code == 1
    assert "StringDataRightTruncation" not in combined
    assert "Schema length preflight failed" in combined
    assert count_rows(db_path, "company") == 0
    assert report["validation_status"] == "failed"
    assert {row["target"] for row in report["reconciliation"]["schema_length_violations"]} == {
        "case_application.dossier_code",
        "change_request_detail.classification_label",
    }


def test_cli_enforces_validation_vs_rebuild_mode_contracts(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        apply_without_mode_code = ilp.main(
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
    assert apply_without_mode_code == 1
    assert "--apply requires --import-mode rehearsal or --import-mode final." in stderr.getvalue()

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        invalid_dry_run_code = ilp.main(
            [
                "--snapshot",
                str(snapshot_path),
                "--runtime-env",
                str(runtime_env),
                "--dry-run",
                "--import-mode",
                "rehearsal",
                "--report-root",
                str(tmp_path / "reports"),
            ]
        )
    assert invalid_dry_run_code == 1
    assert "Dry-run currently supports only --import-mode validation." in stderr.getvalue()


def test_final_apply_uses_candidate_default_and_records_backup_status(tmp_path: Path, monkeypatch) -> None:
    runtime_env = write_runtime_env(tmp_path / "runtime.env")
    snapshot_path = write_snapshot(tmp_path / "legacy_snapshot.json", snapshot_wrapper(sample_snapshot()))
    db_path = tmp_path / "prod.db"
    database_url = prepare_runtime_db(db_path)
    patch_runtime(monkeypatch, database_url, runtime_env)
    patch_target_schema_upgrade(monkeypatch)

    backup_calls: list[str] = []
    monkeypatch.setattr(ilp, "_run_backup", lambda runtime_env_path: backup_calls.append(str(runtime_env_path)))

    report = ilp.execute_import(
        snapshot_path=snapshot_path,
        runtime_env_path=runtime_env,
        mode="apply",
        import_mode="final",
        reset_from_snapshot=True,
        report_root=tmp_path / "reports",
    )

    candidate_db_path = tmp_path / f"{ilp.DEFAULT_FINAL_TARGET_DB}.db"
    assert report.import_mode == "final"
    assert report.target_database == ilp.DEFAULT_FINAL_TARGET_DB
    assert report.backup_status == "ok"
    assert backup_calls == [str(runtime_env)]
    assert count_rows(candidate_db_path, "company") == 1
