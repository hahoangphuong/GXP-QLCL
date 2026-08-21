from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.enums import CaseState
from backend.app.db.models import Base
from backend.app.db.models.phase1 import Case, Company, Site
from backend.app.db.session import build_engine
from backend.app.document.seed_runtime import seed_default_template_metadata
from backend.app.document.service import DocumentPreparationInput, prepare_and_allocate_document_generation_job
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

    with tempfile.TemporaryDirectory() as tmp_dir:
        inspection_root = Path(tmp_dir) / "inspection"
        inspection_root.mkdir(parents=True, exist_ok=True)
        storage = FilesystemStorageService(StorageConfig(inspection_root=inspection_root))

        with session_factory() as session:
            seed_default_template_metadata(session)
            fixture = seed_fixture(session, inspection_root)
            allocated = prepare_and_allocate_document_generation_job(
                session,
                storage,
                DocumentPreparationInput(
                    request=DocumentGenerationRequest(
                        family_code="INSPECTION_QD_KT",
                        requested_by_user_id=None,
                        case_id=fixture["case_id"],
                        gxp_type="GP",
                        storage_scope="inspection_folder",
                        idempotency_key="smoke-phase5-output-allocation",
                    ),
                    payload_values={
                        "QDKT": "12/QD",
                        "NgayQDKT": "2024-01-15",
                        "TT2": "Doan kiem tra",
                    },
                ),
                output_filename="2. QD KT - GMP.docx",
            )
            session.commit()

    print(
        json.dumps(
            {
                "render_ready": allocated.prepared.render_ready,
                "document_version_id": allocated.output_allocation.document_version_id,
                "version_no": allocated.output_allocation.version_no,
                "storage_relative_path": allocated.output_allocation.storage_relative_path,
                "storage_root": allocated.output_allocation.storage_root,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
