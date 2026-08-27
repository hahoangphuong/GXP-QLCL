import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate,
    BusinessEligibilityCertificateLink,
    Case,
    CaseAssessment,
    Certificate,
    CertificateScope,
    CertificateVersion,
    ChangeApproval,
    ChangeRequest,
    Company,
    InspectionOutcome,
    LegacyIdMap,
    MigrationAnomaly,
    Site,
)
from backend.app.domain.phase2_import import (
    CONFIRMED_BLANKED_ROWS_PATH,
    ConfirmedBlankedResurrectionError,
    ConfirmedBlankedContractError,
    ImportExecutionOptions,
    SchemaLengthValidationError,
    build_schema_length_audit,
    import_snapshot,
    load_confirmed_blanked_contract_rows,
    source_row_key,
)
from backend.app.domain import phase2_import as phase2_import_module


def sample_snapshot():
    return {
        "db.cty": [
            {"ID": "1", "TÊN CÔNG TY": "Company A", "COMPANY NAME": "Company A", "TÊN VIẾT TẮT": "CA", "ĐỊA CHỈ TRỤ SỞ": "Addr A", "LEGAL ADDRESS": "Addr A"},
        ],
        "db.cso": [
            {"ID": "10", "ID Cty": "1", "TÊN CƠ SỞ": "Site A", "SITE NAME": "Site A", "ĐỊA CHỈ CƠ SỞ": "Site Addr", "SITE ADDRESS": "Site Addr", "TỈNH/TP": "HN", "TÊN VIẾT TẮT": "SA"},
        ],
        "db.ktra": [
            {"ID": "100", "LOẠI KT": "GMP", "ID CƠ SỞ": "10", "MÃ DC": "A", "TIÊU CHUẨN ÁP DỤNG": "WHO-GMP", "LOẠI KIỂM TRA": "Tái", "Ngày nộp": "2016-06-17 00:00:00", "Mã hồ sơ": "37/GPs", "Ngày thẩm định": "2016-08-02 00:00:00", "Người thẩm định": "Assessor", "Kết quả": "Đạt", "Ngày K.tra": "26-27/8/2016", "Q. định": "368/QĐ-QLD", "B. bản": "2016-08-27 00:00:00"},
        ],
        "db.cc": [
            {
                "ID": "200",
                "MỚI NHẤT": "-",
                "ID MỚI NHẤT": "",
                "LOẠI CC": "GMP",
                "ID ĐỢT KTRA": "100",
                "ID CƠ SỞ": "10",
                "MÃ DC": "A",
                "Mã số CC": "508/GCN-QLD",
                "Ngày cấp CC": "2016-10-19 00:00:00+00:00",
                "Hết hạn CC": "2019-10-19 00:00:00+00:00",
                "PHẠM VI CHỨNG NHẬN": "* Thuốc viên nén không bao;\n* Thuốc viên nang cứng.",
                "TIÊU CHUẨN ÁP DỤNG": "WHO-GMP",
                "Cơ quan cấp chứng nhận": "Cục Quản lý Dược Việt Nam",
            },
        ],
        "db.dkkd": [
            {"ID": "300", "MỚI NHẤT": "-", "ID MỚI NHẤT": "", "ID CƠ SỞ": "10", "ID CTY": "1", "NGƯỜI CHỊU TRÁCH NHIỆM CHUYÊN MÔN": "Pharmacist", "ID CC": "200"},
        ],
        "db.Tdoi": [
            {"ID": "400", "PHẠM VI": "-", "MÔ TẢ": "Đổi tên", "ID CƠ SỞ": "10", "Ngày nộp": "2016-02-22 00:00:00", "ĐƠN VỊ ĐỀ NGHỊ": "Unit", "Ngày hiệu lực của TĐ": "2016-03-08 00:00:00"},
        ],
        "db.Tdoi2": [
            {"ID": "500", "ID Gốc": "400", "ID Phân loại": "", "PHÂN LOẠI": "Đổi tên", "TÌNH TRẠNG CHẤP NHẬN": "", "THÔNG TIN CŨ": "Old", "THÔNG TIN MỚI": "New", "GHI CHÚ": ""},
        ],
    }


def test_import_snapshot_loads_primary_entities():
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        reconciliation = import_snapshot(session, sample_snapshot())
        session.commit()
        assert session.query(Company).count() == 1
        assert session.query(Site).count() == 1
        assert session.query(Case).count() == 1
        assert session.query(Certificate).count() == 1
        assert session.query(BusinessEligibilityCertificate).count() == 1
        assert session.query(ChangeRequest).count() == 1
        assert reconciliation["mismatches"] == {}


def test_import_snapshot_populates_certificate_version_and_scope_from_legacy_db_cc():
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        reconciliation = import_snapshot(session, sample_snapshot())
        session.commit()

        version = session.scalars(select(CertificateVersion)).one()
        scope = session.scalars(select(CertificateScope)).one()

        assert version.certificate_number == "508/GCN-QLD"
        assert str(version.issue_date) == "2016-10-19"
        assert str(version.expiry_date) == "2019-10-19"
        assert version.applicable_standard == "WHO-GMP"
        assert version.issuing_authority == "Cục Quản lý Dược Việt Nam"
        certificate = session.scalars(select(Certificate)).one()
        assert certificate.line_code == "A"
        assert scope.scope_text == "* Thuốc viên nén không bao;\n* Thuốc viên nang cứng."
        assert scope.language_code == "vi"
        assert scope.sort_order == 0
        assert reconciliation["derived_counts"]["certificate_scope"] == 1


def test_import_snapshot_creates_join_and_legacy_maps():
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, sample_snapshot())
        session.commit()
        assert session.query(BusinessEligibilityCertificateLink).count() == 1
        assert session.query(LegacyIdMap).count() >= 6
        assert session.query(MigrationAnomaly).count() == 0


def test_import_snapshot_applies_remediation_override_and_persists_anomaly():
    snapshot = sample_snapshot()
    snapshot["db.cso"] = [
        {"ID": "10", "ID Cty": "", "TÃŠN CÆ  Sá»ž": "Site A", "SITE NAME": "Site A", "Äá»ŠA CHá»ˆ CÆ  Sá»ž": "Site Addr", "SITE ADDRESS": "Site Addr", "Tá»ˆNH/TP": "HN", "TÃŠN VIáº¾T Táº®T": "SA"},
    ]
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        reconciliation = import_snapshot(
            session,
            snapshot,
            remediation_overrides={"db.cso": {"10": {"company_legacy_id": 1}}},
        )
        session.commit()
        assert session.query(Site).count() == 1
        assert session.query(MigrationAnomaly).count() == 1
        assert reconciliation["applied_override_count"] == 1


def test_import_snapshot_rejects_generic_override_for_confirmed_blanked_row(monkeypatch, tmp_path):
    confirmed_blanked_path = tmp_path / "confirmed_blanked_rows.json"
    confirmed_blanked_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "source_sheet": "db.cso",
                        "source_row_key": "10",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    resurrection_path = tmp_path / "confirmed_blanked_resurrections.json"
    resurrection_path.write_text(json.dumps({"rows": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", confirmed_blanked_path)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", resurrection_path)

    snapshot = sample_snapshot()
    snapshot["db.cso"] = [
        {"ID": "10", "ID Cty": "", "TÊN CƠ SỞ": "Site A", "SITE NAME": "Site A", "ĐỊA CHỈ CƠ SỞ": "Site Addr", "SITE ADDRESS": "Site Addr", "TỈNH/TP": "HN", "TÊN VIẾT TẮT": "SA"},
    ]
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        try:
            import_snapshot(
                session,
                snapshot,
                remediation_overrides={"db.cso": {"10": {"company_legacy_id": 1}}},
            )
        except ConfirmedBlankedResurrectionError as exc:
            assert "db.cso:10" in str(exc)
        else:
            raise AssertionError("Expected confirmed blanked resurrection contract failure")
        assert session.query(Site).count() == 0


def test_confirmed_blanked_contract_missing_fails_closed(monkeypatch, tmp_path):
    missing_path = tmp_path / "missing_confirmed_blanked_rows.json"
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", missing_path)

    try:
        load_confirmed_blanked_contract_rows()
    except ConfirmedBlankedContractError as exc:
        assert "Required owner-approved confirmed-blanked contract is missing" in str(exc)
        assert str(missing_path) in str(exc)
    else:
        raise AssertionError("Expected missing confirmed blanked contract failure")


def test_confirmed_blanked_contract_duplicate_identity_fails_closed(monkeypatch, tmp_path):
    confirmed_blanked_path = tmp_path / "confirmed_blanked_rows.json"
    confirmed_blanked_path.write_text(
        json.dumps(
            {
                "rows": [
                    {"source_sheet": "db.ktra", "source_row_key": "100"},
                    {"source_sheet": "db.ktra", "source_row_key": "100"},
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", confirmed_blanked_path)

    try:
        load_confirmed_blanked_contract_rows()
    except ConfirmedBlankedContractError as exc:
        assert "duplicate identity db.ktra:100" in str(exc)
    else:
        raise AssertionError("Expected duplicate confirmed blanked identity failure")


def test_import_snapshot_accepts_approved_confirmed_blanked_resurrection(monkeypatch, tmp_path):
    confirmed_blanked_path = tmp_path / "confirmed_blanked_rows.json"
    confirmed_blanked_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "source_sheet": "db.cso",
                        "source_row_key": "10",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    resurrection_path = tmp_path / "confirmed_blanked_resurrections.json"
    resurrection_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "source_sheet": "db.cso",
                        "source_row_key": "10",
                        "approved_override": {"company_legacy_id": 1},
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", confirmed_blanked_path)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", resurrection_path)

    snapshot = sample_snapshot()
    snapshot["db.cso"] = [
        {"ID": "10", "ID Cty": "", "TÊN CƠ SỞ": "Site A", "SITE NAME": "Site A", "ĐỊA CHỈ CƠ SỞ": "Site Addr", "SITE ADDRESS": "Site Addr", "TỈNH/TP": "HN", "TÊN VIẾT TẮT": "SA"},
    ]
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        reconciliation = import_snapshot(
            session,
            snapshot,
            remediation_overrides={"db.cso": {"10": {"company_legacy_id": 1}}},
        )
        session.commit()
        assert session.query(Site).count() == 1
        assert session.query(MigrationAnomaly).count() == 1
        assert reconciliation["applied_override_count"] == 1


def test_import_snapshot_rejects_mismatched_confirmed_blanked_resurrection(monkeypatch, tmp_path):
    confirmed_blanked_path = tmp_path / "confirmed_blanked_rows.json"
    confirmed_blanked_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "source_sheet": "db.cso",
                        "source_row_key": "10",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    resurrection_path = tmp_path / "confirmed_blanked_resurrections.json"
    resurrection_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "source_sheet": "db.cso",
                        "source_row_key": "10",
                        "approved_override": {"company_legacy_id": 2},
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", confirmed_blanked_path)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", resurrection_path)

    snapshot = sample_snapshot()
    snapshot["db.cso"] = [
        {"ID": "10", "ID Cty": "", "TÊN CƠ SỞ": "Site A", "SITE NAME": "Site A", "ĐỊA CHỈ CƠ SỞ": "Site Addr", "SITE ADDRESS": "Site Addr", "TỈNH/TP": "HN", "TÊN VIẾT TẮT": "SA"},
    ]
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        try:
            import_snapshot(
                session,
                snapshot,
                remediation_overrides={"db.cso": {"10": {"company_legacy_id": 1}}},
            )
        except ConfirmedBlankedResurrectionError as exc:
            assert "does not match" in str(exc)
        else:
            raise AssertionError("Expected approved resurrection mismatch failure")


def test_import_snapshot_allows_certificate_without_case_when_site_exists():
    snapshot = sample_snapshot()
    snapshot["db.cc"] = [
        {"ID": "200", "Má»šI NHáº¤T": "-", "ID Má»šI NHáº¤T": "", "LOáº I CC": "GMP", "ID Äá»¢T KTRA": "", "ID CÆ  Sá»ž": "10", "MÃƒ DC": "A"},
    ]
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        reconciliation = import_snapshot(session, snapshot)
        session.commit()
        certificate = session.scalars(select(Certificate)).one()
        assert certificate.case_id is None
        assert certificate.issuance_basis == "administrative_no_inspection"
        assert session.query(MigrationAnomaly).count() == 0
        assert reconciliation["skipped_rows"] == {}


def test_import_snapshot_still_skips_certificate_with_unresolved_nonblank_case_fk():
    snapshot = sample_snapshot()
    snapshot["db.cc"] = [
        {"ID": "200", "Má»šI NHáº¤T": "-", "ID Má»šI NHáº¤T": "", "LOáº I CC": "GMP", "ID Äá»¢T KTRA": "999", "ID CÆ  Sá»ž": "10", "MÃƒ DC": "A"},
    ]
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        reconciliation = import_snapshot(session, snapshot)
        session.commit()
        assert session.query(Certificate).count() == 0
        assert session.query(MigrationAnomaly).count() == 1
        assert reconciliation["skipped_rows"]["db.cc"] == 1


def test_source_row_key_falls_back_to_excel_row_when_legacy_id_is_blank():
    assert source_row_key(legacy_row_id=200, source_row_number_value=17) == "200"
    assert source_row_key(legacy_row_id=None, source_row_number_value=17) == "row:17"
    assert source_row_key(legacy_row_id=None, source_row_number_value=None) is None


def test_import_snapshot_accepts_override_for_blank_id_row_via_source_row_key():
    snapshot = sample_snapshot()
    snapshot["db.ktra"] = [
        {
            "ID": "",
            "__excel_row_number": "42",
            "LOẠI KT": "GMP",
            "ID CƠ SỞ": "",
            "MÃ DC": "A",
        }
    ]
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        reconciliation = import_snapshot(
            session,
            snapshot,
            remediation_overrides={"db.ktra": {"row:42": {"site_legacy_id": 10}}},
        )
        session.commit()
        assert session.query(Case).count() == 1
        anomaly = session.scalars(
            select(MigrationAnomaly).where(MigrationAnomaly.source_row_key == "row:42")
        ).one()
        assert anomaly.source_row_key == "row:42"
        assert anomaly.legacy_row_id is None
        assert '"source_row_key": "row:42"' in (anomaly.detail_json or "")
        assert reconciliation["applied_override_count"] == 1


def test_numeric_id_confirmed_blanked_match_excludes_row(monkeypatch, tmp_path):
    confirmed_blanked_path = tmp_path / "confirmed_blanked_rows.json"
    confirmed_blanked_path.write_text(
        json.dumps({"rows": [{"source_sheet": "db.ktra", "source_row_key": "100"}]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", confirmed_blanked_path)

    snapshot = sample_snapshot()
    snapshot["db.ktra"][0]["ID CƠ SỞ"] = ""
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        reconciliation = import_snapshot(session, snapshot)
        session.commit()
        anomaly = session.scalars(select(MigrationAnomaly).where(MigrationAnomaly.source_sheet == "db.ktra")).one()
        detail = json.loads(anomaly.detail_json or "{}")
        assert anomaly.status == "excluded_confirmed_blanked"
        assert detail["is_confirmed_blanked"] is True
        assert detail["confirmed_blank_match_method"] == "source_sheet+source_row_key:numeric_legacy_id"
        assert reconciliation["source_balance"]["db.ktra"]["unresolved_count"] == 0
        assert reconciliation["excluded_rows"]["db.ktra"] == 1


def test_row_fallback_confirmed_blanked_match_excludes_row(monkeypatch, tmp_path):
    confirmed_blanked_path = tmp_path / "confirmed_blanked_rows.json"
    confirmed_blanked_path.write_text(
        json.dumps({"rows": [{"source_sheet": "db.ktra", "source_row_key": "row:42"}]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", confirmed_blanked_path)

    snapshot = sample_snapshot()
    snapshot["db.ktra"] = [
        {
            "ID": "",
            "__excel_row_number": "42",
            "LOẠI KT": "GMP",
            "ID CƠ SỞ": "",
            "MÃ DC": "A",
        }
    ]
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        reconciliation = import_snapshot(session, snapshot)
        session.commit()
        anomaly = session.scalars(select(MigrationAnomaly).where(MigrationAnomaly.source_sheet == "db.ktra")).one()
        detail = json.loads(anomaly.detail_json or "{}")
        assert anomaly.status == "excluded_confirmed_blanked"
        assert detail["is_confirmed_blanked"] is True
        assert detail["confirmed_blank_match_method"] == "source_sheet+source_row_key:excel_row_fallback"
        assert reconciliation["source_balance"]["db.ktra"]["unresolved_count"] == 0
        assert reconciliation["excluded_rows"]["db.ktra"] == 1


def test_confirmed_blanked_survives_same_snapshot_replay(monkeypatch, tmp_path):
    confirmed_blanked_path = tmp_path / "confirmed_blanked_rows.json"
    confirmed_blanked_path.write_text(
        json.dumps({"rows": [{"source_sheet": "db.ktra", "source_row_key": "100"}]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", confirmed_blanked_path)

    snapshot = sample_snapshot()
    snapshot["db.ktra"][0]["ID CƠ SỞ"] = ""
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, snapshot)
        session.commit()
        replay = import_snapshot(
            session,
            snapshot,
            options=ImportExecutionOptions(
                ensure_schema=False,
                reset_existing_data=False,
                allow_existing_records=True,
                persist_audit_event=False,
            ),
        )
        session.commit()
        anomalies = session.scalars(select(MigrationAnomaly).where(MigrationAnomaly.source_sheet == "db.ktra")).all()
        assert len(anomalies) == 1
        assert anomalies[0].status == "excluded_confirmed_blanked"
        assert replay["source_balance"]["db.ktra"]["unresolved_count"] == 0
        assert replay["excluded_rows"]["db.ktra"] == 1


def test_downstream_fk_to_confirmed_blanked_parent_is_classified_as_cascade(monkeypatch, tmp_path):
    confirmed_blanked_path = tmp_path / "confirmed_blanked_rows.json"
    confirmed_blanked_path.write_text(
        json.dumps(
            {
                "rows": [
                    {"source_sheet": "db.ktra", "source_row_key": "100"},
                    {"source_sheet": "db.cc", "source_row_key": "200"},
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", confirmed_blanked_path)

    snapshot = sample_snapshot()
    snapshot["db.ktra"][0]["ID CƠ SỞ"] = ""
    snapshot["db.cc"][0]["ID CƠ SỞ"] = "10"
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        reconciliation = import_snapshot(session, snapshot)
        session.commit()
        certificate_anomaly = session.scalars(
            select(MigrationAnomaly).where(MigrationAnomaly.source_sheet == "db.cc")
        ).one()
        detail = json.loads(certificate_anomaly.detail_json or "{}")
        assert certificate_anomaly.status == "excluded_confirmed_blanked"
        assert detail["classification"] == "cascade_from_confirmed_blanked_parent"
        assert detail["parent_source_sheet"] == "db.ktra"
        assert detail["parent_source_row_key"] == "100"
        assert reconciliation["source_balance"]["db.cc"]["unresolved_count"] == 0


def test_unconfirmed_blank_remains_unresolved(monkeypatch, tmp_path):
    confirmed_blanked_path = tmp_path / "confirmed_blanked_rows.json"
    confirmed_blanked_path.write_text(json.dumps({"rows": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", confirmed_blanked_path)

    snapshot = sample_snapshot()
    snapshot["db.ktra"][0]["ID CƠ SỞ"] = ""
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        reconciliation = import_snapshot(session, snapshot)
        session.commit()
        anomaly = session.scalars(select(MigrationAnomaly).where(MigrationAnomaly.source_sheet == "db.ktra")).one()
        detail = json.loads(anomaly.detail_json or "{}")
        assert anomaly.status == "open"
        assert detail["is_confirmed_blanked"] is False
        assert detail["confirmed_blank_match_method"] is None
        assert reconciliation["source_balance"]["db.ktra"]["unresolved_count"] == 1


def test_import_snapshot_does_not_mutate_confirmed_blanked_contract(monkeypatch, tmp_path):
    confirmed_blanked_path = tmp_path / "confirmed_blanked_rows.json"
    original = json.dumps({"rows": [{"source_sheet": "db.ktra", "source_row_key": "100"}]}, ensure_ascii=False, indent=2)
    confirmed_blanked_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", confirmed_blanked_path)

    snapshot = sample_snapshot()
    snapshot["db.ktra"][0]["ID CƠ SỞ"] = ""
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, snapshot)
        session.commit()
    assert confirmed_blanked_path.read_text(encoding="utf-8") == original


def test_import_snapshot_creates_distinct_anomalies_for_blank_id_rows_with_same_other_fields():
    snapshot = sample_snapshot()
    snapshot["db.ktra"] = [
        {
            "ID": "",
            "__excel_row_number": "10",
            "LOẠI KT": "GMP",
            "ID CƠ SỞ": "999",
            "MÃ DC": "A",
        },
        {
            "ID": "",
            "__excel_row_number": "11",
            "LOẠI KT": "GMP",
            "ID CƠ SỞ": "999",
            "MÃ DC": "B",
        },
    ]
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        reconciliation = import_snapshot(session, snapshot)
        session.commit()
        anomalies = session.scalars(
            select(MigrationAnomaly)
            .where(MigrationAnomaly.source_sheet == "db.ktra")
            .order_by(MigrationAnomaly.source_row_key)
        ).all()
        assert [row.source_row_key for row in anomalies] == ["row:10", "row:11"]
        assert all(row.legacy_row_id is None for row in anomalies)
        assert reconciliation["source_balance"]["db.ktra"]["unresolved_count"] == 2


def test_import_snapshot_same_snapshot_replay_does_not_duplicate_blank_id_anomalies():
    snapshot = sample_snapshot()
    snapshot["db.ktra"] = [
        {
            "ID": "",
            "__excel_row_number": "10",
            "LOẠI KT": "GMP",
            "ID CƠ SỞ": "999",
            "MÃ DC": "A",
        },
        {
            "ID": "",
            "__excel_row_number": "11",
            "LOẠI KT": "GMP",
            "ID CƠ SỞ": "999",
            "MÃ DC": "B",
        },
    ]
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, snapshot)
        session.commit()
        replay = import_snapshot(
            session,
            snapshot,
            options=ImportExecutionOptions(
                ensure_schema=False,
                reset_existing_data=False,
                allow_existing_records=True,
                persist_audit_event=False,
            ),
        )
        session.commit()
        anomalies = session.scalars(
            select(MigrationAnomaly)
            .where(MigrationAnomaly.source_sheet == "db.ktra")
            .order_by(MigrationAnomaly.source_row_key)
        ).all()
        assert [row.source_row_key for row in anomalies] == ["row:10", "row:11"]
        assert replay["source_balance"]["db.ktra"]["unresolved_count"] == 2


def test_import_snapshot_raises_on_same_source_row_key_with_conflicting_anomaly_detail():
    snapshot = sample_snapshot()
    snapshot["db.ktra"] = [
        {
            "ID": "",
            "__excel_row_number": "10",
            "LOẠI KT": "GMP",
            "ID CƠ SỞ": "999",
            "MÃ DC": "A",
        }
    ]
    engine = create_engine("sqlite:///:memory:", future=True)
    from backend.app.db.models import Base
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            MigrationAnomaly(
                source_sheet="db.ktra",
                source_row_key="row:10",
                legacy_row_id=None,
                reason="missing_site_fk",
                required_field="ID Cơ Sở",
                raw_fk_value="999",
                override_value=None,
                status="open",
                detail_json=json.dumps(
                    {
                        "source_sheet": "db.ktra",
                        "source_row_key": "row:10",
                        "source_row_number": 999,
                        "legacy_row_id": None,
                        "reason": "missing_site_fk",
                        "required_field": "ID Cơ Sở",
                        "raw_fk_value": "999",
                        "override_value": None,
                        "status": "open",
                    },
                    ensure_ascii=False,
                ),
            )
        )
        session.commit()
        try:
            import_snapshot(
                session,
                snapshot,
                options=ImportExecutionOptions(
                    ensure_schema=False,
                    reset_existing_data=False,
                    allow_existing_records=True,
                    persist_audit_event=False,
                ),
            )
        except Exception as exc:
            message = str(exc)
            assert "source_sheet='db.ktra'" in message
            assert "source_row_key='row:10'" in message
            assert "reason='missing_site_fk'" in message
        else:
            raise AssertionError("Expected conflicting anomaly detail failure")


def test_import_snapshot_blank_and_numeric_anomaly_identities_do_not_collide():
    snapshot = sample_snapshot()
    snapshot["db.ktra"] = [
        {
            "ID": "100",
            "LOẠI KT": "GMP",
            "ID CƠ SỞ": "999",
            "MÃ DC": "A",
        },
        {
            "ID": "",
            "__excel_row_number": "11",
            "LOẠI KT": "GMP",
            "ID CƠ SỞ": "999",
            "MÃ DC": "B",
        },
    ]
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, snapshot)
        session.commit()
        anomalies = session.scalars(
            select(MigrationAnomaly)
            .where(MigrationAnomaly.source_sheet == "db.ktra")
            .order_by(MigrationAnomaly.source_row_key)
        ).all()
        assert [row.source_row_key for row in anomalies] == ["100", "row:11"]
        assert [row.legacy_row_id for row in anomalies] == ["100", None]


def test_real_snapshot_blank_id_rows_no_longer_false_collide_in_migration_anomaly():
    snapshot = json.loads(Path("artifacts/phase3c/legacy_snapshot.json").read_text(encoding="utf-8"))
    source_rows = snapshot.get("sheets", snapshot)
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        reconciliation = import_snapshot(session, source_rows)
        session.commit()
        anomaly_keys = {
            row["source_row_key"]
            for row in reconciliation["anomaly_rows"]
            if row["source_sheet"] == "db.ktra" and row["status"] == "excluded_confirmed_blanked"
        }
        stored_keys = {
            row[0]
            for row in session.execute(
                select(MigrationAnomaly.source_row_key).where(
                    MigrationAnomaly.source_sheet == "db.ktra",
                    MigrationAnomaly.status == "excluded_confirmed_blanked",
                )
            )
        }
        assert {"row:1162", "row:1169"}.issubset(anomaly_keys)
        assert {"row:1162", "row:1169"}.issubset(stored_keys)


def test_real_snapshot_clean_checkout_contract_excludes_all_confirmed_blanked_rows():
    snapshot = json.loads(Path("artifacts/phase3c/legacy_snapshot.json").read_text(encoding="utf-8"))
    source_rows = snapshot.get("sheets", snapshot)
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        reconciliation = import_snapshot(session, source_rows)
        session.commit()
        assert reconciliation["excluded_rows"] == {
            "db.cso": 3,
            "db.ktra": 47,
            "db.cc": 27,
            "db.dkkd": 50,
            "db.Tdoi": 22,
            "db.Tdoi2": 2,
        }
        assert {
            sheet: balance["unresolved_count"]
            for sheet, balance in reconciliation["source_balance"].items()
            if balance["unresolved_count"]
        } == {}


def test_import_snapshot_preserves_long_unicode_assessment_narratives_without_truncation():
    snapshot = sample_snapshot()
    long_result = (
        "Đây là nhận xét chuyên môn rất dài. " * 12
        + "Kết luận cuối cùng vẫn phải được giữ nguyên từng ký tự tiếng Việt."
    )
    snapshot["db.ktra"][0]["Kết quả"] = long_result
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, snapshot)
        session.commit()
        assessment = session.scalars(select(CaseAssessment)).one()
        outcome = session.scalars(select(InspectionOutcome)).one()
        assert assessment.assessment_result == long_result
        assert outcome.outcome_result == long_result


def test_import_snapshot_preserves_long_change_result_narratives_without_truncation():
    snapshot = sample_snapshot()
    long_result = "Biên bản thay đổi " + ("chi tiết; " * 40)
    snapshot["db.Tdoi"][0]["Kết quả"] = long_result
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, snapshot)
        session.commit()
        approval = session.scalars(select(ChangeApproval)).one()
        assert approval.result_label == long_result


def test_schema_length_preflight_detects_all_bounded_field_violations_and_ignores_text_fields():
    snapshot = sample_snapshot()
    snapshot["db.ktra"][0]["Mã hồ sơ"] = "D" * 129
    snapshot["db.Tdoi2"][0]["PHÂN LOẠI"] = "P" * 260
    snapshot["db.ktra"][0]["Kết quả"] = "Nội dung dài " * 80
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        try:
            import_snapshot(session, snapshot)
        except SchemaLengthValidationError as exc:
            targets = {violation.target for violation in exc.violations}
            assert "case_application.dossier_code" in targets
            assert "change_request_detail.classification_label" in targets
            assert "case_assessment.assessment_result" not in targets
            assert "inspection_outcome.outcome_result" not in targets
        else:
            raise AssertionError("Expected schema length preflight failure")


def test_build_schema_length_audit_for_real_snapshot_has_no_remaining_bounded_overflow():
    snapshot = json.loads(Path("artifacts/phase3c/legacy_snapshot.json").read_text(encoding="utf-8"))
    audit_rows = build_schema_length_audit(snapshot)

    assert len(audit_rows) == 34
    assert [row["target"] for row in audit_rows if row["rows_exceeding_limit"] > 0] == []
