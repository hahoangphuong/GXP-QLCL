"""Evidence-independent JSON boundary regressions; no private artifacts."""
import json

import pytest

from backend.app.document.inspection_qd_kt_provenance_gate import (
    QdKtProvenanceGateBlocked, read_provenance_json, semantic_sha256,
)


@pytest.mark.parametrize("raw", [
    b'{"text":"\\ud800"}', b'{"\\udfff":"key"}', b'{"nested":["\\ud800"]}',
    b'{"value":1e10000}', b'{"value":-1e10000}',
], ids=["surrogate-value", "surrogate-key", "surrogate-nested", "positive-overflow", "negative-overflow"])
def test_invalid_utf8_tree_and_overflow_are_rejected_at_parse_owner(tmp_path, raw):
    path = tmp_path / "evidence.json"
    path.write_bytes(raw)
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_SOURCE_PROVENANCE_INCOMPLETE"):
        read_provenance_json(path)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'[]', b'\xff', b'{' + b' ' * (2 * 1024 * 1024)], ids=["duplicate", "nan", "infinity", "array", "bad-utf8", "oversize"])
def test_existing_json_protections_are_preserved(tmp_path, raw):
    path = tmp_path / "evidence.json"
    path.write_bytes(raw)
    with pytest.raises(QdKtProvenanceGateBlocked):
        read_provenance_json(path)


def test_valid_unicode_and_finite_values_keep_exact_semantic_identity(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_bytes(b'{"text":"e\\u0301 \\ud83d\\ude00","number":1.25,"nested":{"ok":true}}')
    value = read_provenance_json(path)
    assert value == {"text": "e\u0301 \U0001f600", "number": 1.25, "nested": {"ok": True}}
    assert semantic_sha256(value) == semantic_sha256(json.loads(path.read_text(encoding="utf-8")))
    assert value["text"] != "\u00e9 \U0001f600"
