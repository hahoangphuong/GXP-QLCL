"""Isolated CI-only FastAPI fixture for two-HEAD document API integration.

This module refuses to import the application or touch storage unless:
  - explicitly opted in by the cross-head workflow,
  - the DB is the disposable local gxp_qlcl_test Postgres instance,
  - and the JSON fixture path is supplied by the runner.

No production service, external NAS, or real user account is used.
"""
from __future__ import annotations

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
    Case, Company, Document, DocumentVariant, DocumentVersion, Site,
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
