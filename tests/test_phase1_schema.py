from sqlalchemy.schema import CreateTable

from backend.app.db.models import Base
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificateLink,
    CaseAssessment,
    Certificate,
    Document,
    DocumentVariant,
    DocumentVersion,
    InspectionOutcome,
    ChangeApproval,
    StorageBinding,
)
from backend.app.runtime_schema import expected_alembic_head_revision


def test_metadata_contains_expected_tables():
    expected = {
        "company",
        "site",
        "case",
        "certificate",
        "business_eligibility_certificate",
        "business_eligibility_certificate_link",
        "document",
        "document_variant",
        "document_version",
        "storage_binding",
        "audit_event",
        "legacy_id_map",
    }
    assert expected.issubset(Base.metadata.tables.keys())


def test_business_eligibility_certificate_link_is_many_to_many_join():
    table = BusinessEligibilityCertificateLink.__table__
    assert {"business_eligibility_version_id", "certificate_id", "link_role"}.issubset(table.c.keys())
    unique_constraints = {tuple(col.name for col in c.columns) for c in table.constraints if c.__class__.__name__ == "UniqueConstraint"}
    assert ("business_eligibility_version_id", "certificate_id") in unique_constraints


def test_document_variant_and_version_are_separate_layers():
    assert DocumentVariant.__table__.c.document_id.foreign_keys
    assert DocumentVersion.__table__.c.document_variant_id.foreign_keys
    assert Document.__table__.c.case_id.foreign_keys


def test_storage_binding_uses_stable_legacy_triplet():
    table = StorageBinding.__table__
    unique_constraints = {tuple(col.name for col in c.columns) for c in table.constraints if c.__class__.__name__ == "UniqueConstraint"}
    assert ("year", "site_legacy_id", "inspection_legacy_code") in unique_constraints


def test_certificate_case_link_is_optional_for_administrative_reissue_flows():
    table = Certificate.__table__
    assert table.c.case_id.nullable is True
    assert table.c.issuance_basis.server_default is not None
    assert "line_code" in table.c.keys()


def test_certificate_version_preserves_standard_and_issuer_fields():
    table = Base.metadata.tables["certificate_version"]
    assert "applicable_standard" in table.c.keys()
    assert "issuing_authority" in table.c.keys()


def test_postgresql_ddl_renders_for_key_tables():
    for table in [Document.__table__, StorageBinding.__table__]:
        ddl = str(CreateTable(table).compile())
        assert "CREATE TABLE" in ddl


def test_legacy_result_narratives_use_text_columns():
    assert CaseAssessment.__table__.c.assessment_result.type.__class__.__name__ == "Text"
    assert InspectionOutcome.__table__.c.outcome_result.type.__class__.__name__ == "Text"
    assert ChangeApproval.__table__.c.result_label.type.__class__.__name__ == "Text"


def test_expected_alembic_head_revision_tracks_latest_runtime_migration():
    assert expected_alembic_head_revision() == "20260827_0004"
