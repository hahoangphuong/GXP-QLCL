"""Rehearsal Case export must refuse non-rehearsal DSNs before connecting."""
import pytest

from tools.export_qdkt_case_cohort_readonly import (
    QdKtRehearsalExportBlocked, EXPECTED_DATABASE,
    require_rehearsal_url, main,
)


@pytest.mark.parametrize("dsn", [
    "sqlite:///gxp_legacy_rehearsal",
    "postgresql://user:password@localhost/gxp_qlcl",
    "postgresql://user:password@localhost/postgres",
    "",
    "malformed-not-a-url",
])
def test_no_non_rehearsal_database_accepted(dsn):
    with pytest.raises(QdKtRehearsalExportBlocked):
        require_rehearsal_url(dsn)


def test_exact_rehearsal_database_name_accepted():
    value = f"postgresql+psycopg://user:password@localhost/{EXPECTED_DATABASE}"
    assert require_rehearsal_url(value) == value


def test_export_with_missing_db_url_never_creates_output(monkeypatch, tmp_path):
    monkeypatch.delenv("QDKT_REHEARSAL_DATABASE_URL", raising=False)
    report = tmp_path / "cohort.json"
    with pytest.raises(SystemExit):
        main(["--output", str(report)])
    assert not report.exists()


def test_export_requires_explicit_env_identifier(tmp_path):
    with pytest.raises(SystemExit):
        main(["--database-url-env", "../secret", "--output", str(tmp_path / "out.json")])


def test_rehearsal_export_enforces_read_only_before_any_select(monkeypatch):
    from contextlib import nullcontext
    from tools import export_qdkt_case_cohort_readonly as owner

    actions = []

    class Connection:
        def begin(self):
            actions.append("begin")
            return nullcontext()

        def exec_driver_sql(self, statement):
            actions.append(statement)

        def execute(self, statement):
            actions.append("select")
            sql = str(statement).lower()
            assert "legacy_inspection_id" in sql
            assert "site_address" not in sql
            return [("case-one", 101), ("case-two", None)]

    class Engine:
        def connect(self):
            actions.append("connect")
            return nullcontext(Connection())

        def dispose(self):
            actions.append("dispose")

    monkeypatch.setattr(owner, "create_engine", lambda dsn, **kwargs: Engine())
    result = owner.read_case_cohort_readonly(
        database_url=f"postgresql+psycopg://reader:secret@localhost/{EXPECTED_DATABASE}",
    )
    assert result == [
        {"case_id": "case-one", "legacy_inspection_id": 101},
        {"case_id": "case-two", "legacy_inspection_id": None},
    ]
    assert actions == [
        "connect", "begin", "SET TRANSACTION READ ONLY", "select", "dispose",
    ]
