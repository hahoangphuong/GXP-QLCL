"""Source-only synthetic C.5e Case -> verified Word -> DocumentVersion integration.

No actual legacy/certificate binary, VM, NAS, OAuth or production DB.
Only the registered binary hashes and the generic scalar readiness plan are
substituted for fixture bytes; canonical DB scope, OOXML, workflow state,
local StorageService and output finalization execute through real owners.
"""
from __future__ import annotations

from hashlib import sha256
import os
from uuid import uuid4
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState, DocumentGenerationStatus
from backend.app.db.models.phase1 import (
    AuditEvent, Case, CaseEvaluationScope, CaseEvaluationScopeBlock,
    CaseEvaluationScopeSelection, Company, Document, DocumentGenerationRun,
    DocumentVersion, EvaluationScopeTaxonomyNode, EvaluationScopeTaxonomyVersion,
    Site, TemplateBinding, TemplateDefinition,
)
from backend.app.document import docx_template_render, template_binary
from backend.app.document import c5e_certificate_detail_source_asset_locator as source_locator_module
from backend.app.document import service as document_service_module
from backend.app.document.c5e_certificate_destination_asset_contract import (
    CertificateDestinationAsset, CertificateDestinationAssetContractError,
)
from backend.app.document.c5e_certificate_detail_source_asset_contract import (
    CertificateDetailSourceAsset,
)
from backend.app.document.c5e_certificate_detail_fragment_extractor import (
    extract_bookmark_table_fragment_from_docx_bytes,
)
from backend.app.document.template_binary_binding import assign_template_binary_binding
from tools.seed_c5e_certificate_template_metadata import (
    _load_registry_seed,
    _ensure_definition,
)
from backend.app.services import document_api as document_api_module
from backend.app.services.document_api import DocumentWorkflowService
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.types import StorageConfig


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _package(document: str, *, suffix: bool = False) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<Types/>')
        archive.writestr("word/document.xml", document.encode("utf-8"))
        if suffix:
            archive.writestr("word/test-retained.txt", b"RETAINED")
    return buffer.getvalue()


def _source_word() -> bytes:
    # Bookmark bounds are in different cells of the same table, as in the
    # audited source geometry; this exercises the *real* fragment extractor.
    return _package(f"""<w:document xmlns:w="{W}">
      <w:body><w:tbl>
        <w:tr>
          <w:tc><w:p>
            <w:bookmarkStart w:id="1" w:name="L1"/>
            <w:r><w:t>VI SOURCE</w:t></w:r>
          </w:p></w:tc>
          <w:tc><w:p/></w:tc>
          <w:tc><w:p>
            <w:r><w:t>EN SOURCE</w:t></w:r>
          </w:p></w:tc>
        </w:tr>
        <w:tr><w:tc><w:p><w:bookmarkEnd w:id="1"/></w:p></w:tc></w:tr>
      </w:tbl></w:body>
    </w:document>""")


def _destination_word() -> bytes:
    return _package(
        f"""<w:document xmlns:w="{W}"><w:body>
          <w:p>
            <w:bookmarkStart w:id="7" w:name="Pvi"/>
            <w:bookmarkEnd w:id="7"/>
            <w:r><w:t>STATIC SUFFIX</w:t></w:r>
          </w:p>
          <w:sectPr/>
        </w:body></w:document>""",
        suffix=True,
    )


def _seed_canonical_case(session: Session, gxp_type: str) -> str:
    company = Company(legacy_company_id=41001, legal_name="Synthetic C5e company")
    session.add(company)
    session.flush()
    site = Site(
        legacy_site_id=41002,
        company_id=company.id,
        site_name="Synthetic C5e site",
    )
    session.add(site)
    session.flush()
    case = Case(
        legacy_inspection_id=41003,
        legacy_inspection_code="CI-C5E-41003",
        site_id=site.id,
        gxp_type=gxp_type,
        state=CaseState.PLANNED,
        opened_year=2024,
    )
    session.add(case)
    session.flush()
    version = EvaluationScopeTaxonomyVersion(
        taxonomy_content_sha256="a" * 64,
        source_workbook_sha256="b" * 64,
        schema_version="evaluation-scope-taxonomy/v1",
    )
    session.add(version)
    session.flush()
    node = EvaluationScopeTaxonomyNode(
        taxonomy_version_id=version.id,
        gxp_type=gxp_type,
        source_name=f"PVCN_{gxp_type}",
        node_key="1",
        description="Synthetic scope",
        hint=None,
        main_topic="",
        short_render="",
        no_expand=None,
        source_order=1,
        source_excel_row=4,
    )
    session.add(node)
    session.flush()
    scope = CaseEvaluationScope(
        case_id=case.id,
        taxonomy_version_id=version.id,
        source_classification="STRUCTURED_VALID",
        raw_legacy_value="{1: synthetic}",
        rendered_prose="MUST NOT SELECT",
        limitation_text=None,
    )
    session.add(scope)
    session.flush()
    block = CaseEvaluationScopeBlock(
        case_evaluation_scope_id=scope.id,
        ordinal=1,
        name=None,
        note=None,
        raw_block_value="{1: synthetic}",
    )
    session.add(block)
    session.flush()
    session.add(CaseEvaluationScopeSelection(
        block_id=block.id,
        taxonomy_node_id=node.id,
        source_order=1,
        custom_description="",
        node_key_snapshot="WRONG_LEGACY_SNAPSHOT",
        taxonomy_description_snapshot="WRONG_LEGACY_DESCRIPTION",
    ))
    session.flush()
    return case.id


def _install_fixture_contracts(
    monkeypatch, session: Session, template_root: Path,
    gxp_type: str, destination: bytes, source: bytes,
) -> None:
    # C.5e deliberately owns its dedicated metadata seed. The generic
    # Phase-5 batch seed is not proof that exact GMP/GLP C.5e templates exist.
    _, definition_seed = _load_registry_seed()
    definition, definition_created = _ensure_definition(session, definition_seed)
    assert definition_created is True
    assert definition.family_code == "CERTIFICATE_ISSUANCE_WORD"
    binding = TemplateBinding(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        template_definition_id=definition.id,
        gxp_type=gxp_type,
        legacy_mode="moi",
        storage_scope="inspection_folder",
        is_active=True,
    )
    session.add(binding)
    session.flush()
    filename = f"9. Chung chi {gxp_type} (moi).dotx"
    path = f"c5e-synthetic/{filename}"
    destination_path = template_root / path
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(destination)
    dest_asset = CertificateDestinationAsset(
        gxp_type=gxp_type, filename=filename, storage_root="template",
        storage_relative_path=path, checksum_sha256=sha256(destination).hexdigest(),
    )
    assign_template_binary_binding(
        session, template_binding_id=binding.id, storage_root="template",
        storage_relative_path=path, original_filename=filename,
        checksum_sha256=dest_asset.checksum_sha256,
    )

    source_filename = f"9. Phamvi{gxp_type}.docx"
    source_path = template_root / "c5e_certificate_detail" / source_filename
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(source)
    source_asset = CertificateDetailSourceAsset(
        source_variant="certificate_9", gxp_type=gxp_type,
        filename=source_filename, sha256=sha256(source).hexdigest(),
    )

    def exact_destination(requested: str):
        if requested != gxp_type:
            raise CertificateDestinationAssetContractError(
                "Unsupported C.5e destination asset GxP"
            )
        return dest_asset

    def exact_source(*, source_variant: str, gxp_type: str, registry=None):
        assert source_variant == "certificate_9"
        assert gxp_type == source_asset.gxp_type
        return source_asset

    monkeypatch.setitem(
        template_binary._EXACT_GXP_ASSET_LOADERS,
        "CERTIFICATE_ISSUANCE_WORD",
        (exact_destination, CertificateDestinationAssetContractError),
    )
    monkeypatch.setattr(source_locator_module, "resolve_source_asset", exact_source)

    # The general scalar bookmark plan is *not* under test. Its binary
    # contract is still checked above; the genuine C.5e fragment pipeline
    # and persistence remain unmocked.
    plan = lambda *args, **kwargs: SimpleNamespace(
        mode="contract_exact", template_variant_key=gxp_type,
        bookmark_replacements={},
    )
    for module in (docx_template_render, document_api_module):
        monkeypatch.setattr(
            module, "load_default_template_contract_reconciliation",
            lambda: None,
        )
        monkeypatch.setattr(
            module, "build_scalar_replacement_plan_for_template", plan,
        )


@pytest.mark.parametrize("gxp_type", ("GMP", "GLP"))
def test_c5e_synthetic_case_to_current_document_version(
    tmp_path, monkeypatch, gxp_type,
):
    # The synthetic integration owns its tracked Phase-5 input artifact
    # root. Other tests/runtime deployments may override this setting;
    # do not let unrelated environments change this fixture's registry.
    tracked_artifacts_root = Path(__file__).resolve().parents[1] / "artifacts"
    assert (tracked_artifacts_root / "phase5" / "template_registry.curated.json").is_file()
    monkeypatch.setenv("GXP_ARTIFACTS_ROOT", str(tracked_artifacts_root))
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    roots = {
        "inspection_root": tmp_path / "inspection",
        "dkkd_root": tmp_path / "dkkd",
        "template_root": tmp_path / "templates",
    }
    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)
    storage = FilesystemStorageService(StorageConfig(**roots))
    source = _source_word()
    destination = _destination_word()
    fragment = extract_bookmark_table_fragment_from_docx_bytes(
        source, bookmark_name="L1"
    )
    assert "VI SOURCE" in fragment.visible_text
    assert "EN SOURCE" in fragment.visible_text
    workflow = DocumentWorkflowService()
    try:
        with Session(engine) as session:
            case_id = _seed_canonical_case(session, gxp_type)
            _install_fixture_contracts(
                monkeypatch, session, roots["template_root"],
                gxp_type, destination, source,
            )
            # Explicitly prove this is a Case-backed source, not the generic
            # request's untrusted imported summary/description snapshots.
            parent_folder = (
                roots["inspection_root"] / "2024" /
                "Synthetic C5e Folder - (ID-41002) - (CI-C5E-41003)"
            )
            parent_folder.mkdir(parents=True, exist_ok=True)
            session.commit()

            payload = {
                "family_code": "CERTIFICATE_ISSUANCE_WORD",
                "case_id": case_id,
                "gxp_type": gxp_type,
                "legacy_mode": "moi",
                "storage_scope": "inspection_folder",
                "language_code": "vi",
                "idempotency_key": f"synthetic-c5e-{gxp_type}",
                "output_filename": f"synthetic-{gxp_type}.docx",
                # At least one registry-owned scalar field is required by the
                # genuine family payload contract. Only generic bookmark
                # composition is stubbed; payload validation stays real.
                "payload": {"TenCoso": "Synthetic C5e site"},
                "strict_payload": True,
            }
            user = build_authenticated_user(
                "c5e-fixture-inspector", "inspector",
            )
            result = workflow.render_template_docx(
                session, storage=storage, payload=payload, user=user,
            )
            session.commit()
            assert result["generation_status"] == "succeeded"
            assert result["checksum_sha256"]

        with Session(engine) as session:
            document = session.get(Document, result["document_id"])
            version = session.get(DocumentVersion, result["document_version_id"])
            run = session.get(DocumentGenerationRun, result["generation_run_id"])
            assert document is not None
            assert document.case_id == case_id
            assert document.certificate_id is None
            assert document.capa_cycle_id is None
            assert document.business_eligibility_certificate_id is None
            assert document.change_request_id is None
            assert version is not None and version.is_current is True
            assert version.checksum_sha256 == result["checksum_sha256"]
            assert run is not None and run.status == DocumentGenerationStatus.SUCCEEDED
            assert run.output_document_version_id == version.id

            written = storage
            with written.read_stream(
                version.storage_relative_path, root=version.storage_root
            ) as stream:
                binary = stream.read()
            assert sha256(binary).hexdigest() == version.checksum_sha256
            with ZipFile(BytesIO(binary), "r") as archive:
                xml = archive.read("word/document.xml")
                assert archive.read("word/test-retained.txt") == b"RETAINED"
            doc_root = ET.fromstring(xml)
            texts = [
                node.text for node in doc_root.findall(f".//{{{W}}}t")
                if node.text
            ]
            joined = " ".join(texts)
            assert "VI SOURCE" in joined
            assert "EN SOURCE" in joined
            assert "STATIC SUFFIX" in joined
            assert "WRONG_LEGACY" not in joined
            assert not doc_root.findall(f".//{{{W}}}bookmarkStart[@{{{W}}}name='Pvi']")
    finally:
        engine.dispose()



@pytest.mark.parametrize("gxp_type", ("GMP", "GLP"))
@pytest.mark.parametrize("tampered_asset", ("destination", "source"))
def test_c5e_tampered_word_binary_never_finalizes_current_document_version(
    tmp_path, monkeypatch, gxp_type, tampered_asset,
):
    """Synthetic full workflow must leave no successful lineage or output."""
    tracked_artifacts_root = Path(__file__).resolve().parents[1] / "artifacts"
    monkeypatch.setenv("GXP_ARTIFACTS_ROOT", str(tracked_artifacts_root))
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    roots = {
        "inspection_root": tmp_path / "inspection",
        "dkkd_root": tmp_path / "dkkd",
        "template_root": tmp_path / "templates",
    }
    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)
    storage = FilesystemStorageService(StorageConfig(**roots))
    workflow = DocumentWorkflowService()
    try:
        with Session(engine) as session:
            case_id = _seed_canonical_case(session, gxp_type)
            _install_fixture_contracts(
                monkeypatch, session, roots["template_root"],
                gxp_type, _destination_word(), _source_word(),
            )
            parent_folder = (
                roots["inspection_root"] / "2024" /
                "Synthetic C5e Folder - (ID-41002) - (CI-C5E-41003)"
            )
            parent_folder.mkdir(parents=True, exist_ok=True)
            if tampered_asset == "destination":
                selected = (
                    roots["template_root"] / "c5e-synthetic" /
                    f"9. Chung chi {gxp_type} (moi).dotx"
                )
            else:
                selected = (
                    roots["template_root"] / "c5e_certificate_detail" /
                    f"9. Phamvi{gxp_type}.docx"
                )
            # The immutable registry and binding still hold SHA256 for the
            # original fixture bytes. Only the *stored* binary is tampered.
            selected.write_bytes(selected.read_bytes() + b"TAMPERED")
            session.commit()

            payload = {
                "family_code": "CERTIFICATE_ISSUANCE_WORD",
                "case_id": case_id,
                "gxp_type": gxp_type,
                "legacy_mode": "moi",
                "storage_scope": "inspection_folder",
                "language_code": "vi",
                "idempotency_key": (
                    f"synthetic-c5e-tampered-{tampered_asset}-{gxp_type}"
                ),
                "output_filename": f"tampered-{gxp_type}.docx",
                "payload": {"TenCoso": "Synthetic C5e site"},
                "strict_payload": True,
            }
            with pytest.raises(HTTPException) as exc:
                workflow.render_template_docx(
                    session,
                    storage=storage,
                    payload=payload,
                    user=build_authenticated_user(
                        "c5e-fixture-inspector", "inspector",
                    ),
                )
            assert exc.value.status_code == 409
            # Template readiness intentionally redacts checksum-specific
            # details from the public 409; post-allocation source checksum
            # errors retain their distinct C.5e runtime failure boundary.
            expected_failure = (
                "template:runtime_contract_failed"
                if tampered_asset == "destination"
                else "checksum mismatch"
            )
            assert expected_failure in str(exc.value.detail).lower()
            session.commit()

        with Session(engine) as session:
            runs = list(session.scalars(select(DocumentGenerationRun)))
            assert len(runs) == 1
            assert runs[0].status == DocumentGenerationStatus.FAILED
            assert expected_failure in (runs[0].error_summary or "").lower()
            documents = list(session.scalars(select(Document)))
            assert len(documents) == 1
            assert documents[0].case_id == case_id
            versions = list(session.scalars(select(DocumentVersion)))
            assert all(not version.is_current for version in versions)
            assert all(not version.checksum_sha256 for version in versions)
        assert list(roots["inspection_root"].rglob("*.docx")) == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("gxp_type", ("GMP", "GLP"))
@pytest.mark.parametrize("tampered_source", (False, True))
def test_c5e_case_to_document_version_postgres_transaction(
    tmp_path, monkeypatch, gxp_type, tampered_source,
):
    """Exercise the real C.5e workflow across a PostgreSQL commit boundary.

    Each scenario owns a disposable *schema* in the CI PostgreSQL database,
    not a live/rehearsal schema. Binary assets remain synthetic. A fresh
    session must observe committed Case/DocumentVersion/run/audit lineage.
    """
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        pytest.skip("requires isolated PostgreSQL schema for C.5e transaction integration")

    artifacts_root = Path(__file__).resolve().parents[1] / "artifacts"
    monkeypatch.setenv("GXP_ARTIFACTS_ROOT", str(artifacts_root))
    schema = "c5e_ci_" + uuid4().hex
    admin_engine = create_engine(database_url, future=True)
    engine = None
    schema_created = False
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        schema_created = True
        # Unqualified ORM tables and their FK targets resolve in this
        # test-private schema; never write into the CI database's public tables.
        engine = create_engine(
            database_url,
            # Do not include public: SQLAlchemy has_table() would see the
            # migrated public tables and create_all() would reuse them.
            connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == schema
            assert connection.scalar(text(
                "SELECT count(*) FROM pg_tables WHERE schemaname = :schema AND tablename = 'company'"
            ), {"schema": schema}) == 1
        roots = {
            "inspection_root": tmp_path / "inspection",
            "dkkd_root": tmp_path / "dkkd",
            "template_root": tmp_path / "templates",
        }
        for root in roots.values():
            root.mkdir(parents=True, exist_ok=True)
        storage = FilesystemStorageService(StorageConfig(**roots))
        workflow = DocumentWorkflowService()
        with Session(engine) as session:
            case_id = _seed_canonical_case(session, gxp_type)
            _install_fixture_contracts(
                monkeypatch, session, roots["template_root"], gxp_type,
                _destination_word(), _source_word(),
            )
            parent_folder = (
                roots["inspection_root"] / "2024" /
                "Synthetic C5e Folder - (ID-41002) - (CI-C5E-41003)"
            )
            parent_folder.mkdir(parents=True, exist_ok=True)
            if tampered_source:
                source_path = (
                    roots["template_root"] / "c5e_certificate_detail" /
                    f"9. Phamvi{gxp_type}.docx"
                )
                source_path.write_bytes(source_path.read_bytes() + b"TAMPERED")
            session.commit()

        payload = {
            "family_code": "CERTIFICATE_ISSUANCE_WORD",
            "case_id": case_id,
            "gxp_type": gxp_type,
            "legacy_mode": "moi",
            "storage_scope": "inspection_folder",
            "language_code": "vi",
            "idempotency_key": f"c5e-pg-{gxp_type}-{schema}",
            "output_filename": f"c5e-pg-{gxp_type}.docx",
            "payload": {"TenCoso": "Synthetic C5e site"},
            "strict_payload": True,
        }
        with Session(engine) as session:
            if tampered_source:
                with pytest.raises(HTTPException) as failure:
                    workflow.render_template_docx(
                        session, storage=storage, payload=payload,
                        user=build_authenticated_user("c5e-pg-inspector", "inspector"),
                    )
                assert failure.value.status_code == 409
                assert "checksum mismatch" in str(failure.value.detail).lower()
            else:
                result = workflow.render_template_docx(
                    session, storage=storage, payload=payload,
                    user=build_authenticated_user("c5e-pg-inspector", "inspector"),
                )
                assert result["generation_status"] == "succeeded"
            session.commit()

        # Post-commit verification uses a genuinely independent DB session.
        with Session(engine) as verify:
            documents = list(verify.scalars(select(Document)))
            versions = list(verify.scalars(select(DocumentVersion)))
            runs = list(verify.scalars(select(DocumentGenerationRun)))
            assert len(documents) == len(runs) == 1
            assert documents[0].family_code == "CERTIFICATE_ISSUANCE_WORD"
            assert documents[0].case_id == case_id
            assert documents[0].certificate_id is None
            assert documents[0].capa_cycle_id is None
            assert documents[0].change_request_id is None
            assert runs[0].document_id == documents[0].id
            if tampered_source:
                assert runs[0].status == DocumentGenerationStatus.FAILED
                assert all(not v.is_current and not v.checksum_sha256 for v in versions)
                assert not list(roots["inspection_root"].rglob("*.docx"))
            else:
                assert runs[0].status == DocumentGenerationStatus.SUCCEEDED
                assert len(versions) == 1
                version = versions[0]
                assert version.is_current is True
                assert version.id == runs[0].output_document_version_id
                assert version.checksum_sha256 == result["checksum_sha256"]
                audit = verify.get(AuditEvent, result["audit_event_id"])
                assert audit is not None
                assert audit.action == "document.render_template_docx"
                with storage.read_stream(
                    version.storage_relative_path, root=version.storage_root,
                ) as stream:
                    binary = stream.read()
                assert sha256(binary).hexdigest() == version.checksum_sha256
                with ZipFile(BytesIO(binary), "r") as archive:
                    xml = archive.read("word/document.xml")
                doc_root = ET.fromstring(xml)
                joined = " ".join(
                    node.text for node in doc_root.findall(f".//{{{W}}}t")
                    if node.text
                )
                assert "VI SOURCE" in joined
                assert "EN SOURCE" in joined
                assert "WRONG_LEGACY" not in joined
    finally:
        if engine is not None:
            engine.dispose()
        if schema_created:
            with admin_engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()
