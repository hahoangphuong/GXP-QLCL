"""Fail-closed fan-in of disposable pytest shard collection receipts.

The required 'backend' CI job succeeds only if the PostgreSQL gate job,
all shard jobs, and the complete, non-overlapping collection partition pass.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.ci_pytest_shard import digest_nodeids, shard_for


class CiShardError(ValueError):
    """Malformed, incomplete, duplicate, or mismatched shard evidence."""


def verify_shards(receipts: list[dict], *, expected_count: int, expected_sha: str) -> dict:
    if len(receipts) != expected_count or expected_count < 2:
        raise CiShardError("Expected exactly one receipt per configured shard.")
    indices: set[int] = set()
    all_selected: list[str] = []
    total: int | None = None
    collection_digest: str | None = None
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
        if any(shard_for(n, expected_count) != index for n in nodeids):
            raise CiShardError("Node ID assigned to an incorrect shard.")
        shard_total = receipt.get("total_collected")
        if type(shard_total) is not int or shard_total <= 0:
            raise CiShardError("Invalid total collection count.")
        shard_digest = receipt.get("all_nodeids_sha256")
        if not isinstance(shard_digest, str) or len(shard_digest) != 64:
            raise CiShardError("Invalid collection digest.")
        if total is None:
            total, collection_digest = shard_total, shard_digest
        elif total != shard_total or collection_digest != shard_digest:
            raise CiShardError("Different shards collected different test universes.")
        all_selected.extend(nodeids)
    if indices != set(range(expected_count)):
        raise CiShardError("Shard index coverage is incomplete.")
    if len(all_selected) != total or len(all_selected) != len(set(all_selected)):
        raise CiShardError("Collected pytest node IDs are missing or repeated.")
    if digest_nodeids(all_selected) != collection_digest:
        raise CiShardError("Partition does not reconstruct the exact pytest collection.")
    return {"status": "BACKEND_PYTEST_SHARDS_PASS", "shards": expected_count, "collected": total, "head_sha": expected_sha}


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
