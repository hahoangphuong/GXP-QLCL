"""Guard the observed Tencoso series without inventing missing VBA helper semantics."""
import json
from pathlib import Path

import pytest

from backend.app.document.inspection_qd_kt_numbered_bookmark_observation import (
    observe_numbered_bookmarks,
)


FIXTURE = (
    Path(__file__).parent / "fixtures"
    / "inspection_qd_kt_observed_template_binaries.json"
)


def test_four_verified_qdkt_templates_contain_same_tencoso_series():
    observed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert {row["gxp_type"] for row in observed["templates"]} == {"GLP", "GMP", "GMPbb", "GSP"}
    for row in observed["templates"]:
        result = observe_numbered_bookmarks("Tencoso", row["bookmark_names"])
        assert result.numbered_targets == ("Tencoso1", "Tencoso2", "Tencoso3")
        assert result.indices == (1, 2, 3)
        assert result.exact_target_present is False
        assert result.business_owner_verified is False
        assert result.vba_write_semantics_verified is False
        assert result.ready_to_render is False


def test_exact_prefix_only_and_stable_numeric_order():
    result = observe_numbered_bookmarks(
        "Tencoso", ["Tencoso10", "Tencoso2", "TencosoExtra1", "xTencoso3", "Tencoso0", "Tencoso01", "Tencoso1"]
    )
    assert result.numbered_targets == ("Tencoso1", "Tencoso2", "Tencoso10")
    assert result.indices == (1, 2, 10)


def test_gaps_are_observed_not_filled_or_suppressed():
    result = observe_numbered_bookmarks("Tencoso", ["Tencoso1", "Tencoso8"])
    assert result.indices == (1, 8)
    assert result.vba_write_semantics_verified is False


def test_exact_base_is_distinct_from_numbered_members():
    result = observe_numbered_bookmarks("Tencoso", ["Tencoso", "Tencoso1"])
    assert result.exact_target_present is True
    assert result.numbered_targets == ("Tencoso1",)


@pytest.mark.parametrize("names", [
    ["Tencoso1", "Tencoso1"], ["Tencoso1", ""], ["Tencoso1", None],
])
def test_malformed_or_duplicate_physical_inventory_fails_closed(names):
    with pytest.raises(ValueError):
        observe_numbered_bookmarks("Tencoso", names)


def test_logical_base_must_be_explicit():
    with pytest.raises(ValueError):
        observe_numbered_bookmarks("", ["Tencoso1"])
