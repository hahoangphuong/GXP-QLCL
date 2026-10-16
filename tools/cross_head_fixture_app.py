"""Isolated CI-only FastAPI fixture for two-HEAD document API integration.

This module refuses to import the application or touch storage unless:
  - explicitly opted in by the cross-head workflow,
  - the DB is the disposable local gxp_qlcl_test Postgres instance,
  - and the JSON fixture path is supplied by the runner.

No production service, external NAS, or real user account is used.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

if os.environ.get("GXP_CROSS_HEAD_DISPOSABLE_GATE") != "1":
    raise RuntimeError("Cross-head fixture is only available in the explicit disposable CI gate.")

_database = os.environ.get("DATABASE_URL", "")
_parsed = make_url(_database) if _database else None
if (
    _parsed is None
    or _parsed.get_backend_name() != "postgresql"
    or _parsed.database != "gxp_qlcl_test"
    or _parsed.host not in {"127.0.0.1", "localhost"}
    or not _parsed.port == 5432
):
    raise RuntimeError("Cross-head fixture requires only local disposable gxp_qlcl_test PostgreSQL.")

_output = os.environ.get("GXP_CROSS_HEAD_FIXTURE_JSON", "")
if not _output or not Path(_output).is_absolute():
    raise RuntimeError("An absolute CI fixture JSON output path is required.")

from backend.app.db.enums import CaseState, DocumentVariantType
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate, BusinessEligibilityCertificateLink,
    BusinessEligibilityVersion, Case, Certificate, CertificateScope,
    CertificateVersion, Company, Document, DocumentVariant, DocumentVersion, Site,
)
from backend.app.main import create_app
from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig


_TEMP = tempfile.TemporaryDirectory(prefix="gxp-cross-head-only-")
root = Path(_TEMP.name) / "inspection"
root.mkdir()
storage = LocalStorageService(StorageConfig(inspection_root=root))
payload = b"GXP_CROSS_HEAD_SYNTHETIC_BINARY_V1"
relative_path = "ci-document/current.docx"
physical_path = root / relative_path
physical_path.parent.mkdir()
physical_path.write_bytes(payload)

fixture_ids = {key: str(uuid4()) for key in (
    "company", "site", "case", "other_case", "document", "variant",
    "version", "conflict_document", "conflict_variant",
    "missing_file_document", "missing_file_variant", "missing_file_version",
    "wrong_checksum_document", "wrong_checksum_variant", "wrong_checksum_version",
    "gxp_certificate", "gxp_version_old", "gxp_version_current",
    "gxp_scope_old", "gxp_scope_current", "ddk_certificate",
    "ddk_version_old", "ddk_version_current", "ddk_link_current",
    "gxp_document", "gxp_document_variant", "gxp_document_version",
    "ddk_document",
)}

engine = create_engine(_database, future=True)
try:
    with Session(engine) as session:
        session.add(Company(
            id=fixture_ids["company"], legal_name="Cross-head CI synthetic company",
        ))
        session.flush()
        session.add(Site(
            id=fixture_ids["site"], company_id=fixture_ids["company"],
            site_name="Cross-head CI synthetic site",
        ))
        session.flush()
        for key in ("case", "other_case"):
            session.add(Case(
                id=fixture_ids[key], site_id=fixture_ids["site"],
                gxp_type="GMP", state=CaseState.DRAFT,
            ))
        session.flush()
        session.add_all([
            Document(
                id=fixture_ids["document"], case_id=fixture_ids["case"],
                family_code="CROSS_HEAD_CI", document_type_code="TEST_DOC",
                title="Synthetic current document",
            ),
            Document(
                id=fixture_ids["conflict_document"], case_id=fixture_ids["case"],
                family_code="CROSS_HEAD_CI", document_type_code="TEST_DOC",
                title="Synthetic document missing current version",
            ),
            Document(
                id=fixture_ids["missing_file_document"], case_id=fixture_ids["case"],
                family_code="CROSS_HEAD_CI", document_type_code="TEST_DOC",
                title="Synthetic document whose registered binary was never stored",
            ),
            Document(
                id=fixture_ids["wrong_checksum_document"], case_id=fixture_ids["case"],
                family_code="CROSS_HEAD_CI", document_type_code="TEST_DOC",
                title="Synthetic document whose content checksum is incorrect",
            ),
        ])
        session.flush()
        session.add_all([
            DocumentVariant(
                id=fixture_ids["variant"], document_id=fixture_ids["document"],
                variant_type=DocumentVariantType.EDITABLE_DOCX,
            ),
            DocumentVariant(
                id=fixture_ids["conflict_variant"],
                document_id=fixture_ids["conflict_document"],
                variant_type=DocumentVariantType.EDITABLE_DOCX,
            ),
            DocumentVariant(
                id=fixture_ids["missing_file_variant"],
                document_id=fixture_ids["missing_file_document"],
                variant_type=DocumentVariantType.EDITABLE_DOCX,
            ),
            DocumentVariant(
                id=fixture_ids["wrong_checksum_variant"],
                document_id=fixture_ids["wrong_checksum_document"],
                variant_type=DocumentVariantType.EDITABLE_DOCX,
            ),
        ])
        session.flush()
        session.add_all([
            DocumentVersion(
                id=fixture_ids["version"],
                document_variant_id=fixture_ids["variant"], version_no=1,
                storage_root="inspection", storage_relative_path=relative_path,
                original_filename="synthetic-current.docx",
                checksum_sha256=sha256(payload).hexdigest(),
                is_current=True,
            ),
            DocumentVersion(
                id=fixture_ids["missing_file_version"],
                document_variant_id=fixture_ids["missing_file_variant"], version_no=1,
                storage_root="inspection",
                storage_relative_path="ci-document/missing-binary.docx",
                original_filename="missing-binary.docx",
                checksum_sha256=sha256(payload).hexdigest(),
                is_current=True,
            ),
            DocumentVersion(
                id=fixture_ids["wrong_checksum_version"],
                document_variant_id=fixture_ids["wrong_checksum_variant"], version_no=1,
                storage_root="inspection", storage_relative_path=relative_path,
                original_filename="wrong-checksum.docx",
                checksum_sha256=sha256(b"not-the-actual-file").hexdigest(),
                is_current=True,
            ),
        ])
        # Independently owned synthetic GxP / DDK historical snapshots.
        # These are fixture-only, not inferred Site coverage or legal grants.
        session.add(Certificate(
            id=fixture_ids["gxp_certificate"],
            site_id=fixture_ids["site"],
            case_id=fixture_ids["case"],
            certificate_type="GMP",
            issuance_basis="inspection_case",
            latest_flag=False,
        ))
        session.flush()
        session.add_all([
            CertificateVersion(
                id=fixture_ids["gxp_version_old"],
                certificate_id=fixture_ids["gxp_certificate"],
                version_no=1,
                certificate_number="SYNTH-GMP-OLD",
                issue_date=date(2023, 1, 15),
                lifecycle_state=None,
                is_latest_version=False,
            ),
            CertificateVersion(
                id=fixture_ids["gxp_version_current"],
                certificate_id=fixture_ids["gxp_certificate"],
                version_no=2,
                certificate_number="SYNTH-GMP-CURRENT",
                issue_date=date(2026, 1, 15),
                lifecycle_state=None,
                is_latest_version=True,
            ),
        ])
        session.flush()
        session.add_all([
            CertificateScope(
                id=fixture_ids["gxp_scope_old"],
                certificate_version_id=fixture_ids["gxp_version_old"],
                scope_key="old-scope", scope_text="Old synthetic scope only",
                language_code="en", sort_order=2,
            ),
            CertificateScope(
                id=fixture_ids["gxp_scope_current"],
                certificate_version_id=fixture_ids["gxp_version_current"],
                scope_key="current-scope", scope_text="Current synthetic scope only",
                language_code="en", sort_order=1,
            ),
        ])
        session.add(BusinessEligibilityCertificate(
            id=fixture_ids["ddk_certificate"],
            company_id=fixture_ids["company"],
            site_id=fixture_ids["site"],
            latest_flag=False,
        ))
        session.flush()
        session.add_all([
            BusinessEligibilityVersion(
                id=fixture_ids["ddk_version_old"],
                business_eligibility_certificate_id=fixture_ids["ddk_certificate"],
                version_no=1, certificate_number="SYNTH-DDK-OLD",
                issued_on=date(2020, 1, 15),
                issuance_history_text="Synthetic archival prose, not extra versions",
                business_activity_text="Historical storage",
            ),
            BusinessEligibilityVersion(
                id=fixture_ids["ddk_version_current"],
                business_eligibility_certificate_id=fixture_ids["ddk_certificate"],
                version_no=2, certificate_number="SYNTH-DDK-CURRENT",
                issued_on=date(2026, 1, 15),
                business_activity_text="Current manufacturing",
            ),
        ])
        session.flush()
        session.add(BusinessEligibilityCertificateLink(
            id=fixture_ids["ddk_link_current"],
            business_eligibility_version_id=fixture_ids["ddk_version_current"],
            certificate_id=fixture_ids["gxp_certificate"],
            link_role="source_certificate",
        ))
        # Canonical document metadata is registered under exact owner FKs;
        # these records do not assert binary presence or signed originals.
        session.add_all([
            Document(
                id=fixture_ids["gxp_document"],
                certificate_id=fixture_ids["gxp_certificate"],
                family_code="SYNTHETIC_GXP_METADATA",
                document_type_code="REGISTERED_ONLY",
                title="Synthetic unverified GxP metadata",
            ),
            Document(
                id=fixture_ids["ddk_document"],
                business_eligibility_certificate_id=fixture_ids["ddk_certificate"],
                family_code="SYNTHETIC_DDK_METADATA",
                document_type_code="REGISTERED_ONLY",
                title="Synthetic unverified DDK metadata",
            ),
        ])
        session.flush()
        session.add(DocumentVariant(
            id=fixture_ids["gxp_document_variant"],
            document_id=fixture_ids["gxp_document"],
            variant_type=DocumentVariantType.EDITABLE_DOCX,
        ))
        session.flush()
        session.add(DocumentVersion(
            id=fixture_ids["gxp_document_version"],
            document_variant_id=fixture_ids["gxp_document_variant"],
            version_no=1,
            original_filename="synthetic-no-binary.docx",
            is_current=True,
            storage_root=None,
            storage_relative_path=None,
        ))
        session.commit()
finally:
    engine.dispose()

fixture_ids["binary_text"] = payload.decode("ascii")
fixture_ids["binary_sha256"] = sha256(payload).hexdigest()
fixture_json = Path(_output)
fixture_json.write_text(json.dumps(fixture_ids), encoding="utf-8")
fixture_json.chmod(0o600)

app = create_app(
    _database,
    storage_service=storage,
    app_env={
        "APP_ENV": "development",
        "AUTH_MODE": "header_stub",
        "AUTH_DEFAULT_ROLE": "reader",
        "DATABASE_URL": _database,
        "DB_MODE": "local_postgres",
    },
)
