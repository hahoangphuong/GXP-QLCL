from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.models import Base
from backend.app.db.models.phase1 import BusinessEligibilityCertificate, Company, Site, TemplateBinding, TemplateDefinition
from backend.app.db.session import build_engine
from backend.app.document.seed_runtime import seed_default_template_metadata
from backend.app.document.service import DocumentPreparationInput, prepare_document_generation_job
from backend.app.document.service_contract import DocumentGenerationRequest, DocumentTemplateSelectionError


def seed_fixture(session) -> dict[str, str]:
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
    return {"business_eligibility_certificate_id": dkkd.id}


def resolve_with_mode(session, business_eligibility_certificate_id: str, legacy_mode: str | None) -> dict[str, object]:
    prepared = prepare_document_generation_job(
        session,
        DocumentPreparationInput(
            request=DocumentGenerationRequest(
                family_code="DDKD_APPENDIX_OR_DECISION",
                requested_by_user_id=None,
                business_eligibility_certificate_id=business_eligibility_certificate_id,
                storage_scope="dkkd_folder",
                legacy_mode=legacy_mode,
                idempotency_key=f"smoke-ddkd-appendix-selection-{legacy_mode or 'none'}",
            ),
            payload_values={
                "TenCty": "Cong ty A",
                "HoatdongKD": "Bao quan thuoc",
            },
        ),
    )
    template_definition = session.execute(
        select(TemplateDefinition).where(TemplateDefinition.id == prepared.persisted_state.template_definition_id)
    ).scalar_one()
    template_binding = session.execute(
        select(TemplateBinding).where(TemplateBinding.id == prepared.persisted_state.template_binding_id)
    ).scalar_one()
    return {
        "logical_name": prepared.generation_plan.template.logical_name,
        "template_pattern": prepared.generation_plan.template.template_pattern,
        "template_name": template_definition.template_name,
        "binding_legacy_mode": template_binding.legacy_mode,
    }


def main() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    with session_factory() as session:
        seed_default_template_metadata(session)
        fixture = seed_fixture(session)
        try:
            resolve_with_mode(session, fixture["business_eligibility_certificate_id"], None)
        except DocumentTemplateSelectionError as exc:
            ambiguous = {
                "ambiguous_without_legacy_mode": True,
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        else:
            raise RuntimeError("Expected DDKD appendix/decision selection to fail closed without legacy_mode.")

        appendix = resolve_with_mode(session, fixture["business_eligibility_certificate_id"], "appendix")
        decision = resolve_with_mode(session, fixture["business_eligibility_certificate_id"], "issuance_decision")
        session.commit()

    print(
        json.dumps(
            {
                "ambiguous": ambiguous,
                "appendix": appendix,
                "issuance_decision": decision,
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
