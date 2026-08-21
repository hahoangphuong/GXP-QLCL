from __future__ import annotations

import json
import shutil
import sys
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.enums import CaseState
from backend.app.db.models import Base
from backend.app.db.models.phase1 import Case, Company, DocumentGenerationRun, DocumentVersion, Site, TemplateDefinition
from backend.app.db.session import build_engine
from backend.app.document.seed_runtime import seed_default_template_metadata
from backend.app.document.service import (
    DocumentPreparationInput,
    TableRegionRenderInput,
    render_template_aware_docx_generation,
)
from backend.app.document.service_contract import DocumentGenerationRequest
from backend.app.document.template_binary import assign_template_binary_locator
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.types import StorageConfig


def _build_table_region_template_bytes() -> bytes:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r><w:t>QDKT: </w:t></w:r>
      <w:bookmarkStart w:id="1" w:name="QDKT"/>
      <w:r><w:t>PLACEHOLDER_QDKT</w:t></w:r>
      <w:bookmarkEnd w:id="1"/>
    </w:p>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Muc</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Noi dung</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc>
          <w:p>
            <w:bookmarkStart w:id="10" w:name="DsTT_ROW"/>
            <w:bookmarkEnd w:id="10"/>
            <w:bookmarkStart w:id="11" w:name="Muc"/>
            <w:r><w:t>ROW_MUC</w:t></w:r>
            <w:bookmarkEnd w:id="11"/>
          </w:p>
        </w:tc>
        <w:tc>
          <w:p>
            <w:bookmarkStart w:id="12" w:name="Noidung"/>
            <w:r><w:t>ROW_NOIDUNG</w:t></w:r>
            <w:bookmarkEnd w:id="12"/>
          </w:p>
        </w:tc>
      </w:tr>
    </w:tbl>
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>"""
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>""",
        )
        archive.writestr("word/document.xml", document_xml)
        archive.writestr(
            "docProps/core.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Table Region Render Smoke</dc:title>
</cp:coreProperties>""",
        )
        archive.writestr(
            "docProps/app.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex GxP Table Region Smoke</Application>
</Properties>""",
        )
    return buffer.getvalue()


def seed_fixture(session, inspection_root: Path) -> dict[str, str]:
    company = Company(legacy_company_id=1, legal_name="Cong ty A")
    session.add(company)
    session.flush()
    site = Site(legacy_site_id=100, company_id=company.id, site_name="Co so A")
    session.add(site)
    session.flush()
    case = Case(
        legacy_inspection_id=200,
        legacy_inspection_code="KT-2024-GMP",
        site_id=site.id,
        gxp_type="GMP",
        state=CaseState.INSPECTION_COMPLETED,
        opened_year=2024,
    )
    session.add(case)
    session.flush()
    folder_path = inspection_root / "2024" / "Co so A (ID-100) (KT-2024-GMP)"
    folder_path.mkdir(parents=True, exist_ok=True)
    return {"case_id": case.id}


def main() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    smoke_root = ROOT / "artifacts" / "phase5" / "_smoke_table_region_render"
    if smoke_root.exists():
        shutil.rmtree(smoke_root)
    smoke_root.mkdir(parents=True, exist_ok=True)
    try:
        inspection_root = smoke_root / "inspection"
        template_root = smoke_root / "templates"
        inspection_root.mkdir(parents=True, exist_ok=True)
        template_root.mkdir(parents=True, exist_ok=True)
        template_path = template_root / "inspection" / "2. QD KT - GMP.docx"
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_bytes(_build_table_region_template_bytes())
        storage = FilesystemStorageService(
            StorageConfig(
                inspection_root=inspection_root,
                template_root=template_root,
            )
        )

        with session_factory() as session:
            seed_default_template_metadata(session)
            fixture = seed_fixture(session, inspection_root)
            template_definition = session.execute(
                select(TemplateDefinition).where(TemplateDefinition.family_code == "INSPECTION_QD_KT")
            ).scalar_one()
            assign_template_binary_locator(
                session,
                template_definition_id=template_definition.id,
                storage_root="template",
                storage_relative_path="inspection/2. QD KT - GMP.docx",
                original_filename="2. QD KT - GMP.docx",
            )
            result = render_template_aware_docx_generation(
                session,
                storage,
                DocumentPreparationInput(
                    request=DocumentGenerationRequest(
                        family_code="INSPECTION_QD_KT",
                        requested_by_user_id=None,
                        case_id=fixture["case_id"],
                        gxp_type="GP",
                        storage_scope="inspection_folder",
                        idempotency_key="smoke-phase5-table-region-render",
                    ),
                    payload_values={
                        "QDKT": "12/QD",
                    },
                    table_regions=(
                        TableRegionRenderInput(
                            region_bookmark_name="DsTT_ROW",
                            rows=(
                                {"Muc": "1", "Noidung": "Noi dung 1"},
                                {"Muc": "2", "Noidung": "Noi dung 2"},
                            ),
                        ),
                    ),
                ),
                output_filename="2. QD KT - GMP.docx",
            )
            document_version = session.execute(
                select(DocumentVersion).where(DocumentVersion.id == result.document_version_id)
            ).scalar_one()
            generation_run = session.execute(
                select(DocumentGenerationRun).where(DocumentGenerationRun.id == result.generation_run_id)
            ).scalar_one()
            session.commit()

        written_path = inspection_root.joinpath("2024", "Co so A (ID-100) (KT-2024-GMP)", "2. QD KT - GMP.docx")
        with ZipFile(written_path, "r") as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")

        print(
            json.dumps(
                {
                    "byte_size": result.byte_size,
                    "checksum": result.checksum_sha256,
                    "replaced_bookmarks": list(result.replaced_bookmarks),
                    "replaced_table_regions": list(result.replaced_table_regions),
                    "document_version_is_current": document_version.is_current,
                    "generation_run_status": generation_run.status.value,
                    "contains_row_1": "Noi dung 1" in document_xml,
                    "contains_row_2": "Noi dung 2" in document_xml,
                    "contains_muc_1": ">1<" in document_xml,
                    "contains_muc_2": ">2<" in document_xml,
                    "row_placeholder_removed": "ROW_NOIDUNG" not in document_xml,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        if smoke_root.exists():
            shutil.rmtree(smoke_root)


if __name__ == "__main__":
    main()
