"""Rehearsal importer on *disposable* PostgreSQL; never connects to the VM.

The guard checks the CI service URL before creating a disposable database.
The test exercises actual PostgreSQL constraints, locks and UUID types,
not merely the SQLite unit-fixture simulation.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate, BusinessEligibilityCertificateLink,
    BusinessEligibilityVersion, Certificate, Company, Site,
)
from backend.app.services.catalog import CatalogReadService
from sqlalchemy.engine import make_url

from tools.apply_ddk_gxp_provenance_rehearsal import SourceLoadBlocked, apply_sealed_plan
from tools.plan_ddk_gxp_provenance_load import _digest, _source_value_digest


ROOT = Path(__file__).resolve().parents[1]
TARGET_DB = "gxp_legacy_rehearsal"


def _guard_ci():
    if os.environ.get("GXP_DDK_CI_POSTGRES_INTEGRATION") != "1":
        pytest.skip("Only guarded CI PostgreSQL service may run writer integration")
    assert os.environ.get("GITHUB_ACTIONS") == "true"
    admin_url = make_url(os.environ["DATABASE_URL"])
    assert admin_url.get_backend_name() == "postgresql"
    assert admin_url.host == "127.0.0.1" and admin_url.port == 5432
    assert admin_url.database == "gxp_qlcl_test"
    assert admin_url.username == "postgres" and admin_url.password == "postgres"
    return admin_url


def _plan():
    sha = "a" * 64
    roles = (("GMP", 15), ("GLP", 19), ("GSP", 23), ("GDP", 27))
    groups = []
    tokens = []
    for role, col in roles:
        values = ["200; 201", " Sterile\n", "WHO-GMP", "Manufacture"] if role == "GMP" else (
            ["", "", "", "Activity with no ID CC"] if role == "GDP"
            else ["", "", "", ""]
        )
        row = {
            "source_workbook_sha256": sha,
            "source_sheet_name": "db.dkkd",
            "source_row_number": 7,
            "legacy_dkkd_id": 400,
            "source_group": role,
            "id_cc_excel_column": col,
            "certificate_scope_excel_column": col + 1,
            "applicable_standard_excel_column": col + 2,
            "business_activity_excel_column": col + 3,
            "id_cc_raw": values[0],
            "certificate_scope_raw": values[1],
            "applicable_standard_raw": values[2],
            "business_activity_raw": values[3],
            "source_values_sha256": _source_value_digest(values),
        }
        key = {k: row[k] for k in (
            "source_workbook_sha256", "source_sheet_name",
            "source_row_number", "source_group",
        )}
        groups.append({"logical_source_key": key, "values": row})
        if role == "GMP":
            for index, cid in enumerate((200, 201), 1):
                tokens.append({
                    "source_group_key": key,
                    "values": {
                        "token_index": index,
                        "raw_token": str(cid),
                        "parsed_legacy_certificate_id": cid,
                    },
                })
    payload = {
        "group_table": "business_eligibility_gxp_source_group",
        "token_table": "business_eligibility_gxp_reference_evidence",
        "source_groups": groups,
        "reference_tokens": tokens,
    }
    return {
        "schema": "GXP_DDK_GXP_PROVENANCE_DRY_RUN_V1",
        "status": "DRY_RUN_ONLY_NOT_APPLIED",
        "source_workbook_sha256": sha,
        "source_baseline": {
            "ddk_rows": 1,
            "excluded_ddk_rows": 0,
            "reference_tokens": 2,
            "source_validation": "PARTIAL_INDEPENDENT_EXPORTS_ONLY",
            "excel_com_check": "WAIVED_BY_OWNER_NOT_PERFORMED",
        },
        "target": {
            "alembic_revision_required": "20261012_0023",
            "database_state": "NOT_CONNECTED_NOT_INSPECTED",
            "foreign_key_to_canonical_certificate": False,
            "canonical_link_changes": 0,
            "sql_writes_executed": 0,
            "uuid_allocation": "NOT_PERFORMED",
        },
        "counts": {
            "original_ddk_rows": 1,
            "excluded_ddk_rows": 0,
            "effective_ddk_rows": 1,
            "group_rows": 4,
            "field_positions": 16,
            "reference_tokens": 2,
            **{"groups_" + role: 1 for role, _ in roles},
        },
        "excluded_source_rows": [],
        "payload_sha256": _digest(payload),
        "payload": payload,
    }


def test_real_postgres_atomic_source_only_insert_retry_and_conflict():
    admin_url = _guard_ci()
    target_url = admin_url.set(database=TARGET_DB)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    created = False
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :database"),
                {"database": TARGET_DB},
            ).scalar()
            assert exists is None, "CI ephemeral rehearsal database already exists"
            conn.exec_driver_sql(f'CREATE DATABASE "{TARGET_DB}"')
            created = True

        env = dict(os.environ)
        env["DATABASE_URL"] = target_url.render_as_string(hide_password=False)
        env["DB_MODE"] = "local_postgres"
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20261012_0023"],
            env=env, cwd=ROOT, capture_output=True, text=True, timeout=180,
            check=False,
        )
        assert result.returncode == 0, (
            "Disposable PostgreSQL migration failed: " + result.stderr[-700:]
        )
        engine = create_engine(target_url)
        try:
            plan = _plan()
            loaded = apply_sealed_plan(engine, plan)
            assert loaded["status"] == "SOURCE_PROVENANCE_LOADED_AND_VERIFIED"
            assert loaded["inserted_groups"] == 4
            assert loaded["inserted_tokens"] == 2
            assert loaded["canonical_links_created"] == 0
            with engine.connect() as conn:
                assert conn.execute(text(
                    "SELECT count(*) FROM public.business_eligibility_gxp_source_group"
                )).scalar_one() == 4
                assert conn.execute(text(
                    "SELECT count(*) FROM public.business_eligibility_gxp_reference_evidence"
                )).scalar_one() == 2
                assert conn.execute(text(
                    "SELECT count(*) FROM public.business_eligibility_certificate_link"
                )).scalar_one() == 0
            # Real PostgreSQL read-model join: canonical DDK identity chooses
            # the original physical workbook row; ID CC remains source only.
            with Session(engine) as session:
                company = Company(legal_name="Disposable source-only org")
                session.add(company)
                session.flush()
                site = Site(company_id=company.id, site_name="Disposable source-only site")
                session.add(site)
                session.flush()
                canonical_ddk = BusinessEligibilityCertificate(
                    company_id=company.id, site_id=site.id, legacy_dkkd_id=400,
                )
                session.add(canonical_ddk)
                session.commit()
                evidence = CatalogReadService().get_business_eligibility_gxp_source_evidence(
                    session, business_eligibility_certificate_id=canonical_ddk.id,
                )
                assert evidence["source_status"] == "available"
                assert [g["source_group"] for g in evidence["groups"]] == ["GMP", "GLP", "GSP", "GDP"]
                assert evidence["groups"][0]["certificate_scope_raw"] == " Sterile\n"
                assert [t["token_index"] for t in evidence["groups"][0]["reference_tokens"]] == [1, 2]
                assert evidence["groups"][3]["business_activity_raw"] == "Activity with no ID CC"
                assert evidence["groups"][3]["reference_tokens"] == []
                assert evidence["canonical_links_included"] is False
                # Exercise historical ĐĐK records under actual PostgreSQL
                # schema/FKs; the raw source token evidence remains separate.
                old = BusinessEligibilityVersion(
                    business_eligibility_certificate_id=canonical_ddk.id,
                    version_no=1, certificate_number="OLD-DDK",
                    issuance_history_text="Historical free text is not two versions",
                )
                new = BusinessEligibilityVersion(
                    business_eligibility_certificate_id=canonical_ddk.id,
                    version_no=2, certificate_number="NEW-DDK",
                    business_activity_text="New DDK activity",
                )
                site_gmp = Certificate(site_id=site.id, certificate_type="GMP")
                session.add_all([old, new, site_gmp])
                session.flush()
                session.add(BusinessEligibilityCertificateLink(
                    business_eligibility_version_id=old.id,
                    certificate_id=site_gmp.id,
                    link_role="source_certificate",
                ))
                session.commit()
                history = CatalogReadService().get_business_eligibility_version_history(
                    session, business_eligibility_certificate_id=canonical_ddk.id,
                )
                assert history["latest_version_id"] == new.id
                assert [v["version_no"] for v in history["versions"]] == [2, 1]
                assert history["versions"][0]["stored_link_records"] == []
                assert history["versions"][0]["business_activity_text"] == "New DDK activity"
                assert history["versions"][1]["issuance_history_text"] == (
                    "Historical free text is not two versions"
                )
                assert len(history["versions"][1]["stored_link_records"]) == 1
                assert history["versions"][1]["stored_link_records"][0]["certificate_id"] == site_gmp.id
                assert history["gxp_source_tokens_included"] is False
                assert history["canonical_link_status"] == "stored_fk_only_not_validated"
                assert len(history["versions"]) == 2
            with engine.connect() as conn:
                # Canonical GxP link is an explicit test seed, not an importer result.
                assert conn.execute(text(
                    "SELECT count(*) FROM public.business_eligibility_certificate_link"
                )).scalar_one() == 1
                assert conn.execute(text(
                    "SELECT count(*) FROM public.business_eligibility_gxp_reference_evidence"
                )).scalar_one() == 2
            rerun = apply_sealed_plan(engine, plan)
            assert rerun["status"] == "SOURCE_PROVENANCE_ALREADY_MATCHES_PLAN"
            assert rerun["inserted_groups"] == rerun["inserted_tokens"] == 0

            # A *validly re-sealed* different source cannot overwrite data.
            different = copy.deepcopy(plan)
            row = different["payload"]["source_groups"][0]["values"]
            row["certificate_scope_raw"] = "Different source scope"
            row["source_values_sha256"] = _source_value_digest([
                row["id_cc_raw"], row["certificate_scope_raw"],
                row["applicable_standard_raw"], row["business_activity_raw"],
            ])
            different["payload_sha256"] = _digest(different["payload"])
            with pytest.raises(SourceLoadBlocked, match="Existing schema/source data conflict"):
                apply_sealed_plan(engine, different)
            with engine.connect() as conn:
                assert conn.execute(text(
                    "SELECT count(*) FROM public.business_eligibility_gxp_source_group"
                )).scalar_one() == 4
        finally:
            engine.dispose()
    finally:
        if created:
            with admin.connect() as conn:
                conn.exec_driver_sql(f'DROP DATABASE "{TARGET_DB}" WITH (FORCE)')
        admin.dispose()
