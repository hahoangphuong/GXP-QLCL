"""Fail-closed fan-in of disposable pytest shard collection receipts.

The required 'backend' CI job succeeds only if the PostgreSQL gate job,
all shard jobs, and the complete, non-overlapping collection partition pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

def shard_for(nodeid: str, count: int) -> int:
    if count < 1:
        raise ValueError("Shard count must be positive.")
    module = nodeid.split("::", 1)[0].replace("\\\\", "/")
    return int.from_bytes(hashlib.sha256(module.encode("utf-8")).digest()[:8], "big") % count


def balance_modules(module_counts: dict[str, int], count: int) -> dict[str, int]:
    """Deterministic longest-module-first bin packing by collected test count.

    Every module and its parameterized tests run on one isolated PostgreSQL
    runner. The independent fan-in verifies the same module census on all
    runners before accepting their partition.
    """
    if type(count) is not int or count < 1:
        raise ValueError("Shard count must be a positive integer.")
    if (
        not isinstance(module_counts, dict)
        or len(module_counts) < count
        or any(
            not isinstance(module, str)
            or not module
            or type(nodes) is not int
            or nodes < 1
            for module, nodes in module_counts.items()
        )
    ):
        raise ValueError("Need at least one valid module per shard.")
    loads = [0] * count
    assignments: dict[str, int] = {}
    for module, nodes in sorted(module_counts.items(), key=lambda item: (-item[1], item[0])):
        index = min(range(count), key=lambda i: (loads[i], i))
        assignments[module] = index
        loads[index] += nodes
    return assignments


def digest_nodeids(nodeids: list[str]) -> str:
    if len(nodeids) != len(set(nodeids)):
        raise ValueError("Duplicate collected pytest node IDs.")
    return hashlib.sha256(json.dumps(sorted(nodeids), ensure_ascii=False).encode("utf-8")).hexdigest()



class CiShardError(ValueError):
    """Malformed, incomplete, duplicate, or mismatched shard evidence."""


def verify_shards(receipts: list[dict], *, expected_count: int, expected_sha: str) -> dict:
    if len(receipts) != expected_count or expected_count < 2:
        raise CiShardError("Expected exactly one receipt per configured shard.")
    indices: set[int] = set()
    all_selected: list[str] = []
    total: int | None = None
    canonical_modules: dict[str, int] | None = None
    for receipt in receipts:
        if type(receipt) is not dict or receipt.get("schema_version") != 1:
            raise CiShardError("Invalid shard receipt schema.")
        if receipt.get("head_sha") != expected_sha:
            raise CiShardError("Shard HEAD does not match the current workflow SHA.")
        index = receipt.get("index")
        count = receipt.get("count")
        if type(index) is not int or type(count) is not int or count != expected_count:
            raise CiShardError("Invalid shard index or count.")
        if index in indices or index < 0 or index >= expected_count:
            raise CiShardError("Missing, repeated, or out-of-range shard index.")
        indices.add(index)
        nodeids = receipt.get("selected_nodeids")
        if not isinstance(nodeids, list) or not nodeids or any(not isinstance(n, str) or not n for n in nodeids):
            raise CiShardError("Each shard must contain collected pytest node IDs.")
        if nodeids != sorted(set(nodeids)):
            raise CiShardError("Shard node IDs must be sorted and unique.")
        shard_total = receipt.get("total_collected")
        if type(shard_total) is not int or shard_total <= 0:
            raise CiShardError("Invalid total collection count.")
        shard_digest = receipt.get("all_nodeids_sha256")
        if not isinstance(shard_digest, str) or len(shard_digest) != 64:
            raise CiShardError("Invalid collection digest.")
        # Parameter IDs can embed runner-dependent repr values. The safe
        # cross-run collection identity is the exact module -> node count
        # census, not a hash of those potentially volatile node IDs.
        modules = receipt.get("all_module_counts")
        if not isinstance(modules, dict) or not modules or any(
            not isinstance(k, str) or not k or type(v) is not int or v <= 0
            for k, v in modules.items()
        ):
            raise CiShardError("Invalid per-module collection census.")
        if sum(modules.values()) != shard_total:
            raise CiShardError("Per-module counts disagree with total collection.")
        if total is None:
            total, canonical_modules = shard_total, modules
        elif total != shard_total or canonical_modules != modules:
            raise CiShardError("Different shards collected different module/test counts.")
        assignments = balance_modules(modules, expected_count)
        if any(assignments.get(nodeid.split("::", 1)[0].replace("\\\\", "/")) != index for nodeid in nodeids):
            raise CiShardError("Node ID assigned to an incorrect shard.")
        own_counts = Counter(nodeid.split("::", 1)[0].replace("\\\\", "/") for nodeid in nodeids)
        expected_own = {
            module: count for module, count in modules.items()
            if assignments[module] == index
        }
        if dict(own_counts) != expected_own:
            raise CiShardError("Shard did not select every collected node from its assigned modules.")
        all_selected.extend(nodeids)
    if indices != set(range(expected_count)):
        raise CiShardError("Shard index coverage is incomplete.")
    if len(all_selected) != total or len(all_selected) != len(set(all_selected)):
        raise CiShardError("Collected pytest node IDs are missing or repeated.")
    selected_counts = Counter(nodeid.split("::", 1)[0].replace("\\\\", "/") for nodeid in all_selected)
    if dict(selected_counts) != canonical_modules:
        raise CiShardError("Shard union does not reconstruct all modules and test counts.")
    return {
        "status": "BACKEND_PYTEST_SHARDS_PASS", "shards": expected_count,
        "collected": total, "modules": len(canonical_modules),
        "shard_node_counts": [sum(n for module, n in canonical_modules.items() if balance_modules(canonical_modules, expected_count)[module] == i) for i in range(expected_count)],
        "head_sha": expected_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    files = sorted(Path(args.directory).glob("backend-shard-*.json"))
    try:
        receipts = [json.loads(path.read_text(encoding="utf-8")) for path in files]
        result = verify_shards(receipts, expected_count=args.expected_count, expected_sha=args.expected_sha)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"STOP: invalid backend shard evidence: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
