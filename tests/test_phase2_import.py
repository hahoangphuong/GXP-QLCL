from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate,
    BusinessEligibilityCertificateLink,
    Case,
    Certificate,
    ChangeRequest,
    Company,
    LegacyIdMap,
    MigrationAnomaly,
    Site,
)
from backend.app.domain.phase2_import import import_snapshot, source_row_key


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
            {"ID": "200", "MỚI NHẤT": "-", "ID MỚI NHẤT": "", "LOẠI CC": "GMP", "ID ĐỢT KTRA": "100", "ID CƠ SỞ": "10", "MÃ DC": "A"},
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
            select(MigrationAnomaly).where(MigrationAnomaly.legacy_row_id.is_(None))
        ).one()
        assert anomaly.legacy_row_id is None
        assert '"source_row_key": "row:42"' in (anomaly.detail_json or "")
        assert reconciliation["applied_override_count"] == 1
