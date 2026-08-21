from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.enums import CaseState, DocumentVariantType
from backend.app.db.models import Base
from backend.app.db.models.phase1 import Case, Company, Document, DocumentVariant, DocumentVersion, Site
from backend.app.db.session import build_engine
from backend.app.document.payload_builders import (
    PayloadBuildInput,
    build_payload_envelope,
    load_default_payload_builder_registry,
)
from backend.app.document.persistence import prepare_generation_persistence
from backend.app.document.seed_runtime import seed_default_template_metadata
from backend.app.document.service_contract import DocumentGenerationRequest, load_default_registry, plan_document_generation
from backend.app.document.source_resolver_contract import build_source_lookup_requests
from backend.app.document.source_resolver_db import resolve_source_document_from_db


def seed_business_fixture(session: Session) -> dict[str, str]:
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
        storage_binding_id=None,
        checksum_sha256=None,
        is_current=True,
        issued_on=None,
    )
    session.add(source_version)
    session.flush()

    return {
        "case_id": case.id,
        "source_document_id": source_document.id,
        "source_version_id": source_version.id,
    }


def main() -> None:
    database_url = "sqlite+pysqlite:///:memory:"
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    with session_factory() as session:
        seed_summary = seed_default_template_metadata(session)
        fixture = seed_business_fixture(session)
        registry = load_default_registry()
        payload_registry = load_default_payload_builder_registry()
        payload_result = build_payload_envelope(
            payload_registry,
            PayloadBuildInput(
                family_code="INSPECTION_PT_CT",
                values={
                    "QDKT": "12/QD",
                    "NgayQDKT": "2024-01-15",
                    "TT2": "Doan kiem tra",
                },
            )
        )
        plan = plan_document_generation(
            registry,
            DocumentGenerationRequest(
                family_code="INSPECTION_PT_CT",
                requested_by_user_id=None,
                case_id=fixture["case_id"],
                gxp_type="GP",
                storage_scope="inspection_folder",
                idempotency_key="smoke-phase5-ptct",
            ),
            payload_result.envelope,
        )
        lookup_requests = build_source_lookup_requests(plan)
        resolutions = tuple(resolve_source_document_from_db(session, request) for request in lookup_requests)
        persisted = prepare_generation_persistence(session, plan, source_resolutions=resolutions)
        session.commit()

    print(
        json.dumps(
            {
                "seed_summary": {
                    "template_definitions_created": seed_summary.template_definitions_created,
                    "template_definitions_updated": seed_summary.template_definitions_updated,
                    "template_bindings_created": seed_summary.template_bindings_created,
                    "template_bindings_updated": seed_summary.template_bindings_updated,
                },
                "lookup_request_count": len(lookup_requests),
                "resolved_source_document_ids": [item.candidate.document_id for item in resolutions],
                "resolved_source_version_ids": [item.candidate.document_version_id for item in resolutions],
                "persisted_document_id": persisted.document_id,
                "persisted_generation_run_id": persisted.generation_run_id,
                "persisted_source_dependency_ids": list(persisted.source_dependency_ids),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
