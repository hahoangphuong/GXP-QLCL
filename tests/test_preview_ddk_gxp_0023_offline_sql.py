"""Safety tests for exact 0022 -> 0023 Alembic SQL-only offline preview."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess
import sys

import pytest

from tools.audit_ddk_idcc_physical import MissingPhysicalEvidence
from tools.preview_ddk_gxp_0023_offline_sql import (
    BASE_REV, TARGET_REV, audit_offline_ddl,
    render_offline_ddl, main,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _sample_ddl():
    return """
BEGIN;
CREATE TABLE business_eligibility_gxp_source_group (
    id UUID NOT NULL, source_workbook_sha256 VARCHAR(64) NOT NULL,
    PRIMARY KEY (id)
);
CREATE INDEX ix_begxp_group_source_workbook
    ON business_eligibility_gxp_source_group (source_workbook_sha256);
CREATE TABLE business_eligibility_gxp_reference_evidence (
    id UUID NOT NULL, source_group_id UUID NOT NULL,
    PRIMARY KEY (id)
);
CREATE INDEX ix_business_eligibility_gxp_reference_evidence_source_group_id
    ON business_eligibility_gxp_reference_evidence (source_group_id);
UPDATE alembic_version SET version_num='20261012_0023'
WHERE alembic_version.version_num = '20261008_0022';
COMMIT;
"""


def test_expected_0023_ddl_is_bounded_to_two_empty_evidence_tables():
    actual = audit_offline_ddl(_sample_ddl())
    assert actual["status"] == "OFFLINE_DDL_PREVIEW_ONLY_NO_DB_IO"
    assert actual["from_revision"] == BASE_REV
    assert actual["to_revision"] == TARGET_REV
    assert len(actual["created_tables"]) == 2
    assert len(actual["created_indexes"]) == 2
    assert actual["sql_sha256"] == sha256(_sample_ddl().encode("utf-8")).hexdigest()


@pytest.mark.parametrize("tamper", [
    lambda s: s + "\nDELETE FROM certificate;",
    lambda s: s + "\nUPDATE business_eligibility_version SET version_no = 9;",
    lambda s: s + "\nDROP TABLE business_eligibility_certificate;",
    lambda s: s + "\nALTER TABLE certificate DROP COLUMN case_id;",
    lambda s: s + "\nINSERT INTO certificate(id) VALUES ('x');",
    lambda s: s.replace("CREATE TABLE business_eligibility_gxp_reference_evidence",
                        "CREATE TABLE certificate"),
    lambda s: s.replace("UPDATE alembic_version", "UPDATE public.site"),
    lambda s: s.replace("20261012_0023", "20261012_0024"),
    lambda s: s.replace("CREATE INDEX ix_begxp_group_source_workbook",
                        "CREATE INDEX ix_wrong_index"),
])
def test_offline_ddl_rejects_unapproved_mutations_or_revision_drift(tamper):
    with pytest.raises(MissingPhysicalEvidence):
        audit_offline_ddl(tamper(_sample_ddl()))


def test_offline_renderer_uses_real_migration_with_no_online_database():
    sql = render_offline_ddl(REPOSITORY_ROOT)
    result = audit_offline_ddl(sql)
    assert result["status"] == "OFFLINE_DDL_PREVIEW_ONLY_NO_DB_IO"
    assert "business_eligibility_gxp_source_group" in sql
    assert "business_eligibility_gxp_reference_evidence" in sql


def test_offline_cli_never_overwrites_previous_review(tmp_path, monkeypatch):
    out = tmp_path / "ddk_0023.sql"
    monkeypatch.setattr(sys, "argv", [
        "preview_ddk_gxp_0023_offline_sql", "--repo", str(REPOSITORY_ROOT),
        "--output", str(out),
    ])
    assert main() == 0
    first = out.read_bytes()
    assert first
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert out.read_bytes() == first


def test_render_fails_closed_if_migration_file_is_not_from_owner_repo(tmp_path):
    with pytest.raises(MissingPhysicalEvidence, match="Missing owner Alembic"):
        render_offline_ddl(tmp_path)
