from __future__ import annotations

from pathlib import Path

from backend.app.project_paths import artifacts_root


PHASE5_RUNTIME_ARTIFACTS = (
    "phase5/template_registry.curated.json",
    "phase5/payload_builder_registry.json",
    "phase5/template_seed.curated.json",
    "phase5/template_contract_reconciled.json",
    "phase5/dkkd_template_variants.json",
    "phase5/bbtd_template_variants.json",
)


def required_phase5_runtime_artifact_paths(root: Path | None = None) -> tuple[Path, ...]:
    base_root = artifacts_root() if root is None else root
    return tuple(base_root / relative_path for relative_path in PHASE5_RUNTIME_ARTIFACTS)


def assert_required_phase5_runtime_artifacts_exist(root: Path | None = None) -> tuple[Path, ...]:
    required_paths = required_phase5_runtime_artifact_paths(root)
    missing_paths = [path for path in required_paths if not path.is_file()]
    if missing_paths:
        missing_display = ", ".join(path.as_posix() for path in missing_paths)
        raise FileNotFoundError(
            "Missing required Phase 5 runtime artifacts for document runtime: "
            f"{missing_display}"
        )
    return required_paths
