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
from backend.app.db.models.phase1 import Case, Company, DocumentGenerationRun, DocumentVersion, Site
from backend.app.db.session import build_engine
from backend.app.document.seed_runtime import seed_default_template_metadata
from backend.app.document.service import DocumentPreparationInput, render_baseline_docx_generation
from backend.app.document.service_contract import DocumentGenerationRequest
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.types import StorageConfig


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

    smoke_root = ROOT / "artifacts" / "phase5" / "_smoke_docx_render"
    if smoke_root.exists():
        shutil.rmtree(smoke_root)
    smoke_root.mkdir(parents=True, exist_ok=True)
    try:
        inspection_root = smoke_root / "inspection"
        inspection_root.mkdir(parents=True, exist_ok=True)
        storage = FilesystemStorageService(StorageConfig(inspection_root=inspection_root))

        with session_factory() as session:
            seed_default_template_metadata(session)
            fixture = seed_fixture(session, inspection_root)
            render_result = render_baseline_docx_generation(
                session,
                storage,
                DocumentPreparationInput(
                    request=DocumentGenerationRequest(
                        family_code="INSPECTION_QD_KT",
                        requested_by_user_id=None,
                        case_id=fixture["case_id"],
                        gxp_type="GP",
                        storage_scope="inspection_folder",
                        idempotency_key="smoke-phase5-docx-render",
                    ),
                    payload_values={
                        "QDKT": "12/QD",
                        "NgayQDKT": "2024-01-15",
                        "TT2": "Doan kiem tra",
                    },
                ),
                output_filename="2. QD KT - GMP.docx",
            )
            document_version = session.execute(
                select(DocumentVersion).where(DocumentVersion.id == render_result.output_allocation.document_version_id)
            ).scalar_one()
            generation_run = session.execute(
                select(DocumentGenerationRun).where(
                    DocumentGenerationRun.id == render_result.output_allocation.generation_run_id
                )
            ).scalar_one()
            session.commit()

        written_path = inspection_root.joinpath(*render_result.output_allocation.storage_relative_path.split("/"))
        with ZipFile(written_path, "r") as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
    finally:
        if smoke_root.exists():
            shutil.rmtree(smoke_root)

    print(
        json.dumps(
            {
                "byte_size": render_result.byte_size,
                "checksum": render_result.checksum_sha256,
                "document_version_is_current": document_version.is_current,
                "generation_run_status": generation_run.status.value,
                "contains_qdkt": "12/QD" in document_xml,
                "contains_family_code": "INSPECTION_QD_KT" in document_xml,
                "written_path": render_result.output_allocation.storage_relative_path,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
