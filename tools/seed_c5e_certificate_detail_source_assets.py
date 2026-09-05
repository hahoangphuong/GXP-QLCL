from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from io import BytesIO
import os
from pathlib import Path
import sys
import tempfile
from typing import Mapping


# ---------------------------------------------------------------------
# Repo bootstrap
# ---------------------------------------------------------------------

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPO_ROOT),
    )


from backend.app.document.c5e_certificate_detail_source_asset_contract import (  # noqa: E402
    CertificateDetailSourceAsset,
    CertificateDetailSourceAssetContractError,
    resolve_source_asset,
    verify_source_asset_bytes,
)
from backend.app.document.c5e_certificate_detail_source_asset_locator import (  # noqa: E402
    CERTIFICATE_DETAIL_RUNTIME_PREFIX,
    CertificateDetailSourceAssetLocator,
    build_runtime_source_asset_locator,
    build_source_asset_requirement,
    open_verified_source_asset_stream,
)
from backend.app.storage.factory import create_storage_service_from_env  # noqa: E402
from tools.env_utils import parse_env_file  # noqa: E402


SUPPORTED_GXP_TYPES = (
    "GMP",
    "GLP",
    "GSP",
)

RUNTIME_SOURCE_VARIANT = "certificate_9"


class SeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedAsset:
    gxp_type: str
    asset: CertificateDetailSourceAsset
    locator: CertificateDetailSourceAssetLocator
    source_path: Path
    payload: bytes


def _sha256(
    payload: bytes,
) -> str:
    return hashlib.sha256(
        payload
    ).hexdigest()


def _ensure_inside(
    root: Path,
    target: Path,
) -> Path:
    root = root.resolve()
    target = target.resolve()

    try:
        target.relative_to(
            root
        )
    except ValueError as exc:
        raise SeedError(
            "Target escapes template root: "
            f"{target}"
        ) from exc

    return target


def _reject_legacy_target(
    *,
    repo_root: Path,
    template_root: Path,
) -> None:
    """
    legacy/Templates is an audited source tree only.

    Never use it as production template storage.
    """

    legacy_root = (
        repo_root
        / "legacy"
    ).resolve()

    target = (
        template_root
        .resolve()
    )

    try:
        target.relative_to(
            legacy_root
        )
    except ValueError:
        return

    raise SeedError(
        "Refusing to seed C.5e runtime assets into the legacy tree. "
        f"template_root={target}; "
        f"legacy_root={legacy_root}."
    )


def _atomic_write(
    target: Path,
    payload: bytes,
) -> None:
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            dir=target.parent,
        ) as fh:
            temp_path = Path(
                fh.name
            )

            fh.write(
                payload
            )

        os.replace(
            temp_path,
            target,
        )

    except Exception:
        if (
            temp_path is not None
            and temp_path.exists()
        ):
            temp_path.unlink(
                missing_ok=True
            )

        raise


def _prepare_assets(
    *,
    repo_root: Path,
) -> tuple[PreparedAsset, ...]:
    """
    Preflight all three production assets before any write occurs.

    This prevents a bad/missing legacy source from producing a partially
    seeded runtime set.
    """

    repo_root = (
        repo_root
        .resolve()
    )

    legacy_template_root = (
        repo_root
        / "legacy"
        / "Templates"
    )

    if not legacy_template_root.is_dir():
        raise SeedError(
            "Legacy template source directory not found: "
            f"{legacy_template_root}"
        )

    prepared: list[PreparedAsset] = []

    for gxp_type in SUPPORTED_GXP_TYPES:
        try:
            asset = resolve_source_asset(
                source_variant=RUNTIME_SOURCE_VARIANT,
                gxp_type=gxp_type,
            )

        except CertificateDetailSourceAssetContractError as exc:
            raise SeedError(
                str(exc)
            ) from exc

        source_path = (
            legacy_template_root
            / asset.filename
        )

        if not source_path.is_file():
            raise SeedError(
                "Legacy source asset not found: "
                f"{source_path}"
            )

        payload = (
            source_path
            .read_bytes()
        )

        try:
            verify_source_asset_bytes(
                asset,
                payload,
            )

        except CertificateDetailSourceAssetContractError as exc:
            raise SeedError(
                "Legacy source asset failed registry checksum: "
                f"{exc}"
            ) from exc

        locator = (
            build_runtime_source_asset_locator(
                gxp_type=gxp_type,
            )
        )

        if locator.source_variant != RUNTIME_SOURCE_VARIANT:
            raise SeedError(
                "Runtime locator returned unexpected source variant: "
                f"{locator.source_variant!r}."
            )

        if locator.storage_root != "template":
            raise SeedError(
                "Runtime locator returned unexpected storage root: "
                f"{locator.storage_root!r}."
            )

        prepared.append(
            PreparedAsset(
                gxp_type=gxp_type,
                asset=asset,
                locator=locator,
                source_path=source_path,
                payload=payload,
            )
        )

    if len(prepared) != 3:
        raise SeedError(
            "Expected exactly three certificate_9 runtime assets; "
            f"prepared={len(prepared)}."
        )

    return tuple(
        prepared
    )


def _print_preamble(
    *,
    repo_root: Path,
    mode: str,
) -> None:
    print(
        f"REPO_ROOT={repo_root.resolve()}"
    )

    print(
        "SOURCE_ROOT="
        f"{(repo_root / 'legacy' / 'Templates').resolve()}"
    )

    print(
        f"MODE={mode}"
    )

    print(
        "SOURCE_VARIANT=certificate_9"
    )

    print(
        "GXP_TYPES=GMP,GLP,GSP"
    )


def seed_filesystem(
    *,
    repo_root: Path,
    template_root: Path,
) -> None:
    """
    Local/test filesystem mode.

    Production SMB deployments should use seed_runtime_storage().
    """

    repo_root = (
        repo_root
        .resolve()
    )

    template_root = (
        template_root
        .resolve()
    )

    _reject_legacy_target(
        repo_root=repo_root,
        template_root=template_root,
    )

    prepared = _prepare_assets(
        repo_root=repo_root,
    )

    template_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    _print_preamble(
        repo_root=repo_root,
        mode="filesystem",
    )

    print(
        f"TEMPLATE_ROOT={template_root}"
    )

    seeded = 0

    for item in prepared:
        target_path = _ensure_inside(
            template_root,
            (
                template_root
                / item.locator.storage_relative_path
            ),
        )

        _atomic_write(
            target_path,
            item.payload,
        )

        written_payload = (
            target_path
            .read_bytes()
        )

        actual_sha256 = _sha256(
            written_payload
        )

        if actual_sha256 != item.asset.sha256:
            raise SeedError(
                "Seeded source asset checksum mismatch: "
                f"{target_path}; "
                f"expected={item.asset.sha256}; "
                f"actual={actual_sha256}"
            )

        seeded += 1

        print(
            "ASSET="
            f"{item.gxp_type}|"
            f"{item.asset.filename}|"
            f"{item.locator.storage_relative_path}|"
            f"{item.asset.sha256}"
        )

    _print_success(
        seeded=seeded,
        mode="filesystem",
    )


def _load_runtime_env(
    runtime_env_path: Path,
) -> dict[str, str]:
    runtime_env_path = (
        runtime_env_path
        .resolve()
    )

    if not runtime_env_path.is_file():
        raise SeedError(
            "Runtime env file not found: "
            f"{runtime_env_path}"
        )

    try:
        values = parse_env_file(
            runtime_env_path
        )
    except Exception as exc:
        raise SeedError(
            "Failed to parse runtime env file: "
            f"{runtime_env_path}: {exc}"
        ) from exc

    return {
        str(key): str(value)
        for key, value in values.items()
    }


def _validate_runtime_storage_env(
    env: Mapping[str, str],
) -> None:
    storage_class = (
        env.get(
            "STORAGE_CLASS",
            "",
        )
        .strip()
    )

    template_root = (
        env.get(
            "STORAGE_TEMPLATE_ROOT",
            "",
        )
        .strip()
    )

    if storage_class not in {
        "synology_smb",
        "synology_smb_bridge",
    }:
        raise SeedError(
            "Runtime-storage seed requires a Synology SMB storage class; "
            f"got STORAGE_CLASS={storage_class!r}."
        )

    if not template_root:
        raise SeedError(
            "STORAGE_TEMPLATE_ROOT is blank."
        )


def seed_runtime_storage(
    *,
    repo_root: Path,
    runtime_env_path: Path,
) -> None:
    """
    Production seed path.

    Reads runtime configuration with the same env parser used by
    tools/runtime_env.py, creates the application's real StorageService,
    writes through root='template', then re-opens every object through
    the checksum-verifying C.5e runtime locator.
    """

    repo_root = (
        repo_root
        .resolve()
    )

    prepared = _prepare_assets(
        repo_root=repo_root,
    )

    runtime_env = _load_runtime_env(
        runtime_env_path
    )

    _validate_runtime_storage_env(
        runtime_env
    )

    try:
        storage = (
            create_storage_service_from_env(
                runtime_env
            )
        )
    except Exception as exc:
        raise SeedError(
            "Failed to create runtime StorageService: "
            f"{exc}"
        ) from exc

    _print_preamble(
        repo_root=repo_root,
        mode="runtime_storage",
    )

    print(
        "STORAGE_CLASS="
        f"{runtime_env.get('STORAGE_CLASS', '').strip()}"
    )

    print(
        "STORAGE_TEMPLATE_ROOT="
        f"{runtime_env.get('STORAGE_TEMPLATE_ROOT', '').strip()}"
    )

    seeded = 0

    for item in prepared:
        try:
            storage.write_stream(
                item.locator.storage_relative_path,
                BytesIO(
                    item.payload
                ),
                root="template",
            )

        except Exception as exc:
            raise SeedError(
                "Failed to write runtime C.5e source asset: "
                f"{item.locator.storage_relative_path}: {exc}"
            ) from exc

        try:
            requirement = (
                build_source_asset_requirement(
                    item.locator
                )
            )

            with open_verified_source_asset_stream(
                storage,
                requirement,
            ) as stream:
                verified_payload = (
                    stream.read()
                )

        except Exception as exc:
            raise SeedError(
                "Runtime asset post-write verification failed: "
                f"{item.locator.storage_relative_path}: {exc}"
            ) from exc

        actual_sha256 = _sha256(
            verified_payload
        )

        if actual_sha256 != item.asset.sha256:
            raise SeedError(
                "Runtime post-write checksum mismatch: "
                f"{item.locator.storage_relative_path}; "
                f"expected={item.asset.sha256}; "
                f"actual={actual_sha256}"
            )

        seeded += 1

        print(
            "ASSET="
            f"{item.gxp_type}|"
            f"{item.asset.filename}|"
            f"{item.locator.storage_relative_path}|"
            f"{item.asset.sha256}"
        )

    _print_success(
        seeded=seeded,
        mode="runtime_storage",
    )


def _print_success(
    *,
    seeded: int,
    mode: str,
) -> None:
    if seeded != 3:
        raise SeedError(
            "Expected exactly 3 runtime assets; "
            f"seeded={seeded}."
        )

    print(
        "STATUS="
        "C5E_CERTIFICATE_DETAIL_SOURCE_ASSETS_SEEDED"
    )

    print(
        f"MODE={mode}"
    )

    print(
        f"SEEDED={seeded}"
    )

    print(
        f"RUNTIME_PREFIX={CERTIFICATE_DETAIL_RUNTIME_PREFIX}"
    )

    print(
        "APPENDIX_Z3_SEEDED=0"
    )

    print(
        "GDP_SEEDED=0"
    )


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--repo-root",
        default=str(
            REPO_ROOT
        ),
    )

    mode = parser.add_mutually_exclusive_group(
        required=True
    )

    mode.add_argument(
        "--template-root",
        help=(
            "Local/test filesystem template root. "
            "Do not use this mode for production SMB."
        ),
    )

    mode.add_argument(
        "--runtime-env",
        help=(
            "Runtime env file. The tool will instantiate the real "
            "StorageService and seed root='template'."
        ),
    )

    args = (
        parser.parse_args()
    )

    try:
        if args.runtime_env:
            seed_runtime_storage(
                repo_root=Path(
                    args.repo_root
                ),
                runtime_env_path=Path(
                    args.runtime_env
                ),
            )
        else:
            seed_filesystem(
                repo_root=Path(
                    args.repo_root
                ),
                template_root=Path(
                    args.template_root
                ),
            )

    except SeedError as exc:
        print(
            "STATUS="
            "C5E_CERTIFICATE_DETAIL_SOURCE_ASSET_SEED_BLOCKED"
        )

        print(
            f"ERROR={exc}"
        )

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
