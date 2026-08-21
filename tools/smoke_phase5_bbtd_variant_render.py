from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from zipfile import ZipFile

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
from backend.app.document.service import DocumentPreparationInput, render_template_aware_docx_generation
from backend.app.document.service_contract import DocumentGenerationRequest
from backend.app.document.template_binary import assign_template_binary_locator
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.types import StorageConfig
from tools.audit_phase5_real_templates import normalize_name


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


def find_template(prefix: str) -> Path:
    templates_root = ROOT / "legacy" / "Templates"
    matches = [
        path
        for path in templates_root.iterdir()
        if path.is_file() and normalize_name(path.name).startswith(prefix)
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one template for prefix={prefix!r}, found {len(matches)}")
    return matches[0]


def run_render(template_prefix: str, output_name: str, idempotency_key: str) -> dict[str, object]:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    smoke_root = ROOT / "artifacts" / "phase5" / f"_smoke_{idempotency_key}"
    if smoke_root.exists():
        shutil.rmtree(smoke_root)
    smoke_root.mkdir(parents=True, exist_ok=True)
    try:
        inspection_root = smoke_root / "inspection"
        template_root = smoke_root / "templates"
        inspection_root.mkdir(parents=True, exist_ok=True)
        template_root.mkdir(parents=True, exist_ok=True)

        source_template = find_template(template_prefix)
        template_relative_path = Path("inspection") / source_template.name
        target_template = template_root / template_relative_path
        target_template.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_template, target_template)

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
                original_filename=source_template.name,
            )
            result = render_template_aware_docx_generation(
                session,
                storage,
                DocumentPreparationInput(
                    request=DocumentGenerationRequest(
                        family_code="INSPECTION_BBTD_HOSO_DK",
                        requested_by_user_id=None,
                        case_id=fixture["case_id"],
                        gxp_type="GP",
                        storage_scope="inspection_folder",
                        idempotency_key=idempotency_key,
                    ),
                    payload_values={
                        "Daychuyen": "DAY_CHUYEN_A",
                        "Diachicoso": "DIA_CHI_A",
                        "Fulldate": "NGAY_A",
                        "Tencoso": "TEN_CO_SO_A",
                    },
                ),
                output_filename=output_name,
            )
            document_version = session.execute(
                select(DocumentVersion).where(DocumentVersion.id == result.document_version_id)
            ).scalar_one()
            generation_run = session.execute(
                select(DocumentGenerationRun).where(DocumentGenerationRun.id == result.generation_run_id)
            ).scalar_one()
            session.commit()

        written_path = inspection_root / "2024" / "Co so A (ID-100) (KT-2024-GMP)" / output_name
        with ZipFile(written_path, "r") as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")

        return {
            "template": source_template.name,
            "scalar_replacement_mode": result.scalar_replacement_mode,
            "template_variant_key": result.template_variant_key,
            "replaced_bookmarks": list(result.replaced_bookmarks),
            "document_version_is_current": document_version.is_current,
            "generation_run_status": generation_run.status.value,
            "daychuyen_count": document_xml.count("DAY_CHUYEN_A"),
            "diachicoso_count": document_xml.count("DIA_CHI_A"),
            "fulldate_count": document_xml.count("NGAY_A"),
            "tencoso_count": document_xml.count("TEN_CO_SO_A"),
        }
    finally:
        if smoke_root.exists():
            shutil.rmtree(smoke_root)


def main() -> None:
    report = {
        "line_1_variant": run_render(
            "1 bbtd ho so dk glp moi",
            "1. BBTD Ho so DK - GLP - Moi.docx",
            "smoke-phase5-bbtd-variant-line-1",
        ),
        "all_lines_variant": run_render(
            "1 bbtd ho so dk gmp moi",
            "1. BBTD Ho so DK - GMP - Moi.docx",
            "smoke-phase5-bbtd-variant-all-lines",
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
