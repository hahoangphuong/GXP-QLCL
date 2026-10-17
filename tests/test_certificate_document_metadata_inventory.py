"""Registered document metadata inventory for GxP / business eligibility owners.

These endpoints MUST NOT infer signed-original authenticity, bind storage or
derive Case/Site coverage. Exercises real owner UUIDs using disposable SQLite.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import DocumentVariantType
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate, Certificate, Company, Document,
    DocumentVariant, DocumentVersion, Site,
)
from backend.app.main import create_app


def _endpoint(app, path):
    return next(route.endpoint for route in app.routes if getattr(route, "path", None) == path)


def _seed(session):
    company = Company(legal_name="Synthetic owner company")
    session.add(company)
    session.flush()
    site = Site(company_id=company.id, site_name="Synthetic owner Site")
    session.add(site)
    session.flush()
    gxp = Certificate(site_id=site.id, certificate_type="GMP")
    ddk = BusinessEligibilityCertificate(site_id=site.id, company_id=company.id)
    session.add_all([gxp, ddk])
    session.commit()
    return gxp.id, ddk.id


def _app_and_session(tmp_path):
    url = f"sqlite:///{(tmp_path / 'document-owner-metadata.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    return create_app(url), engine


@pytest.mark.parametrize(
    ("route", "expected_owner_kind"),
    (
        ("/certificates/{certificate_id}/document-metadata", "certificate"),
        (
            "/business-eligibility-certificates/{business_eligibility_certificate_id}/document-metadata",
            "business_eligibility_certificate",
        ),
    ),
)
def test_owner_metadata_inventory_is_exact_and_never_claims_binary_proof(
    tmp_path, route, expected_owner_kind
):
    app, engine = _app_and_session(tmp_path)
    with Session(engine) as session:
        cert_id, ddk_id = _seed(session)
        ids = {"certificate": cert_id, "business_eligibility_certificate": ddk_id}
        endpoint = _endpoint(app, route)
        viewer = build_authenticated_user(
            "document-viewer", permissions={"certificate.view", "document.read"}
        )

        empty = endpoint(ids[expected_owner_kind], session, viewer)
        assert empty.owner_kind == expected_owner_kind
        assert empty.owner_id == ids[expected_owner_kind]
        assert empty.metadata_status == "no_registered_document_metadata"
        assert empty.documents == []
        assert empty.binary_verified is False
        assert empty.original_signed_document_verified is False

        cert_doc = Document(
            certificate_id=cert_id, family_code="CERTIFICATE_ORIGINAL",
            document_type_code="CERTIFICATE_ORIGINAL", title="Unverified GMP record",
        )
        ddk_doc = Document(
            business_eligibility_certificate_id=ddk_id,
            family_code="DDK_CERTIFICATE_ORIGINAL",
            document_type_code="DDK_CERTIFICATE_ORIGINAL",
            title="Unverified DDK record",
        )
        session.add_all([cert_doc, ddk_doc])
        session.flush()
        variant = DocumentVariant(
            document_id=cert_doc.id, variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi", is_active=True,
        )
        session.add(variant)
        session.flush()
        session.add(DocumentVersion(
            document_variant_id=variant.id, version_no=1,
            original_filename="unverified-source.docx", is_current=True,
            storage_root=None, storage_relative_path=None,
        ))
        session.commit()

        result = endpoint(ids[expected_owner_kind], session, viewer)
        assert result.metadata_status == "registered_metadata_only_unverified"
        assert result.owner_kind == expected_owner_kind
        assert result.binary_verified is False
        assert result.original_signed_document_verified is False
        assert len(result.documents) == 1
        row = result.documents[0]
        assert row.document_id == (
            cert_doc.id if expected_owner_kind == "certificate" else ddk_doc.id
        )
        assert row.registered_variant_count == (1 if expected_owner_kind == "certificate" else 0)
        assert row.registered_version_count == (1 if expected_owner_kind == "certificate" else 0)
        assert row.registered_current_version_count == (
            1 if expected_owner_kind == "certificate" else 0
        )
        # No filenames, storage location, checksum, binary URL or source claim.
        assert set(row.model_dump()) == {
            "document_id", "family_code", "document_type_code", "title",
            "registered_variant_count", "registered_version_count",
            "registered_current_version_count",
        }
        assert "unverified-source.docx" not in str(result.model_dump())

        with pytest.raises(HTTPException) as denied:
            endpoint(
                ids[expected_owner_kind], session,
                build_authenticated_user("cert-only", permissions={"certificate.view"}),
            )
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as absent:
            endpoint("ffffffff-ffff-ffff-ffff-ffffffffffff", session, viewer)
        assert absent.value.status_code == 404
    engine.dispose()


@pytest.mark.parametrize(
    ("route", "owner_kind"),
    (
        ("/certificates/{certificate_id}/document-metadata", "certificate"),
        (
            "/business-eligibility-certificates/{business_eligibility_certificate_id}/document-metadata",
            "business_eligibility_certificate",
        ),
    ),
)
def test_ambiguous_multi_parent_document_fails_closed_without_rebinding(tmp_path, route, owner_kind):
    app, engine = _app_and_session(tmp_path)
    with Session(engine) as session:
        cert_id, ddk_id = _seed(session)
        document = Document(
            certificate_id=cert_id,
            business_eligibility_certificate_id=ddk_id,
            family_code="UNRESOLVED",
            document_type_code="UNRESOLVED",
        )
        session.add(document)
        session.commit()
        endpoint = _endpoint(app, route)
        target_id = cert_id if owner_kind == "certificate" else ddk_id
        with pytest.raises(HTTPException) as blocked:
            endpoint(
                target_id, session,
                build_authenticated_user(
                    "document-viewer", permissions={"certificate.view", "document.read"}
                ),
            )
        assert blocked.value.status_code == 409
        assert document.certificate_id == cert_id
        assert document.business_eligibility_certificate_id == ddk_id
    engine.dispose()
