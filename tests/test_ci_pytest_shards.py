"""Pure regression for CI backend sharding receipts (no database required)."""
from __future__ import annotations

from collections import Counter

import pytest

from tools.verify_ci_pytest_shards import CiShardError, digest_nodeids, shard_for, verify_shards


HEAD = "a" * 40
SHARDS = 3


def _receipts() -> list[dict]:
    # Use real deterministic assignment; ensure each shard has files.
    ids = [f"tests/test_ci_fixture_{i}.py::test_case[{j}]" for i in range(40) for j in range(2)]
    assert {shard_for(nodeid, SHARDS) for nodeid in ids} == {0, 1, 2}
    digest = digest_nodeids(ids)
    module_counts = dict(sorted(Counter(n.split('::', 1)[0] for n in ids).items()))
    return [
        {
            "schema_version": 1, "head_sha": HEAD, "index": index,
            "count": SHARDS, "total_collected": len(ids),
            "all_nodeids_sha256": digest,
            "all_module_counts": module_counts,
            "selected_nodeids": sorted(n for n in ids if shard_for(n, SHARDS) == index),
        }
        for index in range(SHARDS)
    ]


def test_exact_sharded_collection_receipts_pass():
    report = verify_shards(_receipts(), expected_count=SHARDS, expected_sha=HEAD)
    assert report["collected"] == 80
    assert report["status"] == "BACKEND_PYTEST_SHARDS_PASS"


@pytest.mark.parametrize("tamper", ["missing", "duplicate", "wrong_sha", "missing_id", "extra_id", "wrong_index", "different_collection", "wrong_count", "different_module_count", "unassigned_id"])
def test_corrupt_ci_shard_receipts_are_rejected(tamper):
    receipts = _receipts()
    if tamper == "missing":
        receipts.pop()
    elif tamper == "duplicate":
        receipts[2] = dict(receipts[1])
    elif tamper == "wrong_sha":
        receipts[0]["head_sha"] = "b" * 40
    elif tamper == "missing_id":
        receipts[0]["selected_nodeids"].pop()
    elif tamper == "extra_id":
        receipts[0]["selected_nodeids"].append("tests/test_missing.py::test_does_not_exist")
        receipts[0]["selected_nodeids"].sort()
    elif tamper == "wrong_index":
        receipts[1]["index"] = 4
    elif tamper == "different_collection":
        receipts[2]["all_module_counts"] = dict(receipts[2]["all_module_counts"])
        key = next(iter(receipts[2]["all_module_counts"]))
        receipts[2]["all_module_counts"][key] += 1
    elif tamper == "wrong_count":
        receipts[1]["total_collected"] -= 1
    elif tamper == "different_module_count":
        key = next(iter(receipts[1]["all_module_counts"]))
        receipts[1]["all_module_counts"] = dict(receipts[1]["all_module_counts"])
        receipts[1]["all_module_counts"][key] -= 1
    elif tamper == "unassigned_id":
        receipts[1]["selected_nodeids"].pop()
    with pytest.raises(CiShardError):
        verify_shards(receipts, expected_count=SHARDS, expected_sha=HEAD)


def test_shard_assignment_keeps_parameterized_module_together():
    ids = ["tests/test_workflow.py::test_one", "tests/test_workflow.py::test_two[a]", "tests/test_workflow.py::test_two[b]"]
    assert len({shard_for(nodeid, SHARDS) for nodeid in ids}) == 1


def test_shard_collection_digest_is_order_independent_and_duplicate_averse():
    assert digest_nodeids(["a::t", "b::t"]) == digest_nodeids(["b::t", "a::t"])
    with pytest.raises(ValueError, match="Duplicate"):
        digest_nodeids(["a::t", "a::t"])


def test_runner_variant_nodeids_preserve_identical_module_census():
    receipts = _receipts()
    # Distinct runner-generated parameter IDs are permitted only if module
    # identity and collected test counts remain exactly unchanged.
    target = receipts[1]["selected_nodeids"][0]
    receipts[1]["selected_nodeids"][0] = target + "-runner-specific"
    receipts[1]["selected_nodeids"].sort()
    receipts[1]["all_nodeids_sha256"] = "f" * 64
    assert verify_shards(receipts, expected_count=SHARDS, expected_sha=HEAD)["collected"] == 80
