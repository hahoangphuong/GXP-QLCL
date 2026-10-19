"""Source-only synthetic C.5e Case -> verified Word -> DocumentVersion integration.

No actual legacy/certificate binary, VM, NAS, OAuth or production DB.
Only the registered binary hashes and the generic scalar readiness plan are
substituted for fixture bytes; canonical DB scope, OOXML, workflow state,
local StorageService and output finalization execute through real owners.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState, DocumentGenerationStatus
from backend.app.db.models.phase1 import (
    Case, CaseEvaluationScope, CaseEvaluationScopeBlock,
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
from backend.app.document.seed_runtime import seed_default_template_metadata
from backend.app.document.template_binary_binding import assign_template_binary_binding
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
    seed_default_template_metadata(session)
    definition = session.scalar(select(TemplateDefinition).where(
        TemplateDefinition.family_code == "CERTIFICATE_ISSUANCE_WORD"
    ))
    assert definition is not None
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
                "payload": {},
                "strict_payload": False,
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
