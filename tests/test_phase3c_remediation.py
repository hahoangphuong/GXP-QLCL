from tools.phase3c_remediation import canonicalize_snapshot, has_meaningful_payload


def test_has_meaningful_payload_treats_id_only_row_as_placeholder():
    assert has_meaningful_payload({"ID": "257", "ID CƠ SỞ": "", "MÃ DC": "", "GHI CHÚ": ""}) is False
    assert has_meaningful_payload({"ID": "268", "ID CƠ SỞ": "36"}) is True


def test_canonicalize_snapshot_maps_vietnamese_headers_to_importer_keys():
    snapshot = {
        "db.cc": [
            {"ID": "268", "ID ĐỢT KTRA": "257", "ID CƠ SỞ": "36", "LOẠI CC": "GMP"},
        ]
    }
    canonical = canonicalize_snapshot(snapshot)
    row = canonical["db.cc"][0]
    assert row["inspection_case_legacy_id_ref"] == "257"
    assert row["site_legacy_id_ref"] == "36"
    assert row["certificate_type"] == "GMP"
