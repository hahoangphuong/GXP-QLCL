from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from sqlalchemy import select

from backend.app.config import resolve_database_url
from backend.app.db.models.phase1 import TemplateBinding, TemplateDefinition
from backend.app.db.session import build_session_factory
from backend.app.document.inspection_qd_kt_template_asset_contract import (
    INSPECTION_QD_KT_FAMILY,
    InspectionQdKtTemplateAsset,
    load_inspection_qd_kt_template_assets,
)
from backend.app.document.template_binary_binding import (
    TemplateBinaryBindingLocator,
    assign_template_binary_binding,
    get_template_binary_binding_locator,
)
from backend.app.storage.factory import create_storage_service_from_env
from tools.env_utils import parse_env_file


class InspectionQdKtTemplateMetadataSeedError(RuntimeError):
    pass


def _preflight_assets(storage) -> tuple[InspectionQdKtTemplateAsset, ...]:
    verified = []
    for asset in load_inspection_qd_kt_template_assets():
        if not storage.exists(asset.storage_relative_path, root=asset.storage_root):
            raise InspectionQdKtTemplateMetadataSeedError(
                f"Inspection QD KT template is missing for {asset.gxp_type}: {asset.storage_relative_path}"
            )
        with storage.read_stream(asset.storage_relative_path, root=asset.storage_root) as stream:
            actual = hashlib.sha256(stream.read()).hexdigest()
        if actual != asset.checksum_sha256:
            raise InspectionQdKtTemplateMetadataSeedError(
                f"Inspection QD KT template checksum mismatch for {asset.gxp_type}."
            )
        verified.append(asset)
    return tuple(verified)


def _find_definition(session) -> TemplateDefinition:
    matches = list(
        session.scalars(
            select(TemplateDefinition).where(
                TemplateDefinition.family_code == INSPECTION_QD_KT_FAMILY,
                TemplateDefinition.template_name == "2. QD KT - {GP}.dotx",
                TemplateDefinition.is_active.is_(True),
            )
        )
    )
    if len(matches) != 1:
        raise InspectionQdKtTemplateMetadataSeedError(
            "Expected exactly one active INSPECTION_QD_KT TemplateDefinition from the curated metadata seed."
        )
    return matches[0]


def _find_binding(
    session,
    *,
    definition: TemplateDefinition,
    gxp_type: str,
) -> TemplateBinding | None:
    matches = list(
        session.scalars(
            select(TemplateBinding).where(
                TemplateBinding.family_code == INSPECTION_QD_KT_FAMILY,
                TemplateBinding.template_definition_id == definition.id,
                TemplateBinding.gxp_type == gxp_type,
                TemplateBinding.legacy_mode.is_(None),
                TemplateBinding.storage_scope == definition.storage_scope,
            )
        )
    )
    if len(matches) > 1:
        raise InspectionQdKtTemplateMetadataSeedError(
            f"Ambiguous inspection QD KT TemplateBinding rows for {gxp_type}."
        )
    return matches[0] if matches else None


def _validate_locator(
    locator: TemplateBinaryBindingLocator,
    asset: InspectionQdKtTemplateAsset,
) -> None:
    expected = {
        "storage_root": asset.storage_root,
        "storage_relative_path": asset.storage_relative_path,
        "original_filename": asset.filename,
        "checksum_sha256": asset.checksum_sha256,
    }
    mismatches = [
        field_name
        for field_name, expected_value in expected.items()
        if getattr(locator, field_name) != expected_value
    ]
    if mismatches:
        raise InspectionQdKtTemplateMetadataSeedError(
            f"Existing inspection QD KT binary locator conflicts for {asset.gxp_type}: {', '.join(mismatches)}."
        )


def _ensure_binding(
    session,
    *,
    definition: TemplateDefinition,
    asset: InspectionQdKtTemplateAsset,
) -> tuple[TemplateBinding, bool]:
    binding = _find_binding(session, definition=definition, gxp_type=asset.gxp_type)
    if binding is None:
        binding = TemplateBinding(
            family_code=INSPECTION_QD_KT_FAMILY,
            template_definition_id=definition.id,
            gxp_type=asset.gxp_type,
            legacy_mode=None,
            storage_scope=definition.storage_scope,
            is_active=True,
        )
        session.add(binding)
        session.flush()
        return binding, True
    if not binding.is_active:
        raise InspectionQdKtTemplateMetadataSeedError(
            f"Existing inspection QD KT TemplateBinding for {asset.gxp_type} is inactive."
        )
    return binding, False


def seed(*, runtime_env: Path, dry_run: bool) -> None:
    env = parse_env_file(runtime_env)
    assets = _preflight_assets(create_storage_service_from_env(env))
    database_url = resolve_database_url(env)
    if database_url.startswith("sqlite:"):
        raise InspectionQdKtTemplateMetadataSeedError(
            "Inspection QD KT metadata seeding resolved to SQLite; refusing mutation."
        )

    session = build_session_factory(database_url)()
    try:
        definition = _find_definition(session)
        for asset in assets:
            binding = _find_binding(session, definition=definition, gxp_type=asset.gxp_type)
            if binding is not None:
                locator = get_template_binary_binding_locator(session, binding.id)
                if locator is not None:
                    _validate_locator(locator, asset)

        if dry_run:
            session.rollback()
            print("STATUS=INSPECTION_QD_KT_TEMPLATE_METADATA_DRY_RUN_PASS")
            return

        for asset in assets:
            binding, _ = _ensure_binding(session, definition=definition, asset=asset)
            locator = get_template_binary_binding_locator(session, binding.id)
            if locator is None:
                assign_template_binary_binding(
                    session,
                    template_binding_id=binding.id,
                    storage_root=asset.storage_root,
                    storage_relative_path=asset.storage_relative_path,
                    original_filename=asset.filename,
                    checksum_sha256=asset.checksum_sha256,
                )
            else:
                _validate_locator(locator, asset)
        session.commit()
        print("STATUS=INSPECTION_QD_KT_TEMPLATE_METADATA_SEED_PASS")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-env", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    seed(runtime_env=args.runtime_env, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
