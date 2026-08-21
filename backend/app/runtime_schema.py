from __future__ import annotations

import re
from pathlib import Path

from backend.app.project_paths import repo_root


REVISION_PATTERN = re.compile(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
DOWN_REVISION_PATTERN = re.compile(r"^down_revision\s*=\s*(['\"]([^'\"]+)['\"]|None)", re.MULTILINE)


def expected_alembic_head_revision() -> str | None:
    versions_dir = repo_root() / "migrations" / "versions"
    if not versions_dir.exists():
        return None

    revisions: dict[str, str | None] = {}
    referenced_down_revisions: set[str] = set()
    for path in versions_dir.glob("*.py"):
        content = path.read_text(encoding="utf-8")
        revision_match = REVISION_PATTERN.search(content)
        down_revision_match = DOWN_REVISION_PATTERN.search(content)
        if revision_match is None:
            continue
        revision = revision_match.group(1)
        down_revision = None
        if down_revision_match is not None and down_revision_match.group(1) != "None":
            down_revision = down_revision_match.group(2)
        revisions[revision] = down_revision
        if down_revision is not None:
            referenced_down_revisions.add(down_revision)

    heads = sorted(set(revisions) - referenced_down_revisions)
    if len(heads) != 1:
        return None
    return heads[0]
