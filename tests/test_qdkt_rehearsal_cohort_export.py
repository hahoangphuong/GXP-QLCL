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
