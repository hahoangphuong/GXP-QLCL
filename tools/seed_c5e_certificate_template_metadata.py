from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from sqlalchemy import select

from tools.env_utils import parse_env_file
from backend.app.config import resolve_database_url
from backend.app.db.enums import DocumentVariantType
from backend.app.db.models.phase1 import TemplateBinding, TemplateDefinition
from backend.app.db.session import build_session_factory
from backend.app.document.c5e_certificate_destination_asset_contract import (
    CERTIFICATE_DETAIL_FAMILY,
    load_certificate_destination_assets,
)
from backend.app.document.seed_contract import build_template_definition_seeds
from backend.app.document.service_contract import load_default_registry
from backend.app.document.template_binary_binding import (
    assign_template_binary_binding,
    get_template_binary_binding_locator,
)
from backend.app.storage.factory import create_storage_service_from_env


class C5ECertificateTemplateMetadataSeedError(RuntimeError):
    pass


def _load_registry_seed():
    entries = tuple(
        entry
        for entry in load_default_registry()
        if entry.family_code == CERTIFICATE_DETAIL_FAMILY
    )
    if len(entries) != 1:
        raise C5ECertificateTemplateMetadataSeedError(
            "Expected exactly one CERTIFICATE_ISSUANCE_WORD registry entry."
        )
    entry = entries[0]
    if entry.source_application != "Word":
        raise C5ECertificateTemplateMetadataSeedError(
            "CERTIFICATE_ISSUANCE_WORD must remain Word-backed."
        )
    if entry.selection_legacy_mode != "moi":
        raise C5ECertificateTemplateMetadataSeedError(
            "CERTIFICATE_ISSUANCE_WORD must retain legacy_mode='moi'."
        )
    if entry.template_pattern != "9. Chung chi {GP} (moi).dotx":
        raise C5ECertificateTemplateMetadataSeedError(
            "CERTIFICATE_ISSUANCE_WORD template pattern drifted from the locked registry contract."
        )
    return entry, build_template_definition_seeds(entries)[0]


def _preflight_assets(storage):
    verified = []
    for asset in load_certificate_destination_assets():
        if not storage.exists(asset.storage_relative_path, root=asset.storage_root):
            raise C5ECertificateTemplateMetadataSeedError(
                f"Destination template is missing for {asset.gxp_type}: {asset.storage_relative_path}"
            )
        with storage.read_stream(asset.storage_relative_path, root=asset.storage_root) as stream:
            payload = stream.read()
        actual = hashlib.sha256(payload).hexdigest()
        if actual != asset.checksum_sha256:
            raise C5ECertificateTemplateMetadataSeedError(
                "Destination template checksum mismatch for "
                f"{asset.gxp_type}: expected={asset.checksum_sha256}, actual={actual}"
            )
        verified.append(asset)
        print(
            "ASSET=",
            asset.gxp_type,
            asset.storage_relative_path,
            actual,
            "PASS",
        )
    return tuple(verified)


def _validate_definition(existing: TemplateDefinition, seed) -> None:
    expected = {
        "family_code": seed.family_code,
        "document_type_code": seed.document_type_code,
        "source_application": seed.source_application,
        "storage_scope": seed.storage_scope,
        "legacy_host_procedure": seed.legacy_host_procedure,
        "legacy_case_number": seed.legacy_case_number,
        "variant_type": DocumentVariantType(seed.variant_type),
        "template_name": seed.template_name,
        "template_pattern": seed.template_pattern,
        "bookmark_contract": seed.bookmark_contract_json,
    }
    mismatches = []
    for field_name, expected_value in expected.items():
        actual_value = getattr(existing, field_name)
        if actual_value != expected_value:
            mismatches.append(
                f"{field_name}: expected={expected_value!r}, actual={actual_value!r}"
            )
    if mismatches:
        raise C5ECertificateTemplateMetadataSeedError(
            "Existing certificate TemplateDefinition conflicts with registry contract: "
            + "; ".join(mismatches)
        )


def _ensure_definition(session, seed) -> tuple[TemplateDefinition, bool]:
    matches = list(
        session.scalars(
            select(TemplateDefinition).where(
                TemplateDefinition.family_code == seed.family_code,
                TemplateDefinition.template_name == seed.template_name,
            )
        )
    )
    if len(matches) > 1:
        raise C5ECertificateTemplateMetadataSeedError(
            "Ambiguous existing certificate TemplateDefinition rows."
        )
    if matches:
        existing = matches[0]
        _validate_definition(existing, seed)
        if not existing.is_active:
            raise C5ECertificateTemplateMetadataSeedError(
                "Existing certificate TemplateDefinition is inactive; refusing implicit reactivation."
            )
        return existing, False

    definition = TemplateDefinition(
        family_code=seed.family_code,
        document_type_code=seed.document_type_code,
        source_application=seed.source_application,
        storage_scope=seed.storage_scope,
        legacy_host_procedure=seed.legacy_host_procedure,
        legacy_case_number=seed.legacy_case_number,
        variant_type=DocumentVariantType(seed.variant_type),
        template_name=seed.template_name,
        template_pattern=seed.template_pattern,
        bookmark_contract=seed.bookmark_contract_json,
        is_active=True,
        notes=seed.notes,
        template_storage_root=None,
        template_storage_relative_path=None,
        template_original_filename=None,
        template_checksum_sha256=None,
    )
    session.add(definition)
    session.flush()
    return definition, True


def _assert_no_generic_binding(session, definition: TemplateDefinition, *, storage_scope: str) -> None:
    generic = list(
        session.scalars(
            select(TemplateBinding).where(
                TemplateBinding.family_code == CERTIFICATE_DETAIL_FAMILY,
                TemplateBinding.template_definition_id == definition.id,
                TemplateBinding.gxp_type == "{GP}",
                TemplateBinding.legacy_mode == "moi",
                TemplateBinding.storage_scope == storage_scope,
                TemplateBinding.is_active.is_(True),
            )
        )
    )
    if generic:
        raise C5ECertificateTemplateMetadataSeedError(
            "Active generic {GP} certificate binding would make exact GMP/GLP binding selection ambiguous."
        )


def _ensure_binding(
    session,
    definition: TemplateDefinition,
    *,
    gxp_type: str,
    storage_scope: str,
) -> tuple[TemplateBinding, bool]:
    matches = list(
        session.scalars(
            select(TemplateBinding).where(
                TemplateBinding.family_code == CERTIFICATE_DETAIL_FAMILY,
                TemplateBinding.template_definition_id == definition.id,
                TemplateBinding.gxp_type == gxp_type,
                TemplateBinding.legacy_mode == "moi",
                TemplateBinding.storage_scope == storage_scope,
            )
        )
    )
    if len(matches) > 1:
        raise C5ECertificateTemplateMetadataSeedError(
            f"Ambiguous existing certificate TemplateBinding rows for {gxp_type}."
        )
    if matches:
        binding = matches[0]
        if not binding.is_active:
            raise C5ECertificateTemplateMetadataSeedError(
                f"Existing certificate TemplateBinding for {gxp_type} is inactive."
            )
        return binding, False

    binding = TemplateBinding(
        family_code=CERTIFICATE_DETAIL_FAMILY,
        template_definition_id=definition.id,
        gxp_type=gxp_type,
        legacy_mode="moi",
        storage_scope=storage_scope,
        is_active=True,
    )
    session.add(binding)
    session.flush()
    return binding, True


def seed(*, runtime_env: Path, dry_run: bool) -> None:
    env = parse_env_file(runtime_env)
    storage = create_storage_service_from_env(env)
    assets = _preflight_assets(storage)
    entry, definition_seed = _load_registry_seed()

    database_url = resolve_database_url(env)
    if database_url.startswith("sqlite:"):
        raise C5ECertificateTemplateMetadataSeedError(
            "Production metadata seeding resolved to SQLite; refusing mutation."
        )

    session_factory = build_session_factory(database_url)
    session = session_factory()
    try:
        existing_definitions = list(
            session.scalars(
                select(TemplateDefinition).where(
                    TemplateDefinition.family_code == CERTIFICATE_DETAIL_FAMILY
                )
            )
        )
        print("EXISTING_DEFINITIONS=", len(existing_definitions))

        if dry_run:
            print("DRY_RUN=1")
            print("WOULD_SEED_DEFINITION=", definition_seed.template_name)
            for asset in assets:
                print(
                    "WOULD_SEED_BINDING=",
                    asset.gxp_type,
                    asset.storage_relative_path,
                    asset.checksum_sha256,
                )
            session.rollback()
            print("STATUS=C5E_CERTIFICATE_TEMPLATE_METADATA_DRY_RUN_PASS")
            return

        definition, definition_created = _ensure_definition(session, definition_seed)
        _assert_no_generic_binding(
            session,
            definition,
            storage_scope=entry.storage_scope,
        )

        created_bindings = 0
        for asset in assets:
            binding, binding_created = _ensure_binding(
                session,
                definition,
                gxp_type=asset.gxp_type,
                storage_scope=entry.storage_scope,
            )
            if binding_created:
                created_bindings += 1

            assign_template_binary_binding(
                session,
                template_binding_id=binding.id,
                storage_root=asset.storage_root,
                storage_relative_path=asset.storage_relative_path,
                original_filename=asset.filename,
                checksum_sha256=asset.checksum_sha256,
            )

            locator = get_template_binary_binding_locator(session, binding.id)
            if locator is None or locator.checksum_sha256 != asset.checksum_sha256:
                raise C5ECertificateTemplateMetadataSeedError(
                    f"Failed to reopen exact binary locator for {asset.gxp_type}."
                )
            print(
                "BOUND=",
                asset.gxp_type,
                binding.id,
                locator.storage_relative_path,
                locator.checksum_sha256,
            )

        session.commit()
        print("DEFINITION_CREATED=", int(definition_created))
        print("BINDINGS_CREATED=", created_bindings)
        print("GSP_BOUND=0")
        print("GDP_BOUND=0")
        print("STATUS=C5E_CERTIFICATE_TEMPLATE_METADATA_SEED_PASS")
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
