from __future__ import annotations

from enum import Enum


class CaseState(str, Enum):
    DRAFT = "draft"
    APPLICATION_RECEIVED = "application_received"
    UNDER_ASSESSMENT = "under_assessment"
    PLANNED = "planned"
    DECISION_ISSUED = "decision_issued"
    INSPECTION_IN_PROGRESS = "inspection_in_progress"
    INSPECTION_COMPLETED = "inspection_completed"
    AWAITING_CERTIFICATE_DECISION = "awaiting_certificate_decision"
    CERTIFIED = "certified"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class ChangeRequestState(str, Enum):
    RECEIVED = "received"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EFFECTIVE = "effective"
    SUPERSEDED = "superseded"


class DocumentVariantType(str, Enum):
    EDITABLE_DOCX = "editable_docx"
    EDITABLE_XLSX = "editable_xlsx"
    GENERATED_PDF = "generated_pdf"
    SCANNED_PDF = "scanned_pdf"
    SIGNED_PDF = "signed_pdf"
    PRESENTATION_SOURCE = "presentation_source"


class DocumentGenerationStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StorageResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"


class LegacyEntityType(str, Enum):
    COMPANY = "company"
    SITE = "site"
    CASE = "case"
    CERTIFICATE = "certificate"
    BUSINESS_ELIGIBILITY = "business_eligibility"
    CHANGE_REQUEST = "change_request"
    DOCUMENT = "document"


class InspectionEventType(str, Enum):
    APPLICATION_SUBMITTED = "application_submitted"
    ASSESSMENT_COMPLETED = "assessment_completed"
    PLAN_CREATED = "plan_created"
    DECISION_ISSUED = "decision_issued"
    INSPECTION_EXECUTED = "inspection_executed"
    OUTCOME_RECORDED = "outcome_recorded"
    CERTIFICATE_ISSUED = "certificate_issued"


class AuditActorType(str, Enum):
    USER = "user"
    SYSTEM = "system"
    MIGRATION = "migration"
