"""EXPERIMENTAL_ONLY: proposed canonicalization vectors, not a backend contract."""
import pytest
from tools.experiments.change_request_receipt.reference_fingerprint import fingerprint, normalized_unordered_ids


def digest(payload, **overrides):
    args = {'key': b'synthetic-key', 'version': 1, 'actor': 'actor-a', 'site': 'site-a', 'command': 'change-request.create', 'payload': payload}
    args.update(overrides)
    return fingerprint(**args)


def test_mapping_order_is_not_semantic():
    assert digest({'scope': 'a', 'date': '2026-11-04'}) == digest({'date': '2026-11-04', 'scope': 'a'})


def test_omission_and_explicit_null_are_distinct():
    assert digest({}) != digest({'scope': None})


@pytest.mark.parametrize('field,value', [('actor', 'actor-b'), ('site', 'site-b'), ('command', 'other'), ('version', 2)])
def test_binding_and_version_change_digest(field, value):
    assert digest({'scope': 'a'}) != digest({'scope': 'a'}, **{field: value})


def test_expected_version_is_part_of_the_command_when_present():
    assert digest({'expected_version': 1}) != digest({'expected_version': 2})


def test_ordered_list_order_is_significant():
    assert digest({'items': ['a', 'b']}) != digest({'items': ['b', 'a']})


def test_explicitly_unordered_ids_are_sorted_and_duplicates_rejected():
    assert digest({'items': normalized_unordered_ids(['b', 'a'])}) == digest({'items': normalized_unordered_ids(['a', 'b'])})
    with pytest.raises(ValueError):
        normalized_unordered_ids(['a', 'a'])


def test_no_silent_unicode_normalization():
    assert digest({'scope': 'é'}) != digest({'scope': 'e\u0301'})
