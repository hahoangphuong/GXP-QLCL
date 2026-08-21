from __future__ import annotations

import json
import sys
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


def seed_fixture(session):
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

    binding = StorageBinding(
        case_id=case.id,
        year=2024,
        site_legacy_id=100,
        inspection_legacy_code="KT-2024-GMP",
        relative_path="2024/Co so A (ID-100) (KT-2024-GMP)",
        observed_folder_label="Co so A (ID-100) (KT-2024-GMP)",
        storage_class="synology_legacy",
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

    return {
        "case_id": case.id,
    }


def main() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    with session_factory() as session:
        seed_default_template_metadata(session)
        fixture = seed_fixture(session)
        prepared = prepare_document_generation_job(
            session,
            DocumentPreparationInput(
                request=DocumentGenerationRequest(
                    family_code="INSPECTION_PT_CT",
                    requested_by_user_id=None,
                    case_id=fixture["case_id"],
                    gxp_type="GP",
                    storage_scope="inspection_folder",
                    idempotency_key="smoke-phase5-pre-render",
                ),
                payload_values={
                    "QDKT": "12/QD",
                    "NgayQDKT": "2024-01-15",
                    "TT2": "Doan kiem tra",
                },
            ),
        )
        session.commit()

    print(
        json.dumps(
            {
                "render_ready": prepared.render_ready,
                "lookup_request_count": len(prepared.source_lookup_requests),
                "source_binary_requirements": [
                    {
                        "source_family_code": requirement.source_family_code,
                        "storage_root": requirement.storage_root,
                        "folder_relative_path": requirement.folder_relative_path,
                        "legacy_filename_prefix_hints": list(requirement.legacy_filename_prefix_hints),
                        "readiness_status": requirement.readiness_status,
                    }
                    for requirement in prepared.source_binary_requirements
                ],
                "persisted_generation_run_id": prepared.persisted_state.generation_run_id,
                "persisted_source_dependency_ids": list(prepared.persisted_state.source_dependency_ids),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
