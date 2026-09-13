from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TOOL = (
    ROOT
    / "tools"
    / "audit_c5e_certificate_detail_taxonomy_bookmark_coverage.py"
)


def _load_tool():
    spec = (
        importlib.util.spec_from_file_location(
            "c5e_taxonomy_bookmark_gate",
            TOOL,
        )
    )

    assert spec is not None
    assert spec.loader is not None

    module = (
        importlib.util.module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        module
    )

    return module


def test_key2bookmark_exact_legacy_contract():
    module = _load_tool()

    assert module.key2bookmark(
        "1"
    ) == "L1"

    assert module.key2bookmark(
        " 1. "
    ) == "L1"

    assert module.key2bookmark(
        "1.1"
    ) == "L1_1"

    assert module.key2bookmark(
        "6.1"
    ) == "L6_1"

    assert module.key2bookmark(
        "6.2"
    ) == "L6_2"


def test_key2bookmark_removes_only_one_final_period():
    module = _load_tool()

    assert module.key2bookmark(
        "1.."
    ) == "L1_"