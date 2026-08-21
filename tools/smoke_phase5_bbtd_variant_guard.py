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
from backend.app.db.models.phase1 import Case, Company, Site, TemplateDefinition
from backend.app.db.session import build_engine
from backend.app.document.seed_runtime import seed_default_template_metadata
from backend.app.document.service import DocumentPreparationInput, render_template_aware_docx_generation
from backend.app.document.service_contract import DocumentGenerationRequest
from backend.app.document.template_binary import assign_template_binary_locator
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.types import StorageConfig


def _build_unknown_bbtd_template_bytes() -> bytes:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:bookmarkStart w:id="1" w:name="DayChuyen9"/><w:r><w:t>A</w:t></w:r><w:bookmarkEnd w:id="1"/></w:p>
    <w:p><w:bookmarkStart w:id="2" w:name="DiaChiCoSo9"/><w:r><w:t>B</w:t></w:r><w:bookmarkEnd w:id="2"/></w:p>
    <w:p><w:bookmarkStart w:id="3" w:name="Fulldate9"/><w:r><w:t>C</w:t></w:r><w:bookmarkEnd w:id="3"/></w:p>
    <w:p><w:bookmarkStart w:id="4" w:name="TenCoSo9"/><w:r><w:t>D</w:t></w:r><w:bookmarkEnd w:id="4"/></w:p>
    <w:sectPr><w:pgSz w:w="12240" w:h="15840"/></w:sectPr>
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
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>""",
        )
        archive.writestr("word/document.xml", document_xml)
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

    smoke_root = ROOT / "artifacts" / "phase5" / "_smoke_bbtd_variant_guard"
    if smoke_root.exists():
        shutil.rmtree(smoke_root)
    smoke_root.mkdir(parents=True, exist_ok=True)
    try:
        inspection_root = smoke_root / "inspection"
        template_root = smoke_root / "templates"
        inspection_root.mkdir(parents=True, exist_ok=True)
        template_root.mkdir(parents=True, exist_ok=True)

        template_relative_path = Path("inspection") / "1. BBTD Ho so DK - UNKNOWN.docx"
        target_template = template_root / template_relative_path
        target_template.parent.mkdir(parents=True, exist_ok=True)
        target_template.write_bytes(_build_unknown_bbtd_template_bytes())

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
                select(TemplateDefinition).where(TemplateDefinition.family_code == "INSPECTION_BBTD_HOSO_DK")
            ).scalar_one()
            assign_template_binary_locator(
                session,
                template_definition_id=template_definition.id,
                storage_root="template",
                storage_relative_path=template_relative_path.as_posix(),
                original_filename="1. BBTD Ho so DK - UNKNOWN.docx",
            )
            try:
                render_template_aware_docx_generation(
                    session,
                    storage,
                    DocumentPreparationInput(
                        request=DocumentGenerationRequest(
                            family_code="INSPECTION_BBTD_HOSO_DK",
                            requested_by_user_id=None,
                            case_id=fixture["case_id"],
                            gxp_type="GP",
                            storage_scope="inspection_folder",
                            idempotency_key="smoke-phase5-bbtd-variant-guard",
                        ),
                        payload_values={
                            "Daychuyen": "DAY_CHUYEN_A",
                            "Diachicoso": "DIA_CHI_A",
                            "Fulldate": "NGAY_A",
                            "Tencoso": "TEN_CO_SO_A",
                        },
                    ),
                    output_filename="1. BBTD Ho so DK - UNKNOWN.docx",
                )
            except Exception as exc:
                print(
                    json.dumps(
                        {
                            "guard_triggered": True,
                            "error_type": type(exc).__name__,
                            "message": str(exc),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return
            raise RuntimeError("Expected BBTD variant guard to fail closed, but render succeeded.")
    finally:
        if smoke_root.exists():
            shutil.rmtree(smoke_root)


if __name__ == "__main__":
    main()
