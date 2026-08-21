from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.enums import CaseState, DocumentVariantType
from backend.app.db.models import Base
from backend.app.db.models.phase1 import Case, Company, Document, DocumentVariant, DocumentVersion, Site, StorageBinding
from backend.app.db.session import build_engine
from backend.app.document.seed_runtime import seed_default_template_metadata
from backend.app.document.service import DocumentPreparationInput, prepare_document_generation_job
from backend.app.document.service_contract import DocumentGenerationRequest
from backend.app.document.source_binary_access import open_source_binary_stream
from backend.app.document.version_locator import assign_document_version_locator
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

    folder_relative_path = "2024/Co so A (ID-100) (KT-2024-GMP)"
    folder_path = inspection_root / folder_relative_path
    folder_path.mkdir(parents=True, exist_ok=True)
    source_file = folder_path / "6. PT.PCT - GMP.docx"
    source_file.write_bytes(b"legacy-pt-pct-source")

    binding = StorageBinding(
        case_id=case.id,
        year=2024,
        site_legacy_id=100,
        inspection_legacy_code="KT-2024-GMP",
        relative_path=folder_relative_path,
        observed_folder_label="Co so A (ID-100) (KT-2024-GMP)",
        storage_class="local_filesystem_fake",
    )
    session.add(binding)
    session.flush()

    source_document = Document(
        family_code="INSPECTION_PT_PCT",
        document_type_code="inspection_pt_pct",
        title="PT.PCT GMP",
        case_id=case.id,
    )
    session.add(source_document)
    session.flush()

    source_variant = DocumentVariant(
        document_id=source_document.id,
        variant_type=DocumentVariantType.EDITABLE_DOCX,
        language_code="vi",
        is_active=True,
    )
    session.add(source_variant)
    session.flush()

    source_version = DocumentVersion(
        document_variant_id=source_variant.id,
        version_no=1,
        storage_binding_id=binding.id,
        checksum_sha256=None,
        is_current=True,
        issued_on=None,
    )
    session.add(source_version)
    session.flush()
    assign_document_version_locator(
        session,
        document_version_id=source_version.id,
        storage_root="inspection",
        storage_relative_path=f"{folder_relative_path}/6. PT.PCT - GMP.docx",
        original_filename="6. PT.PCT - GMP.docx",
    )
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
            prepared = prepare_document_generation_job(
                session,
                DocumentPreparationInput(
                    request=DocumentGenerationRequest(
                        family_code="INSPECTION_PT_CT",
                        requested_by_user_id=None,
                        case_id=fixture["case_id"],
                        gxp_type="GP",
                        storage_scope="inspection_folder",
                        idempotency_key="smoke-phase5-source-binary",
                    ),
                    payload_values={
                        "QDKT": "12/QD",
                        "NgayQDKT": "2024-01-15",
                        "TT2": "Doan kiem tra",
                    },
                ),
            )
            with open_source_binary_stream(storage, prepared.source_binary_requirements[0]) as stream:
                binary_payload = stream.read().decode("utf-8")
            session.commit()

    print(
        json.dumps(
            {
                "render_ready": prepared.render_ready,
                "source_binary_requirement_status": prepared.source_binary_requirements[0].readiness_status,
                "exact_storage_relative_path": prepared.source_binary_requirements[0].exact_storage_relative_path,
                "source_payload_preview": binary_payload,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
