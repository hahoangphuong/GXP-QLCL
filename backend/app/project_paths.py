from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def artifacts_root() -> Path:
    override = os.environ.get("GXP_ARTIFACTS_ROOT", "").strip()
    if override:
        return Path(override)
    return repo_root() / "artifacts"


def legacy_root() -> Path:
    override = os.environ.get("GXP_LEGACY_ROOT", "").strip()
    if override:
        return Path(override)
    return repo_root() / "legacy"


def phase_artifact_path(*parts: str) -> Path:
    return artifacts_root().joinpath(*parts)


def legacy_path(*parts: str) -> Path:
    return legacy_root().joinpath(*parts)


def frontend_dist_root() -> Path:
    override = os.environ.get("GXP_FRONTEND_DIST_ROOT", "").strip()
    if override:
        return Path(override)
    return repo_root() / "frontend" / "dist"
