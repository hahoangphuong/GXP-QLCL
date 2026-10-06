from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from io import BytesIO
from typing import TYPE_CHECKING, BinaryIO, Iterator

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import TemplateBinding, TemplateDefinition
from backend.app.document.inspection_ke_hoach_kt_template_asset_contract import (
    INSPECTION_KE_HOACH_KT_FAMILY,
    InspectionKeHoachKtTemplateAssetContractError,
    get_inspection_ke_hoach_kt_template_asset,
)
from backend.app.document.inspection_qd_kt_template_asset_contract import (
    INSPECTION_QD_KT_FAMILY,
    InspectionQdKtTemplateAssetContractError,
    get_inspection_qd_kt_template_asset,
)
from backend.app.document.template_binary_binding import (
    TemplateBinaryBindingError,
    get_template_binary_binding_locator,
    normalize_template_binary_relative_path,
)
from backend.app.storage.types import StorageServiceProtocol

if TYPE_CHECKING:
    from backend.app.document.service import AllocatedDocumentGeneration


class TemplateBinaryError(RuntimeError):
    pass


_EXACT_INSPECTION_GXP_ASSET_LOADERS = {
    INSPECTION_QD_KT_FAMILY: (
        get_inspection_qd_kt_template_asset,
        InspectionQdKtTemplateAssetContractError,
    ),
    INSPECTION_KE_HOACH_KT_FAMILY: (
        get_inspection_ke_hoach_kt_template_asset,
        InspectionKeHoachKtTemplateAssetContractError,
    ),
}


@dataclass(frozen=True)
class TemplateBinaryLocator:
    template_definition_id: str
    family_code: str
    template_name: str
    storage_root: str
    storage_relative_path: str
    original_filename: str | None
    checksum_sha256: str | None


@dataclass(frozen=True)
class TemplateBinaryRequirement:
    template_definition_id: str | None
    family_code: str
    template_name: str
    storage_root: str | None
    storage_relative_path: str | None
    original_filename: str | None
    checksum_sha256: str | None
    readiness_status: str
    detail: str


def _load_template_definition(session: Session, template_definition_id: str) -> TemplateDefinition:
    stmt: Select[tuple[TemplateDefinition]] = select(TemplateDefinition).where(TemplateDefinition.id == template_definition_id)
    template_definition = session.execute(stmt).scalar_one_or_none()
    if template_definition is None:
        raise TemplateBinaryError(f"TemplateDefinition {template_definition_id!r} was not found.")
    return template_definition


def _normalize_relative_path(relative_path: str) -> str:
    try:
        return normalize_template_binary_relative_path(relative_path)
    except TemplateBinaryBindingError as exc:
        raise TemplateBinaryError(str(exc)) from exc


def assign_template_binary_locator(
    session: Session,
    *,
    template_definition_id: str,
    storage_root: str,
    storage_relative_path: str,
    original_filename: str | None = None,
    checksum_sha256: str | None = None,
) -> TemplateBinaryLocator:
    if storage_root != "template":
        raise TemplateBinaryError("Template binaries must use storage_root='template'.")
    template_definition = _load_template_definition(session, template_definition_id)
    normalized_path = _normalize_relative_path(storage_relative_path)
    template_definition.template_storage_root = storage_root
    template_definition.template_storage_relative_path = normalized_path
    template_definition.template_original_filename = original_filename
    template_definition.template_checksum_sha256 = checksum_sha256
    session.flush()
    return TemplateBinaryLocator(
        template_definition_id=template_definition.id,
        family_code=template_definition.family_code,
        template_name=template_definition.template_name,
        storage_root=storage_root,
        storage_relative_path=normalized_path,
        original_filename=original_filename,
        checksum_sha256=checksum_sha256,
    )


def get_template_binary_locator(
    session: Session,
    template_definition_id: str,
) -> TemplateBinaryLocator | None:
    template_definition = _load_template_definition(session, template_definition_id)
    if template_definition.template_storage_root is None or template_definition.template_storage_relative_path is None:
        return None
    return TemplateBinaryLocator(
        template_definition_id=template_definition.id,
        family_code=template_definition.family_code,
        template_name=template_definition.template_name,
        storage_root=template_definition.template_storage_root,
        storage_relative_path=template_definition.template_storage_relative_path,
        original_filename=template_definition.template_original_filename,
        checksum_sha256=template_definition.template_checksum_sha256,
    )


def build_template_binary_requirement(
    session: Session,
    allocated: AllocatedDocumentGeneration,
) -> TemplateBinaryRequirement:
    template_definition_id = allocated.prepared.persisted_state.template_definition_id
    if template_definition_id is None:
        return TemplateBinaryRequirement(
            template_definition_id=None,
            family_code=allocated.prepared.generation_plan.template.family_code,
            template_name=allocated.prepared.generation_plan.template.template_pattern,
            storage_root=None,
            storage_relative_path=None,
            original_filename=None,
            checksum_sha256=None,
            readiness_status="missing_template_definition",
            detail="No template_definition row is linked to the prepared generation.",
        )

    template_definition = _load_template_definition(session, template_definition_id)

    requested_gxp_type = getattr(
        getattr(allocated.prepared.generation_plan, "request", None),
        "gxp_type",
        None,
    )
    exact_asset_loader = _EXACT_INSPECTION_GXP_ASSET_LOADERS.get(template_definition.family_code)
    if exact_asset_loader is not None and requested_gxp_type is not None:
        asset_loader, asset_error = exact_asset_loader
        try:
            expected_asset = asset_loader(requested_gxp_type)
        except asset_error as exc:
            return TemplateBinaryRequirement(
                template_definition_id=template_definition.id,
                family_code=template_definition.family_code,
                template_name=template_definition.template_name,
                storage_root=None,
                storage_relative_path=None,
                original_filename=None,
                checksum_sha256=None,
                readiness_status="invalid_template_binding",
                detail=str(exc),
            )

        template_binding_id = allocated.prepared.persisted_state.template_binding_id
        binding = session.get(TemplateBinding, template_binding_id) if template_binding_id else None
        if binding is None or binding.gxp_type != requested_gxp_type:
            return TemplateBinaryRequirement(
                template_definition_id=template_definition.id,
                family_code=template_definition.family_code,
                template_name=template_definition.template_name,
                storage_root=None,
                storage_relative_path=None,
                original_filename=None,
                checksum_sha256=None,
                readiness_status="missing_exact_template_binding",
                detail=(
                    f"{template_definition.family_code} requires an exact GxP TemplateBinding "
                    "with a binary locator; generic TemplateDefinition fallback is not allowed."
                ),
            )
        binding_locator = get_template_binary_binding_locator(session, binding.id)
        if binding_locator is None:
            return TemplateBinaryRequirement(
                template_definition_id=template_definition.id,
                family_code=template_definition.family_code,
                template_name=template_definition.template_name,
                storage_root=None,
                storage_relative_path=None,
                original_filename=None,
                checksum_sha256=None,
                readiness_status="missing_template_locator",
                detail=f"The exact {template_definition.family_code} TemplateBinding has no binary locator.",
            )
        actual_locator = (
            binding_locator.storage_root,
            binding_locator.storage_relative_path,
            binding_locator.original_filename,
            binding_locator.checksum_sha256,
        )
        expected_locator = (
            expected_asset.storage_root,
            expected_asset.storage_relative_path,
            expected_asset.filename,
            expected_asset.checksum_sha256,
        )
        if actual_locator != expected_locator:
            return TemplateBinaryRequirement(
                template_definition_id=template_definition.id,
                family_code=template_definition.family_code,
                template_name=template_definition.template_name,
                storage_root=None,
                storage_relative_path=None,
                original_filename=None,
                checksum_sha256=None,
                readiness_status="invalid_template_binding",
                detail=(
                    f"The exact {template_definition.family_code} TemplateBinding does not match "
                    "the immutable asset contract."
                ),
            )
        return TemplateBinaryRequirement(
            template_definition_id=template_definition.id,
            family_code=template_definition.family_code,
            template_name=template_definition.template_name,
            storage_root=binding_locator.storage_root,
            storage_relative_path=binding_locator.storage_relative_path,
            original_filename=binding_locator.original_filename,
            checksum_sha256=binding_locator.checksum_sha256,
            readiness_status="direct_stream_ready",
            detail=(
                f"{template_definition.family_code} exact GxP TemplateBinding matches the immutable "
                "binary asset contract."
            ),
        )

    template_binding_id = allocated.prepared.persisted_state.template_binding_id
    if template_binding_id is not None:
        binding_locator = get_template_binary_binding_locator(
            session,
            template_binding_id,
        )
        if binding_locator is not None:
            if binding_locator.storage_root != "template":
                return TemplateBinaryRequirement(
                    template_definition_id=template_definition.id,
                    family_code=template_definition.family_code,
                    template_name=template_definition.template_name,
                    storage_root=binding_locator.storage_root,
                    storage_relative_path=binding_locator.storage_relative_path,
                    original_filename=binding_locator.original_filename,
                    checksum_sha256=binding_locator.checksum_sha256,
                    readiness_status="invalid_template_root",
                    detail="TemplateBinding binary locator must use storage_root='template'.",
                )
            return TemplateBinaryRequirement(
                template_definition_id=template_definition.id,
                family_code=template_definition.family_code,
                template_name=template_definition.template_name,
                storage_root=binding_locator.storage_root,
                storage_relative_path=binding_locator.storage_relative_path,
                original_filename=binding_locator.original_filename,
                checksum_sha256=binding_locator.checksum_sha256,
                readiness_status="direct_stream_ready",
                detail="TemplateBinding has an exact binary locator and can be opened through StorageService.",
            )

    if template_definition.template_storage_root is None or template_definition.template_storage_relative_path is None:
        return TemplateBinaryRequirement(
            template_definition_id=template_definition.id,
            family_code=template_definition.family_code,
            template_name=template_definition.template_name,
            storage_root=None,
            storage_relative_path=None,
            original_filename=template_definition.template_original_filename,
            checksum_sha256=template_definition.template_checksum_sha256,
            readiness_status="missing_template_locator",
            detail="Neither the selected TemplateBinding nor TemplateDefinition has an exact template binary locator yet.",
        )
    if template_definition.template_storage_root != "template":
        return TemplateBinaryRequirement(
            template_definition_id=template_definition.id,
            family_code=template_definition.family_code,
            template_name=template_definition.template_name,
            storage_root=template_definition.template_storage_root,
            storage_relative_path=template_definition.template_storage_relative_path,
            original_filename=template_definition.template_original_filename,
            checksum_sha256=template_definition.template_checksum_sha256,
            readiness_status="invalid_template_root",
            detail="TemplateDefinition template binary locator must use storage_root='template'.",
        )
    return TemplateBinaryRequirement(
        template_definition_id=template_definition.id,
        family_code=template_definition.family_code,
        template_name=template_definition.template_name,
        storage_root=template_definition.template_storage_root,
        storage_relative_path=template_definition.template_storage_relative_path,
        original_filename=template_definition.template_original_filename,
        checksum_sha256=template_definition.template_checksum_sha256,
        readiness_status="direct_stream_ready",
        detail="TemplateDefinition has an exact template binary locator and can be opened through StorageService.",
    )


@contextmanager
def open_template_binary_stream(
    storage: StorageServiceProtocol,
    requirement: TemplateBinaryRequirement,
) -> Iterator[BinaryIO]:
    if requirement.readiness_status != "direct_stream_ready":
        raise TemplateBinaryError(f"Template binary is not ready for direct access: {requirement.readiness_status}.")
    if requirement.storage_root is None or requirement.storage_relative_path is None:
        raise TemplateBinaryError("Template binary locator is incomplete.")

    with storage.read_stream(requirement.storage_relative_path, root=requirement.storage_root) as stream:
        payload = stream.read()

    if requirement.checksum_sha256 is not None:
        expected = requirement.checksum_sha256.strip().lower()
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            raise TemplateBinaryError(
                "Template binary checksum mismatch: "
                f"expected={expected}, actual={actual}, path={requirement.storage_relative_path!r}."
            )

    yield BytesIO(payload)
