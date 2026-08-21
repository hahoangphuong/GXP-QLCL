from tools.export_phase3_anomaly_review_report import build_review_rows, build_snapshot_lookup


def test_build_snapshot_lookup_uses_row_fallback_key_when_id_missing():
    snapshot = {
        "db.ktra": [
            {"ID": "", "__excel_row_number": "42", "ID CƠ SỞ": "", "LOẠI KT": "GMP"},
        ]
    }

    lookup = build_snapshot_lookup(snapshot)

    assert ("db.ktra", "row:42") in lookup


def test_build_review_rows_enriches_anomaly_from_snapshot_context():
    reconciliation = {
        "anomaly_rows": [
            {
                "source_sheet": "db.cc",
                "legacy_row_id": None,
                "source_row_number": 948,
                "source_row_key": "row:948",
                "reason": "missing_site_fk",
                "required_field": "ID CƠ SỞ",
                "raw_fk_value": "",
                "status": "open",
            }
        ]
    }
    snapshot = {
        "db.cc": [
            {
                "ID": "",
                "__excel_row_number": "948",
                "LOẠI CC": "GMP",
                "ID CƠ SỞ": "",
                "TÊN CƠ SỞ": "Cơ sở A",
                "Mã số CC": "ABC",
            }
        ]
    }

    rows = build_review_rows(reconciliation, snapshot)

    assert len(rows) == 1
    assert rows[0]["source_row_key"] == "row:948"
    assert rows[0]["display_label"] == "Chứng chỉ thiếu liên kết"
    assert "Cơ sở A" in rows[0]["review_summary"]
