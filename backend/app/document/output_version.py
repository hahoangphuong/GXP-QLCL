from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import TYPE_CHECKING

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from backend.app.db.enums import DocumentGenerationStatus
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate,
    Case,
    DocumentGenerationRun,
    DocumentVariant,
    DocumentVersion,
    Site,
)
from backend.app.storage.binding_service import StorageBindingService
from backend.app.db.models.phase1 import StorageBinding
from backend.app.storage.local import LocalStorageService

if TYPE_CHECKING:
    from backend.app.document.service import PreparedDocumentGeneration


class OutputVersionAllocationError(RuntimeError):
    pass


@dataclass(frozen=True)
class OutputVersionAllocation:
    document_id: str
    document_variant_id: str
    document_version_id: str
    generation_run_id: str
    version_no: int
    storage_root: str
    storage_relative_path: str
    original_filename: str
    storage_binding_id: str | None


def _normalize_filename(filename: str) -> str:
    normalized = str(filename or "").strip().replace("\\", "/")
    if not normalized or "/" in normalized:
        raise OutputVersionAllocationError("Output filename must be a single file name without path separators.")
    if normalized in {".", ".."}:
        raise OutputVersionAllocationError("Output filename is invalid.")
    return normalized


def _load_generation_run(session: Session, generation_run_id: str) -> DocumentGenerationRun:
    stmt: Select[tuple[DocumentGenerationRun]] = select(DocumentGenerationRun).where(
        DocumentGenerationRun.id == generation_run_id
    )
    generation_run = session.execute(stmt).scalar_one_or_none()
    if generation_run is None:
        raise OutputVersionAllocationError(f"DocumentGenerationRun {generation_run_id!r} was not found.")
    return generation_run


def _lock_generation_run_for_output_allocation(
    session: Session,
    generation_run_id: str,
) -> DocumentGenerationRun:
    stmt: Select[tuple[DocumentGenerationRun]] = (
        select(DocumentGenerationRun)
        .where(DocumentGenerationRun.id == generation_run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    generation_run = session.execute(stmt).scalar_one_or_none()
    if generation_run is None:
        raise OutputVersionAllocationError(
            f"DocumentGenerationRun {generation_run_id!r} was not found during output allocation."
        )
    return generation_run


def _load_case_storage_identity(session: Session, case_id: str) -> tuple[int, int, str]:
    stmt: Select[tuple[Case, Site]] = (
        select(Case, Site)
        .join(Site, Site.id == Case.site_id)
        .where(Case.id == case_id)
    )
    row = session.execute(stmt).one_or_none()
    if row is None:
        raise OutputVersionAllocationError(f"Case {case_id!r} was not found.")
    case, site = row
    if case.opened_year is None or site.legacy_site_id is None or case.legacy_inspection_code is None:
        raise OutputVersionAllocationError("Case is missing year/site/code values required for inspection folder resolution.")
    return case.opened_year, site.legacy_site_id, case.legacy_inspection_code


def _load_dkkd_storage_identity(session: Session, business_eligibility_certificate_id: str) -> int:
    stmt: Select[tuple[BusinessEligibilityCertificate, Site]] = (
        select(BusinessEligibilityCertificate, Site)
        .join(Site, Site.id == BusinessEligibilityCertificate.site_id)
        .where(BusinessEligibilityCertificate.id == business_eligibility_certificate_id)
    )
    row = session.execute(stmt).one_or_none()
    if row is None:
        raise OutputVersionAllocationError(
            f"BusinessEligibilityCertificate {business_eligibility_certificate_id!r} was not found."
        )
    _, site = row
    if site.legacy_site_id is None:
        raise OutputVersionAllocationError(
            "Business eligibility certificate is missing site legacy ID required for DDKD folder resolution."
        )
    return site.legacy_site_id


def _resolve_output_binding(
    session: Session,
    storage: LocalStorageService,
    prepared: PreparedDocumentGeneration,
) -> tuple[str, str, StorageBinding | None]:
    scope = prepared.generation_plan.template.storage_scope
    request = prepared.generation_plan.request
    if scope == "inspection_folder":
        if request.case_id is None:
            raise OutputVersionAllocationError("Inspection-folder output allocation requires case_id.")
        year, site_legacy_id, inspection_legacy_code = _load_case_storage_identity(session, request.case_id)
        result = StorageBindingService(storage).resolve_inspection_folder(
            session,
            case_id=request.case_id,
            year=year,
            site_legacy_id=site_legacy_id,
            inspection_legacy_code=inspection_legacy_code,
        )
        if result.resolution.status.value != "resolved" or result.binding is None:
            raise OutputVersionAllocationError(
                f"Inspection folder resolution failed for output allocation: {result.resolution.status.value}."
            )
        return "inspection", result.binding.relative_path, result.binding
    if scope == "dkkd_folder":
        if request.business_eligibility_certificate_id is None:
            raise OutputVersionAllocationError("DDKD-folder output allocation requires business_eligibility_certificate_id.")
        site_legacy_id = _load_dkkd_storage_identity(session, request.business_eligibility_certificate_id)
        resolution = storage.resolve_dkkd_folder(
            case_id=None,
            site_legacy_id=site_legacy_id,
        )
        if resolution.status.value != "resolved" or resolution.relative_path is None:
            raise OutputVersionAllocationError(
                f"DDKD folder resolution failed for output allocation: {resolution.status.value}."
            )
        return "dkkd", resolution.relative_path, None
    raise OutputVersionAllocationError(
        f"Output allocation for storage_scope={scope!r} is not implemented yet; fail closed."
    )


def _resolve_reused_output_identity(
    session: Session,
    storage: LocalStorageService,
    prepared: PreparedDocumentGeneration,
) -> tuple[str, str, str | None]:
    scope = prepared.generation_plan.template.storage_scope
    request = prepared.generation_plan.request
    if scope == "inspection_folder":
        if request.case_id is None:
            raise OutputVersionAllocationError("Inspection-folder output allocation requires case_id.")
        year, site_legacy_id, inspection_legacy_code = _load_case_storage_identity(session, request.case_id)
        stmt: Select[tuple[StorageBinding]] = select(StorageBinding).where(
            StorageBinding.year == year,
            StorageBinding.site_legacy_id == site_legacy_id,
            StorageBinding.inspection_legacy_code == inspection_legacy_code,
        )
        binding = session.execute(stmt).scalar_one_or_none()
        if binding is not None and storage.exists(binding.relative_path):
            return "inspection", binding.relative_path, binding.id
        resolution = storage.resolve_inspection_folder(
            case_id=request.case_id,
            year=year,
            site_legacy_id=site_legacy_id,
            inspection_legacy_code=inspection_legacy_code,
        )
        if resolution.status.value != "resolved" or resolution.relative_path is None:
            raise OutputVersionAllocationError(
                f"Inspection folder resolution failed for reused output allocation: {resolution.status.value}."
            )
        return (
            "inspection",
            resolution.relative_path,
            None if binding is None else binding.id,
        )
    if scope == "dkkd_folder":
        if request.business_eligibility_certificate_id is None:
            raise OutputVersionAllocationError("DDKD-folder output allocation requires business_eligibility_certificate_id.")
        site_legacy_id = _load_dkkd_storage_identity(session, request.business_eligibility_certificate_id)
        resolution = storage.resolve_dkkd_folder(
            case_id=None,
            site_legacy_id=site_legacy_id,
        )
        if resolution.status.value != "resolved" or resolution.relative_path is None:
            raise OutputVersionAllocationError(
                f"DDKD folder resolution failed for reused output allocation: {resolution.status.value}."
            )
        return "dkkd", resolution.relative_path, None
    raise OutputVersionAllocationError(
        f"Output allocation for storage_scope={scope!r} is not implemented yet; fail closed."
    )


def _next_version_no(session: Session, document_variant_id: str) -> int:
    stmt = select(func.max(DocumentVersion.version_no)).where(DocumentVersion.document_variant_id == document_variant_id)
    current = session.execute(stmt).scalar_one()
    return int(current or 0) + 1


def _existing_output_allocation(
    session: Session,
    generation_run: DocumentGenerationRun,
) -> OutputVersionAllocation | None:
    if generation_run.output_document_version_id is None:
        return None
    stmt: Select[tuple[DocumentVersion]] = select(DocumentVersion).where(
        DocumentVersion.id == generation_run.output_document_version_id
    )
    document_version = session.execute(stmt).scalar_one_or_none()
    if document_version is None:
        raise OutputVersionAllocationError(
            f"Generation run {generation_run.id!r} references missing output_document_version_id."
        )
    if (
        document_version.storage_root is None
        or document_version.storage_relative_path is None
        or document_version.original_filename is None
    ):
        raise OutputVersionAllocationError(
            f"Generation run {generation_run.id!r} references incomplete output document version locator."
        )
    return OutputVersionAllocation(
        document_id=generation_run.document_id,
        document_variant_id=document_version.document_variant_id,
        document_version_id=document_version.id,
        generation_run_id=generation_run.id,
        version_no=document_version.version_no,
        storage_root=document_version.storage_root,
        storage_relative_path=document_version.storage_relative_path,
        original_filename=document_version.original_filename,
        storage_binding_id=document_version.storage_binding_id,
    )


def _load_document_variant_for_output_version(
    session: Session,
    document_variant_id: str,
) -> DocumentVariant:
    stmt: Select[tuple[DocumentVariant]] = select(DocumentVariant).where(
        DocumentVariant.id == document_variant_id
    )
    variant = session.execute(stmt).scalar_one_or_none()
    if variant is None:
        raise OutputVersionAllocationError(
            f"DocumentVariant {document_variant_id!r} was not found during output allocation."
        )
    return variant


def _assert_output_allocation_lineage_identity(
    generation_run: DocumentGenerationRun,
    variant: DocumentVariant,
    prepared: PreparedDocumentGeneration,
) -> None:
    persisted_state = prepared.persisted_state
    comparisons = (
        (
            "generation_run.document_id",
            generation_run.document_id,
            persisted_state.document_id,
        ),
        (
            "document_variant.id",
            variant.id,
            persisted_state.document_variant_id,
        ),
        (
            "document_variant.document_id",
            variant.document_id,
            persisted_state.document_id,
        ),
    )
    mismatches = [
        f"{label}={persisted!r}->{requested!r}"
        for label, persisted, requested in comparisons
        if persisted != requested
    ]
    if mismatches:
        raise OutputVersionAllocationError(
            "Output allocation lineage identity mismatch: "
            + ", ".join(mismatches)
            + "."
        )


def allocate_output_document_version(
    session: Session,
    storage: LocalStorageService,
    prepared: PreparedDocumentGeneration,
    *,
    output_filename: str,
) -> OutputVersionAllocation:
    filename = _normalize_filename(output_filename)
    generation_run = _lock_generation_run_for_output_allocation(
        session,
        prepared.persisted_state.generation_run_id,
    )
    existing = _existing_output_allocation(session, generation_run)
    if existing is not None:
        variant = _load_document_variant_for_output_version(
            session,
            existing.document_variant_id,
        )
        _assert_output_allocation_lineage_identity(
            generation_run,
            variant,
            prepared,
        )
        storage_root, folder_relative_path, binding_id = _resolve_reused_output_identity(
            session,
            storage,
            prepared,
        )
        storage_relative_path = f"{folder_relative_path}/{filename}"
        mismatches: list[str] = []
        if existing.original_filename != filename:
            mismatches.append(
                f"filename={existing.original_filename!r}->{filename!r}"
            )
        if existing.storage_root != storage_root:
            mismatches.append(
                f"storage_root={existing.storage_root!r}->{storage_root!r}"
            )
        if existing.storage_binding_id != binding_id:
            mismatches.append(
                "storage_binding_id="
                f"{existing.storage_binding_id!r}->{binding_id!r}"
            )
        if existing.storage_relative_path != storage_relative_path:
            mismatches.append(
                "storage_relative_path="
                f"{existing.storage_relative_path!r}->{storage_relative_path!r}"
            )
        if mismatches:
            raise OutputVersionAllocationError(
                "Generation run output allocation is already bound to a different "
                "output identity: " + ", ".join(mismatches) + "."
            )
        return existing
    variant = _lock_document_variant_for_output_version(
        session,
        prepared.persisted_state.document_variant_id,
    )
    _assert_output_allocation_lineage_identity(
        generation_run,
        variant,
        prepared,
    )
    storage_root, folder_relative_path, binding = _resolve_output_binding(
        session,
        storage,
        prepared,
    )
    storage_relative_path = f"{folder_relative_path}/{filename}"
    if storage.exists(storage_relative_path, root=storage_root):
        raise OutputVersionAllocationError(
            f"Output path already exists and will not be overwritten automatically: {storage_relative_path!r}"
        )
    document_version = DocumentVersion(
        document_variant_id=prepared.persisted_state.document_variant_id,
        version_no=_next_version_no(session, prepared.persisted_state.document_variant_id),
        storage_binding_id=binding.id if binding is not None else None,
        storage_root=storage_root,
        storage_relative_path=storage_relative_path,
        original_filename=filename,
        checksum_sha256=None,
        is_current=False,
        issued_on=None,
    )
    session.add(document_version)
    session.flush()
    generation_run.output_document_version_id = document_version.id
    session.flush()
    return OutputVersionAllocation(
        document_id=prepared.persisted_state.document_id,
        document_variant_id=prepared.persisted_state.document_variant_id,
        document_version_id=document_version.id,
        generation_run_id=generation_run.id,
        version_no=document_version.version_no,
        storage_root=storage_root,
        storage_relative_path=storage_relative_path,
        original_filename=filename,
        storage_binding_id=binding.id if binding is not None else None,
    )


def _assert_finalization_allocation_identity(
    generation_run: DocumentGenerationRun,
    document_version: DocumentVersion,
    variant: DocumentVariant,
    allocation: OutputVersionAllocation,
) -> None:
    mismatches: list[str] = []

    comparisons = (
        ("generation_run.document_id", generation_run.document_id, allocation.document_id),
        (
            "generation_run.output_document_version_id",
            generation_run.output_document_version_id,
            allocation.document_version_id,
        ),
        ("document_variant.id", variant.id, allocation.document_variant_id),
        ("document_variant.document_id", variant.document_id, allocation.document_id),
        (
            "document_version.document_variant_id",
            document_version.document_variant_id,
            allocation.document_variant_id,
        ),
        ("document_version.version_no", document_version.version_no, allocation.version_no),
        (
            "document_version.storage_binding_id",
            document_version.storage_binding_id,
            allocation.storage_binding_id,
        ),
        ("document_version.storage_root", document_version.storage_root, allocation.storage_root),
        (
            "document_version.storage_relative_path",
            document_version.storage_relative_path,
            allocation.storage_relative_path,
        ),
        (
            "document_version.original_filename",
            document_version.original_filename,
            allocation.original_filename,
        ),
    )
    for label, persisted, requested in comparisons:
        if persisted != requested:
            mismatches.append(f"{label}={persisted!r}->{requested!r}")

    if mismatches:
        raise OutputVersionAllocationError(
            "Output finalization allocation identity mismatch: "
            + ", ".join(mismatches)
            + "."
        )


def _assert_generation_run_finalizable(
    generation_run: DocumentGenerationRun,
) -> None:
    if generation_run.status != DocumentGenerationStatus.PENDING:
        raise OutputVersionAllocationError(
            "Document generation run cannot be finalized from status "
            f"{generation_run.status.value!r}; expected 'pending'."
        )


def _assert_finalization_targets_latest_version(
    session: Session,
    document_version: DocumentVersion,
) -> None:
    latest_version_no = session.execute(
        select(func.max(DocumentVersion.version_no)).where(
            DocumentVersion.document_variant_id
            == document_version.document_variant_id
        )
    ).scalar_one()
    if latest_version_no is None or document_version.version_no != int(latest_version_no):
        raise OutputVersionAllocationError(
            "Allocated document version is not the latest persisted version for its variant; "
            f"allocated version_no={document_version.version_no!r}, "
            f"latest version_no={latest_version_no!r}."
        )


def _assert_single_current_version_before_finalization(
    session: Session,
    document_variant_id: str,
) -> None:
    stmt = (
        select(DocumentVersion.id)
        .where(
            DocumentVersion.document_variant_id == document_variant_id,
            DocumentVersion.is_current.is_(True),
        )
        .limit(2)
    )
    current_ids = tuple(session.scalars(stmt))
    if len(current_ids) > 1:
        raise OutputVersionAllocationError(
            "Document variant has multiple current versions before output finalization."
        )


def _lock_document_variant_for_output_version(
    session: Session,
    document_variant_id: str,
) -> DocumentVariant:
    stmt: Select[tuple[DocumentVariant]] = (
        select(DocumentVariant)
        .where(DocumentVariant.id == document_variant_id)
        .with_for_update()
    )
    variant = session.execute(stmt).scalar_one_or_none()
    if variant is None:
        raise OutputVersionAllocationError(
            f"DocumentVariant {document_variant_id!r} was not found during output version mutation."
        )
    return variant


def finalize_output_document_version_write(
    session: Session,
    storage: LocalStorageService,
    allocation: OutputVersionAllocation,
    *,
    binary_payload: bytes,
    issued_on: datetime | None = None,
) -> str:
    generation_run = _load_generation_run(session, allocation.generation_run_id)
    _assert_generation_run_finalizable(generation_run)
    stmt: Select[tuple[DocumentVersion]] = select(DocumentVersion).where(
        DocumentVersion.id == allocation.document_version_id
    )
    document_version = session.execute(stmt).scalar_one_or_none()
    if document_version is None:
        raise OutputVersionAllocationError(f"Allocated DocumentVersion {allocation.document_version_id!r} was not found.")
    variant = _lock_document_variant_for_output_version(
        session,
        document_version.document_variant_id,
    )
    _assert_finalization_allocation_identity(
        generation_run,
        document_version,
        variant,
        allocation,
    )
    _assert_single_current_version_before_finalization(
        session,
        document_version.document_variant_id,
    )
    _assert_finalization_targets_latest_version(
        session,
        document_version,
    )
    storage.write_stream(
        allocation.storage_relative_path,
        BytesIO(binary_payload),
        root=allocation.storage_root,
        overwrite=False,
    )
    checksum = storage.checksum(
        allocation.storage_relative_path,
        root=allocation.storage_root,
    )
    session.execute(
        update(DocumentVersion)
        .where(
            DocumentVersion.document_variant_id == allocation.document_variant_id,
            DocumentVersion.id != allocation.document_version_id,
        )
        .values(is_current=False)
    )
    document_version.checksum_sha256 = checksum
    document_version.is_current = True
    document_version.issued_on = issued_on or datetime.now(timezone.utc)
    generation_run.status = DocumentGenerationStatus.SUCCEEDED
    generation_run.error_summary = None
    session.flush()
    return checksum
