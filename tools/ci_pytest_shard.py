"""Deterministic file-level pytest shards for isolated GitHub CI runners.

Enabled only with --ci-shard-index / --ci-shard-count / --ci-shard-manifest.
Each runner collects the complete suite before selecting whole test modules.
Normal local pytest collection/execution is unchanged.
"""
from __future__ import annotations

import json
from collections import Counter
import os
from pathlib import Path

import pytest

from tools.verify_ci_pytest_shards import balance_modules, digest_nodeids


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("gxp-ci-shards")
    group.addoption("--ci-shard-index", type=int, default=None, help="Zero-based CI shard index")
    group.addoption("--ci-shard-count", type=int, default=None, help="Total CI shards")
    group.addoption("--ci-shard-manifest", default=None, help="Shard manifest output path")


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    index = config.getoption("--ci-shard-index")
    count = config.getoption("--ci-shard-count")
    path = config.getoption("--ci-shard-manifest")
    if index is None and count is None and path is None:
        return
    if not isinstance(index, int) or not isinstance(count, int) or not 0 <= index < count:
        raise pytest.UsageError("CI sharding requires 0 <= index < count.")
    if not path or not os.environ.get("GITHUB_SHA"):
        raise pytest.UsageError("CI shard manifest and GITHUB_SHA are mandatory.")
    all_ids = [item.nodeid for item in items]
    if not all_ids or len(all_ids) != len(set(all_ids)):
        raise pytest.UsageError("CI shard collection must be nonempty with unique node IDs.")
    module_counts = dict(sorted(Counter(
        item.nodeid.split("::", 1)[0].replace("\\\\", "/")
        for item in items
    ).items()))
    assignments = balance_modules(module_counts, count)
    selected = [
        item for item in items
        if assignments[item.nodeid.split("::", 1)[0].replace("\\\\", "/")] == index
    ]
    deselected = [
        item for item in items
        if assignments[item.nodeid.split("::", 1)[0].replace("\\\\", "/")] != index
    ]
    if not selected:
        raise pytest.UsageError(f"CI shard {index} is empty.")
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected
    manifest = {
        "schema_version": 1,
        "head_sha": os.environ["GITHUB_SHA"],
        "index": index,
        "count": count,
        "total_collected": len(all_ids),
        "all_nodeids_sha256": digest_nodeids(all_ids),
        "all_module_counts": module_counts,
        "selected_nodeids": sorted(item.nodeid for item in selected),
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"CI_SHARD_SELECTED index={index}/{count} selected={len(selected)} total={len(all_ids)}")
