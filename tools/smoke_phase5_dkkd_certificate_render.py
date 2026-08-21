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

from backend.app.db.models import Base
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate,
    Company,
    DocumentGenerationRun,
    DocumentVersion,
    Site,
    TemplateDefinition,
)
from backend.app.db.session import build_engine
from backend.app.document.seed_runtime import seed_default_template_metadata
from backend.app.document.service import DocumentPreparationInput, render_template_aware_docx_generation
from backend.app.document.service_contract import DocumentGenerationRequest
from backend.app.document.template_binary import assign_template_binary_locator
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.types import StorageConfig
from tools.audit_phase5_real_templates import normalize_name


def seed_fixture(session, dkkd_root: Path) -> dict[str, str]:
    company = Company(legacy_company_id=1, legal_name="Cong ty A")
    session.add(company)
    session.flush()

    site = Site(legacy_site_id=100, company_id=company.id, site_name="Co so A")
    session.add(site)
    session.flush()

    dkkd = BusinessEligibilityCertificate(
        legacy_dkkd_id=300,
        site_id=site.id,
        company_id=company.id,
        latest_flag=True,
        latest_legacy_dkkd_id=300,
    )
    session.add(dkkd)
    session.flush()

    folder_path = dkkd_root / "Cong ty A - Dia chi A (100)"
    folder_path.mkdir(parents=True, exist_ok=True)
    return {"business_eligibility_certificate_id": dkkd.id}


def find_dkkd_template(prefix: str) -> Path:
    templates_root = ROOT / "legacy" / "Templates"
    matches = [
        path
        for path in templates_root.iterdir()
        if path.is_file() and normalize_name(path.name).startswith(prefix)
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one DDKD template for prefix={prefix!r}, found {len(matches)}")
    return matches[0]


def main() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    smoke_root = ROOT / "artifacts" / "phase5" / "_smoke_dkkd_certificate_render"
    if smoke_root.exists():
        shutil.rmtree(smoke_root)
    smoke_root.mkdir(parents=True, exist_ok=True)
    try:
        inspection_root = smoke_root / "inspection"
        dkkd_root = smoke_root / "dkkd"
        template_root = smoke_root / "templates"
        inspection_root.mkdir(parents=True, exist_ok=True)
        dkkd_root.mkdir(parents=True, exist_ok=True)
        template_root.mkdir(parents=True, exist_ok=True)

        source_template = find_dkkd_template("z2 giay chung nhan ddkkdd moi")
        template_relative_path = Path("dkkd") / source_template.name
        target_template = template_root / template_relative_path
        target_template.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_template, target_template)

        storage = FilesystemStorageService(
            StorageConfig(
                inspection_root=inspection_root,
                dkkd_root=dkkd_root,
                template_root=template_root,
            )
        )

        with session_factory() as session:
            seed_default_template_metadata(session)
            fixture = seed_fixture(session, dkkd_root)
            template_definition = session.execute(
                select(TemplateDefinition).where(TemplateDefinition.family_code == "DDKD_CERTIFICATE")
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
                        family_code="DDKD_CERTIFICATE",
                        requested_by_user_id=None,
                        business_eligibility_certificate_id=fixture["business_eligibility_certificate_id"],
                        storage_scope="dkkd_folder",
                        idempotency_key="smoke-phase5-dkkd-certificate-render",
                    ),
                    payload_values={
                        "TenCty": "Cong ty A",
                        "DiachiCoso": "123 Duong A",
                        "HoatdongKD": "Bao quan, ban buon thuoc",
                    },
                ),
                output_filename="z2. Giay chung nhan DDKKDD.docx",
            )
            document_version = session.execute(
                select(DocumentVersion).where(DocumentVersion.id == result.document_version_id)
            ).scalar_one()
            generation_run = session.execute(
                select(DocumentGenerationRun).where(DocumentGenerationRun.id == result.generation_run_id)
            ).scalar_one()
            session.commit()

        written_path = dkkd_root / "Cong ty A - Dia chi A (100)" / "z2. Giay chung nhan DDKKDD.docx"
        with ZipFile(written_path, "r") as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")

        print(
            json.dumps(
                {
                    "scalar_replacement_mode": result.scalar_replacement_mode,
                    "template_variant_key": result.template_variant_key,
                    "byte_size": result.byte_size,
                    "checksum": result.checksum_sha256,
                    "document_version_is_current": document_version.is_current,
                    "document_version_storage_root": document_version.storage_root,
                    "document_version_storage_binding_id": document_version.storage_binding_id,
                    "generation_run_status": generation_run.status.value,
                    "contains_ten_cty": "Cong ty A" in document_xml,
                    "contains_dia_chi": "123 Duong A" in document_xml,
                    "contains_hoat_dong": "Bao quan, ban buon thuoc" in document_xml,
                    "written_exists": written_path.exists(),
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
