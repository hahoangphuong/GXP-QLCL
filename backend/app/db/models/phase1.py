from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from backend.app.db.enums import (
    AuditActorType,
    CaseState,
    ChangeRequestState,
    DocumentGenerationStatus,
    DocumentVariantType,
    InspectionEventType,
    LegacyEntityType,
    StorageResolutionStatus,
)


class VersionedMixin:
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    __mapper_args__ = {"version_id_col": row_version}


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "company"

    legacy_company_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    legacy_gmp_company_code: Mapped[str | None] = mapped_column(String(32))
    legacy_glp_company_code: Mapped[str | None] = mapped_column(String(32))
    legacy_gmpbb_company_code: Mapped[str | None] = mapped_column(String(32))
    legal_name: Mapped[str] = mapped_column(String(512), nullable=False)
    english_name: Mapped[str | None] = mapped_column(String(512))
    short_name: Mapped[str | None] = mapped_column(String(128))
    legal_address: Mapped[str | None] = mapped_column(Text)
    legal_address_en: Mapped[str | None] = mapped_column(Text)
    is_inactive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class Site(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "site"

    legacy_site_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    legacy_gmp_site_code: Mapped[str | None] = mapped_column(String(32))
    legacy_glp_site_code: Mapped[str | None] = mapped_column(String(32))
    legacy_gmpbb_site_code: Mapped[str | None] = mapped_column(String(32))
    site_name: Mapped[str] = mapped_column(String(512), nullable=False)
    site_name_en: Mapped[str | None] = mapped_column(String(512))
    site_address: Mapped[str | None] = mapped_column(Text)
    site_address_en: Mapped[str | None] = mapped_column(Text)
    province_name: Mapped[str | None] = mapped_column(String(255))
    short_name: Mapped[str | None] = mapped_column(String(255))


class Person(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "person"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)


class PersonRole(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "person_role"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("site.id"), index=True)
    role_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role_title: Mapped[str | None] = mapped_column(String(255))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class ProfessionalLicense(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "professional_license"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    license_number: Mapped[str] = mapped_column(String(128), nullable=False)
    qualification: Mapped[str | None] = mapped_column(String(255))
    issued_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)


class InspectorProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inspector_profile"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, unique=True)
    legacy_initials: Mapped[str | None] = mapped_column(String(32))
    legacy_display_text: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class DictionaryValue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dictionary_value"

    dictionary_name: Mapped[str] = mapped_column(String(128), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_en: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("dictionary_name", "key"),)


class Case(UUIDPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "case"

    legacy_inspection_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    legacy_inspection_code: Mapped[str | None] = mapped_column(String(64), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"), nullable=False, index=True)
    gxp_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_code: Mapped[str | None] = mapped_column(String(32))
    applicable_standard: Mapped[str | None] = mapped_column(String(255))
    inspection_type: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[CaseState] = mapped_column(Enum(CaseState, name="case_state"), nullable=False, index=True)
    opened_year: Mapped[int | None] = mapped_column(Integer)


class CaseApplication(UUIDPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "case_application"

    case_id: Mapped[str] = mapped_column(ForeignKey("case.id"), nullable=False, unique=True)
    submitted_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dossier_code: Mapped[str | None] = mapped_column(String(128))
    dossier_reference: Mapped[str | None] = mapped_column(Text)
    applicant_name: Mapped[str | None] = mapped_column(String(255))


class CaseAssessment(UUIDPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "case_assessment"

    case_id: Mapped[str] = mapped_column(ForeignKey("case.id"), nullable=False, unique=True)
    assessed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assessor_name: Mapped[str | None] = mapped_column(String(255))
    assessment_result: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)


class InspectionPlan(UUIDPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "inspection_plan"

    case_id: Mapped[str] = mapped_column(ForeignKey("case.id"), nullable=False, unique=True)
    plan_start_on: Mapped[date | None] = mapped_column(Date)
    plan_end_on: Mapped[date | None] = mapped_column(Date)
    planning_sheet_name: Mapped[str | None] = mapped_column(String(64))
    decision_document_hint: Mapped[str | None] = mapped_column(String(255))


class InspectionEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inspection_event"

    case_id: Mapped[str] = mapped_column(ForeignKey("case.id"), nullable=False, index=True)
    event_type: Mapped[InspectionEventType] = mapped_column(
        Enum(InspectionEventType, name="inspection_event_type"),
        nullable=False,
        index=True,
    )
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[str | None] = mapped_column(Text)


class InspectionTeam(UUIDPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "inspection_team"

    case_id: Mapped[str] = mapped_column(ForeignKey("case.id"), nullable=False, unique=True)
    display_text: Mapped[str | None] = mapped_column(Text)


class InspectionTeamMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inspection_team_member"

    team_id: Mapped[str] = mapped_column(ForeignKey("inspection_team.id"), nullable=False, index=True)
    inspector_profile_id: Mapped[str | None] = mapped_column(ForeignKey("inspector_profile.id"), index=True)
    person_id: Mapped[str | None] = mapped_column(ForeignKey("person.id"), index=True)
    role_label: Mapped[str | None] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    __table_args__ = (CheckConstraint("inspector_profile_id IS NOT NULL OR person_id IS NOT NULL", name="team_member_has_identity"),)


class InspectionOutcome(UUIDPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "inspection_outcome"

    case_id: Mapped[str] = mapped_column(ForeignKey("case.id"), nullable=False, unique=True)
    inspected_on: Mapped[date | None] = mapped_column(Date)
    inspected_to_on: Mapped[date | None] = mapped_column(Date)
    decision_reference: Mapped[str | None] = mapped_column(String(255))
    bbkt_reference: Mapped[str | None] = mapped_column(String(255))
    outcome_result: Mapped[str | None] = mapped_column(String(255))


class CapaCycle(UUIDPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "capa_cycle"

    case_id: Mapped[str] = mapped_column(ForeignKey("case.id"), nullable=False, index=True)
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_on: Mapped[date | None] = mapped_column(Date)
    submitted_on: Mapped[date | None] = mapped_column(Date)
    assessed_on: Mapped[date | None] = mapped_column(Date)
    assessor_user_id: Mapped[str | None] = mapped_column(ForeignKey("app_user.id"), index=True)
    assessor_name: Mapped[str | None] = mapped_column(String(255))
    result: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="draft", server_default="draft")
    notes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("case_id", "round_no"),)


class Certificate(UUIDPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "certificate"

    legacy_certificate_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("case.id"), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"), nullable=False, index=True)
    certificate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    issuance_basis: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="inspection_case",
        server_default="inspection_case",
    )
    latest_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    latest_legacy_certificate_id: Mapped[int | None] = mapped_column(Integer)


class CertificateVersion(UUIDPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "certificate_version"

    certificate_id: Mapped[str] = mapped_column(ForeignKey("certificate.id"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    certificate_number: Mapped[str | None] = mapped_column(String(128))
    is_latest_version: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    __table_args__ = (UniqueConstraint("certificate_id", "version_no"),)


class CertificateScope(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "certificate_scope"

    certificate_version_id: Mapped[str] = mapped_column(ForeignKey("certificate_version.id"), nullable=False, index=True)
    scope_key: Mapped[str | None] = mapped_column(String(128))
    scope_text: Mapped[str] = mapped_column(Text, nullable=False)
    language_code: Mapped[str] = mapped_column(String(8), nullable=False, default="vi", server_default="vi")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class BusinessEligibilityCertificate(UUIDPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "business_eligibility_certificate"

    legacy_dkkd_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"), nullable=False, index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("company.id"), nullable=False, index=True)
    latest_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    latest_legacy_dkkd_id: Mapped[int | None] = mapped_column(Integer)


class BusinessEligibilityVersion(UUIDPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "business_eligibility_version"

    business_eligibility_certificate_id: Mapped[str] = mapped_column(
        ForeignKey("business_eligibility_certificate.id"),
        nullable=False,
        index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    certificate_number: Mapped[str | None] = mapped_column(String(128))
    issued_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)
    professional_responsible_person_name: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("business_eligibility_certificate_id", "version_no"),)


class BusinessEligibilityCertificateLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_eligibility_certificate_link"

    business_eligibility_version_id: Mapped[str] = mapped_column(
        ForeignKey("business_eligibility_version.id"),
        nullable=False,
        index=True,
    )
    certificate_id: Mapped[str] = mapped_column(ForeignKey("certificate.id"), nullable=False, index=True)
    link_role: Mapped[str] = mapped_column(String(64), nullable=False, default="source_certificate", server_default="source_certificate")
    __table_args__ = (UniqueConstraint("business_eligibility_version_id", "certificate_id"),)


class ChangeRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "change_request"

    legacy_change_request_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("site.id"), nullable=False, index=True)
    scope_label: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    submitted_on: Mapped[date | None] = mapped_column(Date)
    requester_name: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[ChangeRequestState] = mapped_column(
        Enum(ChangeRequestState, name="change_request_state"),
        nullable=False,
        index=True,
    )


class ChangeRequestDetail(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "change_request_detail"

    legacy_change_detail_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    change_request_id: Mapped[str] = mapped_column(ForeignKey("change_request.id"), nullable=False, index=True)
    classification_id: Mapped[int | None] = mapped_column(Integer)
    classification_label: Mapped[str | None] = mapped_column(String(255))
    approval_status: Mapped[str | None] = mapped_column(String(255))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)


class ChangeApproval(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "change_approval"

    change_request_id: Mapped[str] = mapped_column(ForeignKey("change_request.id"), nullable=False, unique=True)
    handled_on: Mapped[date | None] = mapped_column(Date)
    handled_by_name: Mapped[str | None] = mapped_column(String(255))
    result_label: Mapped[str | None] = mapped_column(String(255))
    effective_on: Mapped[date | None] = mapped_column(Date)
    approval_reference: Mapped[str | None] = mapped_column(String(255))


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document"

    legacy_entity_type: Mapped[LegacyEntityType | None] = mapped_column(Enum(LegacyEntityType, name="legacy_entity_type"))
    family_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    document_type_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    case_id: Mapped[str | None] = mapped_column(ForeignKey("case.id"), index=True)
    capa_cycle_id: Mapped[str | None] = mapped_column(ForeignKey("capa_cycle.id"), index=True)
    certificate_id: Mapped[str | None] = mapped_column(ForeignKey("certificate.id"), index=True)
    business_eligibility_certificate_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_eligibility_certificate.id"),
        index=True,
    )
    change_request_id: Mapped[str | None] = mapped_column(ForeignKey("change_request.id"), index=True)
    __table_args__ = (
        CheckConstraint(
            "(case_id IS NOT NULL) OR (capa_cycle_id IS NOT NULL) OR (certificate_id IS NOT NULL) OR "
            "(business_eligibility_certificate_id IS NOT NULL) OR (change_request_id IS NOT NULL)",
            name="document_has_parent",
        ),
    )


class DocumentVariant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_variant"

    document_id: Mapped[str] = mapped_column(ForeignKey("document.id"), nullable=False, index=True)
    variant_type: Mapped[DocumentVariantType] = mapped_column(
        Enum(DocumentVariantType, name="document_variant_type"),
        nullable=False,
    )
    language_code: Mapped[str] = mapped_column(String(8), nullable=False, default="vi", server_default="vi")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    __table_args__ = (UniqueConstraint("document_id", "variant_type", "language_code"),)


class DocumentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_version"

    document_variant_id: Mapped[str] = mapped_column(ForeignKey("document_variant.id"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_binding_id: Mapped[str | None] = mapped_column(ForeignKey("storage_binding.id"), index=True)
    storage_root: Mapped[str | None] = mapped_column(String(32))
    storage_relative_path: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    issued_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("document_variant_id", "version_no"),
        CheckConstraint(
            "(storage_root IS NULL AND storage_relative_path IS NULL) OR "
            "(storage_root IS NOT NULL AND storage_relative_path IS NOT NULL)",
            name="document_version_storage_locator_complete",
        ),
    )


class DocumentRelation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_relation"

    source_document_id: Mapped[str] = mapped_column(ForeignKey("document.id"), nullable=False, index=True)
    target_document_id: Mapped[str] = mapped_column(ForeignKey("document.id"), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        UniqueConstraint("source_document_id", "target_document_id", "relation_type"),
        CheckConstraint("source_document_id <> target_document_id", name="document_relation_not_self"),
    )


class TemplateDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "template_definition"

    family_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    document_type_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_application: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    legacy_host_procedure: Mapped[str | None] = mapped_column(String(128))
    legacy_case_number: Mapped[int | None] = mapped_column(Integer)
    variant_type: Mapped[DocumentVariantType] = mapped_column(
        Enum(DocumentVariantType, name="template_variant_type"),
        nullable=False,
    )
    template_name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_pattern: Mapped[str | None] = mapped_column(String(255))
    bookmark_contract: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    notes: Mapped[str | None] = mapped_column(Text)
    template_storage_root: Mapped[str | None] = mapped_column(String(32))
    template_storage_relative_path: Mapped[str | None] = mapped_column(Text)
    template_original_filename: Mapped[str | None] = mapped_column(String(255))
    template_checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("family_code", "template_name"),
        CheckConstraint(
            "(template_storage_root IS NULL AND template_storage_relative_path IS NULL) OR "
            "(template_storage_root IS NOT NULL AND template_storage_relative_path IS NOT NULL)",
            name="template_definition_storage_locator_complete",
        ),
    )


class TemplateBinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "template_binding"

    family_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    template_definition_id: Mapped[str] = mapped_column(ForeignKey("template_definition.id"), nullable=False, index=True)
    gxp_type: Mapped[str | None] = mapped_column(String(32), index=True)
    legacy_mode: Mapped[str | None] = mapped_column(String(64), index=True)
    storage_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    __table_args__ = (
        UniqueConstraint("family_code", "template_definition_id", "gxp_type", "legacy_mode", "storage_scope"),
    )


class DocumentGenerationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_generation_run"

    document_id: Mapped[str] = mapped_column(ForeignKey("document.id"), nullable=False, index=True)
    template_binding_id: Mapped[str | None] = mapped_column(ForeignKey("template_binding.id"), index=True)
    template_definition_id: Mapped[str | None] = mapped_column(ForeignKey("template_definition.id"), index=True)
    output_document_version_id: Mapped[str | None] = mapped_column(ForeignKey("document_version.id"), index=True)
    status: Mapped[DocumentGenerationStatus] = mapped_column(
        Enum(DocumentGenerationStatus, name="document_generation_status"),
        nullable=False,
        index=True,
    )
    source_application: Mapped[str | None] = mapped_column(String(32))
    requested_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("app_user.id"), index=True)
    input_payload_redacted: Mapped[str | None] = mapped_column(Text)
    error_summary: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)


class DocumentSourceDependency(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_source_dependency"

    document_generation_run_id: Mapped[str] = mapped_column(
        ForeignKey("document_generation_run.id"),
        nullable=False,
        index=True,
    )
    source_document_id: Mapped[str] = mapped_column(ForeignKey("document.id"), nullable=False, index=True)
    source_document_version_id: Mapped[str | None] = mapped_column(ForeignKey("document_version.id"), index=True)
    dependency_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_bookmarks: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint(
            "document_generation_run_id",
            "source_document_id",
            "source_document_version_id",
            "dependency_type",
        ),
    )


class StorageBinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "storage_binding"

    case_id: Mapped[str | None] = mapped_column(ForeignKey("case.id"), index=True)
    year: Mapped[int | None] = mapped_column(Integer)
    site_legacy_id: Mapped[int | None] = mapped_column(Integer)
    inspection_legacy_code: Mapped[str | None] = mapped_column(String(64))
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    observed_folder_label: Mapped[str | None] = mapped_column(String(512))
    storage_class: Mapped[str] = mapped_column(String(64), nullable=False, default="synology_legacy", server_default="synology_legacy")
    __table_args__ = (
        UniqueConstraint("year", "site_legacy_id", "inspection_legacy_code"),
        CheckConstraint(
            "(year IS NULL AND site_legacy_id IS NULL AND inspection_legacy_code IS NULL) OR "
            "(year IS NOT NULL AND site_legacy_id IS NOT NULL AND inspection_legacy_code IS NOT NULL)",
            name="storage_binding_key_triplet_complete",
        ),
    )


class StorageResolutionLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "storage_resolution_log"

    case_id: Mapped[str | None] = mapped_column(ForeignKey("case.id"), index=True)
    year: Mapped[int | None] = mapped_column(Integer)
    site_legacy_id: Mapped[int | None] = mapped_column(Integer)
    inspection_legacy_code: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[StorageResolutionStatus] = mapped_column(
        Enum(StorageResolutionStatus, name="storage_resolution_status"),
        nullable=False,
        index=True,
    )
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    resolved_relative_path: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)


class RbacRole(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rbac_role"

    role_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class AppUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_user"

    username: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    external_email: Mapped[str | None] = mapped_column(String(255), unique=True)
    external_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class AppUserRole(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_user_role"

    app_user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"), nullable=False, index=True)
    rbac_role_id: Mapped[str] = mapped_column(ForeignKey("rbac_role.id"), nullable=False, index=True)
    __table_args__ = (UniqueConstraint("app_user_id", "rbac_role_id"),)


class RbacPermission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rbac_permission"

    permission_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class RbacRolePermission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rbac_role_permission"

    rbac_role_id: Mapped[str] = mapped_column(ForeignKey("rbac_role.id"), nullable=False, index=True)
    rbac_permission_id: Mapped[str] = mapped_column(ForeignKey("rbac_permission.id"), nullable=False, index=True)
    __table_args__ = (UniqueConstraint("rbac_role_id", "rbac_permission_id"),)


class AuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_event"

    actor_type: Mapped[AuditActorType] = mapped_column(
        Enum(AuditActorType, name="audit_actor_type"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("app_user.id"), index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    changed_fields_json: Mapped[str | None] = mapped_column(Text)
    old_values_json: Mapped[str | None] = mapped_column(Text)
    new_values_json: Mapped[str | None] = mapped_column(Text)
    payload_redacted: Mapped[str | None] = mapped_column(Text)


class MigrationAnomaly(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "migration_anomaly"

    source_sheet: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    legacy_row_id: Mapped[str | None] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    required_field: Mapped[str | None] = mapped_column(String(128))
    raw_fk_value: Mapped[str | None] = mapped_column(String(255))
    override_value: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open", server_default="open")
    detail_json: Mapped[str | None] = mapped_column(Text)


class CurrentProjectionConflict(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "current_projection_conflict"

    projection_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_sheet: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    business_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    classification: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resolution_policy: Mapped[str] = mapped_column(String(64), nullable=False, default="manual_review_required", server_default="manual_review_required")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open", server_default="open")
    detected_on: Mapped[date] = mapped_column(Date, nullable=False)
    adjudicated_on: Mapped[date | None] = mapped_column(Date)
    adjudicated_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("app_user.id"), index=True)
    candidate_legacy_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    adjudication_payload_json: Mapped[str | None] = mapped_column(Text)
    detail_json: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("projection_type", "source_sheet", "business_key", name="uq_current_projection_conflict_open_key"),
    )


class LegacyIdMap(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "legacy_id_map"

    entity_type: Mapped[LegacyEntityType] = mapped_column(
        Enum(LegacyEntityType, name="legacy_id_map_entity_type"),
        nullable=False,
    )
    legacy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_table: Mapped[str] = mapped_column(String(128), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("entity_type", "legacy_id"),)


Index("ix_case_site_state", Case.site_id, Case.state)
Index("ix_certificate_case_type", Certificate.case_id, Certificate.certificate_type)
Index("ix_storage_resolution_lookup", StorageResolutionLog.year, StorageResolutionLog.site_legacy_id, StorageResolutionLog.inspection_legacy_code)
