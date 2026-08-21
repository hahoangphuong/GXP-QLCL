from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

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
from backend.app.document.service import DocumentPreparationInput, prepare_template_aware_docx_generation
from backend.app.document.service_contract import DocumentGenerationRequest
from backend.app.document.template_binary import assign_template_binary_locator, open_template_binary_stream
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

    smoke_root = ROOT / "artifacts" / "phase5" / "_smoke_template_ingestion"
    if smoke_root.exists():
        shutil.rmtree(smoke_root)
    smoke_root.mkdir(parents=True, exist_ok=True)
    try:
        inspection_root = smoke_root / "inspection"
        template_root = smoke_root / "templates"
        inspection_root.mkdir(parents=True, exist_ok=True)
        template_root.mkdir(parents=True, exist_ok=True)
        template_file = template_root / "inspection" / "2. QD KT - GMP.dotx"
        template_file.parent.mkdir(parents=True, exist_ok=True)
        template_file.write_bytes(b"fake-template-binary")
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
                storage_relative_path="inspection/2. QD KT - GMP.dotx",
                original_filename="2. QD KT - GMP.dotx",
            )
            prepared = prepare_template_aware_docx_generation(
                session,
                storage,
                DocumentPreparationInput(
                    request=DocumentGenerationRequest(
                        family_code="INSPECTION_QD_KT",
                        requested_by_user_id=None,
                        case_id=fixture["case_id"],
                        gxp_type="GP",
                        storage_scope="inspection_folder",
                        idempotency_key="smoke-phase5-template-ingestion",
                    ),
                    payload_values={
                        "QDKT": "12/QD",
                        "NgayQDKT": "2024-01-15",
                        "TT2": "Doan kiem tra",
                    },
                ),
                output_filename="2. QD KT - GMP.docx",
            )
            with open_template_binary_stream(storage, prepared.template_binary_requirement) as stream:
                template_preview = stream.read().decode("utf-8")
            session.commit()

        print(
            json.dumps(
                {
                    "template_render_ready": prepared.template_render_ready,
                    "template_requirement_status": prepared.template_binary_requirement.readiness_status,
                    "template_storage_relative_path": prepared.template_binary_requirement.storage_relative_path,
                    "output_storage_relative_path": prepared.allocated.output_allocation.storage_relative_path,
                    "template_preview": template_preview,
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
