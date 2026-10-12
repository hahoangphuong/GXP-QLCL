import json
from pathlib import Path

import pytest

from sqlalchemy import create_engine, event, func, inspect, select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate,
    BusinessEligibilityCertificateLink,
    BusinessEligibilityVersion,
    Case,
    CaseAssessment,
    Certificate,
    CertificateScope,
    CertificateVersion,
    ChangeApproval,
    ChangeRequest,
    Company,
    EvaluationScopeTaxonomyNode,
    InspectionOutcome,
    InspectionPeriodSegment,
    LegacyIdMap,
    MigrationAnomaly,
    Site,
)
from backend.app.domain.phase2_import import (
    CONFIRMED_BLANKED_ROWS_PATH,
    CertificateCaseSourceIntegrityError,
    ConfirmedBlankedResurrectionError,
    ConfirmedBlankedContractError,
    ImportCollisionError,
    ImportExecutionOptions,
    SchemaLengthValidationError,
    build_schema_length_audit,
    import_snapshot,
    load_confirmed_blanked_contract_rows,
    parse_legacy_inspection_period,
    source_row_key,
)
from backend.app.domain import phase2_import as phase2_import_module



def test_evaluation_scope_taxonomy_seed_avoids_uuid_returning_sentinel_path():
    engine = create_engine("sqlite:///:memory:", future=True)
    taxonomy_insert_statements: list[tuple[str, bool]] = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture_taxonomy_insert(conn, cursor, statement, parameters, context, executemany):
        if "INSERT INTO evaluation_scope_taxonomy_node" in statement:
            taxonomy_insert_statements.append((statement, executemany))

    with Session(engine) as session:
        phase2_import_module.create_schema(session)
        artifact, version = phase2_import_module._load_evaluation_scope_taxonomy(session)
        expected_count = sum(
            len(definition["rows"])
            for definition in artifact["named_ranges"].values()
        )
        expected_parent_count = sum(
            1
            for definition in artifact["named_ranges"].values()
            for row in definition["rows"]
            if "." in row["key"]
        )
        actual_count = session.scalar(
            select(func.count())
            .select_from(EvaluationScopeTaxonomyNode)
            .where(EvaluationScopeTaxonomyNode.taxonomy_version_id == version.id)
        )
        actual_parent_count = session.scalar(
            select(func.count())
            .select_from(EvaluationScopeTaxonomyNode)
            .where(
                EvaluationScopeTaxonomyNode.taxonomy_version_id == version.id,
                EvaluationScopeTaxonomyNode.parent_node_id.is_not(None),
            )
        )

    assert actual_count == expected_count
    assert actual_parent_count == expected_parent_count
    assert taxonomy_insert_statements
    assert any(executemany for _, executemany in taxonomy_insert_statements)
    assert all(
        "RETURNING" not in statement.upper()
        for statement, _ in taxonomy_insert_statements
    )

def sample_snapshot():
    return {
        "db.cty": [
            {"ID": "1", "TÊN CÔNG TY": "Company A", "COMPANY NAME": "Company A", "TÊN VIẾT TẮT": "CA", "ĐỊA CHỈ TRỤ SỞ": "Addr A", "LEGAL ADDRESS": "Addr A"},
        ],
        "db.cso": [
            {
                "ID": "10",
                "ID Cty": "1",
                "TÊN CƠ SỞ": "Site A",
                "SITE NAME": "Site A",
                "ĐỊA CHỈ CƠ SỞ": "Site Addr",
                "SITE ADDRESS": "Site Addr",
                "TỈNH/TP": "HN",
                "TÊN VIẾT TẮT": "SA",
                "Chuyên viên phụ trách": "Hà Hoàng Phương",
                "DOANH NGHIỆP NƯỚC NGOÀI": "Nhật Bản",
                "LIÊN HỆ": "QA: 0903 000 000",
                "NGƯỜI ĐỨNG ĐẦU CƠ SỞ": "Lãnh đạo Site",
                "NGƯỜI CHỊU TRÁCH NHIỆM CHUYÊN MÔN": "Pharmacist Site",
                "NGƯỜI PHỤ TRÁCH QA": "Manager QA",
                "NGỪNG HOẠT ĐỘNG": "Tạm ngừng một phần",
            },
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
            {
                "ID": "300",
                "MỚI NHẤT": "-",
                "ID MỚI NHẤT": "",
                "ID CƠ SỞ": "10",
                "ID CTY": "1",
                "Mã số CC": "126/DKKDD-BYT",
                "Ngày cấp CC": "2018-10-31 00:00:00+00:00",
                "Số QĐ cấp": "6580/QĐ-BYT",
                "LẦN CẤP": "2",
                "LỊCH SỬ CẤP": "Cấp lần 1: 122/BYT-ĐKKDD ngày 01/9/2015",
                "NGƯỜI CHỊU TRÁCH NHIỆM CHUYÊN MÔN": "Pharmacist",
                "NGƯỜI PHỤ TRÁCH QA": "Manager QA DDKD",
                "TRÌNH ĐỘ CHUYÊN MÔN": "Dược sĩ đại học",
                "CHỨNG CHỈ HÀNH NGHỀ": "3344/CCHN-D-SYT-HCM",
                "NGÀY CẤP CCHN": "2018-08-10 00:00:00+00:00",
                "NƠI CẤP CCHN": "Sở Y tế thành phố Hồ Chí Minh",
                "NGÀY CẤP CCHN - PTCM": "2013-08-16 00:00:00+00:00",
                "NƠI CẤP CCHN - PTCM": "Sở Y tế Thành phố Hồ Chí Minh",
                "HOẠT ĐỘNG KINH DOANH": "Sản xuất thuốc, nguyên liệu làm thuốc",
                "NGƯỜI XỬ LÝ": "Hà Hoàng Phương",
                "NGỪNG HOẠT ĐỘNG": "chứng chỉ còn hiệu lực",
                "HỒ SƠ ĐỀ NGHỊ CẤP/ĐIỀU CHỈNH": "51/OTS-RA ngày 19/12/2024",
                "THAY THẾ GIẤY ID": "299",
                "BỊ THAY THẾ BỞI GIẤY ID": "301",
                "ID CC": "200",
            },
        ],
        "db.Tdoi": [
            {"ID": "400", "PHẠM VI": "-", "MÔ TẢ": "Đổi tên", "ID CƠ SỞ": "10", "Ngày nộp": "2016-02-22 00:00:00", "ĐƠN VỊ ĐỀ NGHỊ": "Unit", "Ngày hiệu lực của TĐ": "2016-03-08 00:00:00"},
        ],
        "db.Tdoi2": [
            {"ID": "500", "ID Gốc": "400", "ID Phân loại": "", "PHÂN LOẠI": "Đổi tên", "TÌNH TRẠNG CHẤP NHẬN": "", "THÔNG TIN CŨ": "Old", "THÔNG TIN MỚI": "New", "GHI CHÚ": ""},
        ],
    }


@pytest.mark.parametrize(
    ("raw_id", "expected"),
    [
        ("100", 100),
        ("100.0", 100),
        (" 00100.000 ", 100),
        ("0", 0),
        ("100.5", None),
        ("1e2", None),
        ("-100", None),
        ("100abc", None),
    ],
)
def test_legacy_identifier_parser_refuses_nonintegral_or_inferred_values(raw_id, expected):
    assert phase2_import_module.parse_int(raw_id) == expected


@pytest.mark.parametrize(
    ("case_reference", "site_reference", "missing_fk"),
    [
        ("100.5", "10", "missing_case_fk"),
        ("1e2", "10", "missing_case_fk"),
        ("100", "10.5", "missing_site_fk"),
    ],
)
def test_default_import_does_not_link_truncated_fractional_source_fk(
    case_reference, site_reference, missing_fk
):
    snapshot = sample_snapshot()
    snapshot["db.cc"][0]["ID ĐỢT KTRA"] = case_reference
    snapshot["db.cc"][0]["ID CƠ SỞ"] = site_reference
    source_before = json.loads(json.dumps(snapshot))
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        report = import_snapshot(session, snapshot)
        assert session.scalar(select(func.count()).select_from(Certificate)) == 0
        assert report["skipped_rows"]["db.cc"] == 1
        assert report["skipped_row_samples"]["db.cc"][0]["reason"] == missing_fk
    assert snapshot == source_before


@pytest.mark.parametrize(
    "source_sheet",
    ["db.cty", "db.cso", "db.ktra", "db.cc", "db.dkkd", "db.Tdoi", "db.Tdoi2"],
)
def test_import_rejects_nonintegral_explicit_source_id_before_schema(source_sheet):
    snapshot = sample_snapshot()
    snapshot[source_sheet][0]["ID"] = "100.5"
    source_before = json.loads(json.dumps(snapshot))
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(
        ImportCollisionError, match="Invalid legacy ID"
    ):
        import_snapshot(session, snapshot)
    assert inspect(engine).has_table("company") is False
    assert inspect(engine).has_table("certificate") is False
    assert snapshot == source_before


@pytest.mark.parametrize(
    ("case_site", "case_gxp", "case_reference", "expected_classification"),
    [
        ("11", "GMP", "100", "SITE_MISMATCH"),
        ("10", "GLP", "100", "GXP_MISMATCH"),
        ("11", "GLP", "100", "SITE_AND_GXP_MISMATCH"),
        ("10", "GMP", "999", "CASE_SOURCE_NOT_FOUND"),
        ("10", "GMP", "ambiguous", "UNPARSEABLE_CASE_REFERENCE"),
        ("", "GMP", "100", "SITE_CONTEXT_INCOMPLETE"),
    ],
)
def test_strict_certificate_source_integrity_rejects_before_database_mutation(
    case_site, case_gxp, case_reference, expected_classification
):
    snapshot = sample_snapshot()
    snapshot["db.ktra"][0]["ID CƠ SỞ"] = case_site
    snapshot["db.ktra"][0]["LOẠI KT"] = case_gxp
    snapshot["db.cc"][0]["ID ĐỢT KTRA"] = case_reference

    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(CertificateCaseSourceIntegrityError) as exc:
        import_snapshot(
            session, snapshot,
            options=ImportExecutionOptions(strict_certificate_case_source_links=True),
        )

    report = exc.value.report
    assert [item["classification"] for item in report["effective_anomalies"]] == [expected_classification]
    assert report["database_mutated"] is False
    assert inspect(engine).has_table("certificate") is False
    assert inspect(engine).has_table("site") is False


def test_strict_certificate_source_integrity_allows_valid_and_administrative_link():
    for case_reference, expected_case_link in (("100", True), ("", False)):
        snapshot = sample_snapshot()
        snapshot["db.cc"][0]["ID ĐỢT KTRA"] = case_reference
        engine = create_engine("sqlite:///:memory:", future=True)
        with Session(engine) as session:
            import_snapshot(
                session, snapshot,
                options=ImportExecutionOptions(strict_certificate_case_source_links=True),
            )
            certificate = session.scalars(select(Certificate)).one()
            assert (certificate.case_id is not None) is expected_case_link


def test_strict_preflight_duplicate_certificate_identity_is_rejected_before_schema_creation():
    # The standalone source audit must match this existing importer invariant.
    snapshot = sample_snapshot()
    snapshot["db.cc"].append(dict(snapshot["db.cc"][0]))
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(
        ImportCollisionError, match="Duplicate source row key"
    ):
        import_snapshot(
            session, snapshot,
            options=ImportExecutionOptions(strict_certificate_case_source_links=True),
        )
    assert inspect(engine).has_table("certificate") is False
    assert inspect(engine).has_table("site") is False


@pytest.mark.parametrize("parent_sheet", ["db.cty", "db.cso", "db.ktra"])
def test_import_rejects_duplicate_parent_source_identity_before_schema_creation(parent_sheet):
    # Standalone --strict audit now mirrors this all-sheet importer invariant.
    snapshot = sample_snapshot()
    snapshot["db.cc"][0]["ID ĐỢT KTRA"] = ""  # Administrative; no Case link to audit.
    snapshot[parent_sheet].append(dict(snapshot[parent_sheet][0]))
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(
        ImportCollisionError, match="Duplicate source row key"
    ):
        import_snapshot(
            session, snapshot,
            options=ImportExecutionOptions(strict_certificate_case_source_links=True),
        )
    assert inspect(engine).has_table("certificate") is False
    assert inspect(engine).has_table("site") is False


@pytest.mark.parametrize("orphan_kind", ["matching_case_and_certificate_site", "administrative_certificate_site"])
def test_strict_preflight_rejects_non_materializable_parent_before_schema_creation(orphan_kind):
    snapshot = sample_snapshot()
    if orphan_kind == "matching_case_and_certificate_site":
        # Raw Certificate/Case Site values agree, but neither Site parent exists.
        snapshot["db.ktra"][0]["ID CƠ SỞ"] = "999"
        snapshot["db.cc"][0]["ID CƠ SỞ"] = "999"
        expected = {"CERTIFICATE_SITE_PARENT_NOT_IMPORTABLE", "LINKED_CASE_PARENT_NOT_IMPORTABLE"}
    else:
        # A blank Case reference is permitted, but an orphan Site is not.
        snapshot["db.cc"][0]["ID ĐỢT KTRA"] = ""
        snapshot["db.cso"][0]["ID Cty"] = "999"
        expected = {"CERTIFICATE_SITE_PARENT_NOT_IMPORTABLE"}

    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(CertificateCaseSourceIntegrityError) as exc:
        import_snapshot(
            session, snapshot,
            options=ImportExecutionOptions(strict_certificate_case_source_links=True),
        )
    assert exc.value.report["effective_anomalies"] == []
    parent_anomalies = exc.value.report["effective_parent_anomalies"]
    assert {item["classification"] for item in parent_anomalies} == expected
    assert "0 unresolved Certificate-Case link(s)" in str(exc.value)
    assert f"{len(parent_anomalies)} unimportable source-parent" in str(exc.value)
    assert inspect(engine).has_table("certificate") is False
    assert inspect(engine).has_table("site") is False


def test_real_legacy_snapshot_strict_preflight_rejects_only_effective_conflicts():
    snapshot = json.loads(Path("artifacts/phase3c/legacy_snapshot.json").read_text(encoding="utf-8"))
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(CertificateCaseSourceIntegrityError) as exc:
        import_snapshot(
            session, snapshot.get("sheets", snapshot),
            options=ImportExecutionOptions(strict_certificate_case_source_links=True),
        )
    report = exc.value.report
    assert report["effective_certificate_source_rows"] == 1601
    assert report["effective_classification_counts"] == {
        "ADMINISTRATIVE_NO_CASE_REFERENCE": 143,
        "EXACT_SOURCE_CONTEXT": 1455,
        "SITE_MISMATCH": 3,
    }
    assert [row["certificate_legacy_id"] for row in report["effective_anomalies"]] == [
        376, 1037, 1180
    ]
    assert inspect(engine).has_table("certificate") is False


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
        outcome = session.scalars(select(InspectionOutcome)).one()
        assert outcome.inspected_on.isoformat() == "2016-08-26"
        assert outcome.inspected_to_on.isoformat() == "2016-08-27"
        assert reconciliation["mismatches"] == {}


def test_legacy_inspection_period_parser_is_deterministic_and_fail_closed():
    assert parse_legacy_inspection_period("20/10/2011") is not None
    assert tuple(value.isoformat() for value in parse_legacy_inspection_period("20/10/2011")) == ("2011-10-20", "2011-10-20")
    assert tuple(value.isoformat() for value in parse_legacy_inspection_period("20-21/10/2011")) == ("2011-10-20", "2011-10-21")
    assert tuple(value.isoformat() for value in parse_legacy_inspection_period("31/07-01/08/2009")) == ("2009-07-31", "2009-08-01")
    assert tuple(value.isoformat() for value in parse_legacy_inspection_period("1-12/12/2017")) == ("2017-12-01", "2017-12-12")
    assert parse_legacy_inspection_period("01/01/2020, 02/01/2020") is None


def test_import_snapshot_never_uses_bbkt_as_inspection_period_fallback():
    snapshot = sample_snapshot()
    snapshot["db.ktra"][0]["Ngày K.tra"] = ""
    snapshot["db.ktra"][0]["B. bản"] = "2016-08-27 00:00:00"
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, snapshot)
        outcome = session.scalars(select(InspectionOutcome)).one()
        assert outcome.inspected_on is None
        assert outcome.inspected_to_on is None


def test_import_snapshot_projects_canonical_inspection_folder_code_from_legacy_identity():
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, sample_snapshot())
        session.commit()

        case = session.scalars(select(Case)).one()

    assert case.legacy_inspection_id == 100
    assert case.legacy_inspection_code == "KT-100-GMP"


def test_import_snapshot_projects_gmpbb_and_glp_inspection_folder_codes_without_fabricating_unknown_type():
    snapshot = sample_snapshot()
    snapshot["db.ktra"] = [
        {**snapshot["db.ktra"][0], "ID": "101", "LOẠI KT": " GMPbb "},
        {**snapshot["db.ktra"][0], "ID": "102", "LOẠI KT": "GLP"},
        {**snapshot["db.ktra"][0], "ID": "103", "LOẠI KT": "UNKNOWN"},
    ]
    snapshot["db.cc"] = []
    snapshot["db.dkkd"] = []
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, snapshot)
        session.commit()
        cases = {case.legacy_inspection_id: case for case in session.scalars(select(Case))}

    assert cases[101].legacy_inspection_code == "KT-101-GMPbb"
    assert cases[102].legacy_inspection_code == "KT-102-GLP"
    assert cases[103].legacy_inspection_code is None


def test_import_snapshot_populates_general_info_owner_fields_from_legacy_db_cso():
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, sample_snapshot())
        session.commit()

        company = session.scalars(select(Company)).one()
        site = session.scalars(select(Site)).one()

        assert company.assigned_specialist_text == "Hà Hoàng Phương"
        assert site.foreign_investment_text == "Nhật Bản"
        assert site.contact_information == "QA: 0903 000 000"
        assert site.facility_leader_name == "Lãnh đạo Site"
        assert site.professional_responsible_person_name == "Pharmacist Site"
        assert site.quality_assurance_person_name == "Manager QA"
        assert site.current_status_text == "Tạm ngừng một phần"


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


def test_import_snapshot_leaves_general_info_owner_fields_null_when_legacy_source_is_blank():
    snapshot = sample_snapshot()
    snapshot["db.cso"][0]["Chuyên viên phụ trách"] = ""
    snapshot["db.cso"][0]["DOANH NGHIỆP NƯỚC NGOÀI"] = ""
    snapshot["db.cso"][0]["LIÊN HỆ"] = ""
    snapshot["db.cso"][0]["NGƯỜI ĐỨNG ĐẦU CƠ SỞ"] = ""
    snapshot["db.cso"][0]["NGƯỜI CHỊU TRÁCH NHIỆM CHUYÊN MÔN"] = ""
    snapshot["db.cso"][0]["NGƯỜI PHỤ TRÁCH QA"] = ""
    snapshot["db.cso"][0]["NGỪNG HOẠT ĐỘNG"] = ""
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, snapshot)
        session.commit()

        company = session.scalars(select(Company)).one()
        site = session.scalars(select(Site)).one()

        assert company.assigned_specialist_text is None
        assert site.foreign_investment_text is None
        assert site.contact_information is None
        assert site.facility_leader_name is None
        assert site.professional_responsible_person_name is None
        assert site.quality_assurance_person_name is None
        assert site.current_status_text is None


def test_import_snapshot_populates_business_eligibility_detail_owner_fields_from_legacy_db_dkkd():
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, sample_snapshot())
        session.commit()

        certificate = session.scalars(select(BusinessEligibilityCertificate)).one()
        version = session.scalars(select(BusinessEligibilityVersion)).one()

        assert certificate.legacy_dkkd_id == 300
        assert certificate.replaces_legacy_dkkd_id == 299
        assert certificate.replaced_by_legacy_dkkd_id == 301
        assert version.certificate_number == "126/DKKDD-BYT"
        assert str(version.issued_on) == "2018-10-31"
        assert version.decision_reference == "6580/QĐ-BYT"
        assert version.issuance_sequence_text == "2"
        assert version.issuance_history_text == "Cấp lần 1: 122/BYT-ĐKKDD ngày 01/9/2015"
        assert version.quality_assurance_person_name == "Manager QA DDKD"
        assert version.professional_qualification_text == "Dược sĩ đại học"
        assert version.professional_license_number == "3344/CCHN-D-SYT-HCM"
        assert str(version.professional_license_issued_on) == "2018-08-10"
        assert version.professional_license_issuer == "Sở Y tế thành phố Hồ Chí Minh"
        assert str(version.responsible_license_issued_on) == "2013-08-16"
        assert version.responsible_license_issuer == "Sở Y tế Thành phố Hồ Chí Minh"
        assert version.business_activity_text == "Sản xuất thuốc, nguyên liệu làm thuốc"
        assert version.current_status_text is None
        assert version.handled_by_name == "Hà Hoàng Phương"
        assert version.application_dossier_reference == "51/OTS-RA ngày 19/12/2024"


def test_import_snapshot_keeps_ngung_hoat_dong_owned_by_site_only_not_business_eligibility():
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, sample_snapshot())
        session.commit()

        site = session.scalars(select(Site)).one()
        version = session.scalars(select(BusinessEligibilityVersion)).one()

        assert site.current_status_text == "Tạm ngừng một phần"
        assert version.current_status_text is None


def test_import_snapshot_fails_closed_when_company_assigned_specialist_conflicts_across_sites():
    snapshot = sample_snapshot()
    snapshot["db.cso"].append(
        {
            "ID": "11",
            "ID Cty": "1",
            "TÊN CƠ SỞ": "Site B",
            "SITE NAME": "Site B",
            "ĐỊA CHỈ CƠ SỞ": "Site Addr B",
            "SITE ADDRESS": "Site Addr B",
            "TỈNH/TP": "HCM",
            "TÊN VIẾT TẮT": "SB",
            "Chuyên viên phụ trách": "Người khác",
        }
    )
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        try:
            import_snapshot(session, snapshot)
        except ImportCollisionError as exc:
            assert "assigned specialist" in str(exc)
            assert "legacy company 1" in str(exc)
        else:
            raise AssertionError("Expected conflicting company specialist import to fail closed")


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
        # Contract validation now occurs before schema creation, so even a
        # read query against Site would be invalid. Assert the stronger guard.
        assert inspect(engine).has_table("site") is False
        assert inspect(engine).has_table("company") is False


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


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize(
    ("approved_sheet", "approved_row_key"),
    [("db.cc", "999"), ("db.ktra", "200")],
)
def test_stale_resurrection_approval_not_in_confirmed_blanked_contract_fails_pre_schema(
    monkeypatch, tmp_path, strict, approved_sheet, approved_row_key
):
    # Signed approval is not a source-of-truth designation of deleted rows.
    # Previously this orphan authorization was ignored and import proceeded.
    blanked = tmp_path / "blanked.json"
    blanked.write_text(json.dumps({"rows": []}), encoding="utf-8")
    resurrection = tmp_path / "resurrections.json"
    resurrection.write_text(json.dumps({"rows": [{
        "source_sheet": approved_sheet,
        "source_row_key": approved_row_key,
        "approved_override": {"site_legacy_id": 10},
    }]}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", blanked)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", resurrection)
    snapshot = sample_snapshot()
    original_source = json.loads(json.dumps(snapshot))
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(
        ConfirmedBlankedContractError, match="unconfirmed row"
    ) as exc:
        import_snapshot(
            session,
            snapshot,
            options=ImportExecutionOptions(strict_certificate_case_source_links=strict),
        )
    assert f"{approved_sheet}:{approved_row_key}" in str(exc.value)
    assert inspect(engine).has_table("company") is False
    assert inspect(engine).has_table("certificate") is False
    assert snapshot == original_source


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("invalid_value", ["1.5", "1e2", "not-an-id", None])
def test_signed_resurrection_with_mixed_valid_invalid_override_values_fails_pre_schema(
    monkeypatch, tmp_path, strict, invalid_value
):
    # Signed authorization must not silently drop an invalid second field
    # while retaining the first and passing import preflight.
    blanked = tmp_path / "confirmed_blanked.json"
    blanked.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cc", "source_row_key": "200",
    }]}), encoding="utf-8")
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cc", "source_row_key": "200",
        "approved_override": {
            "case_legacy_id": 100,
            "site_legacy_id": invalid_value,
        },
    }]}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", blanked)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approved)
    snapshot = sample_snapshot()
    original_source = json.loads(json.dumps(snapshot))
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(
        ConfirmedBlankedContractError, match="invalid approved_override"
    ) as exc:
        import_snapshot(
            session, snapshot,
            options=ImportExecutionOptions(strict_certificate_case_source_links=strict),
        )
    assert "db.cc:200" in str(exc.value)
    assert inspect(engine).has_table("company") is False
    assert snapshot == original_source


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("invalid_value", ["1.5", "1e2", "not-an-id", None])
def test_signed_resurrection_cannot_ignore_invalid_extra_submitted_override_pre_schema(
    monkeypatch, tmp_path, strict, invalid_value
):
    # Before the fix, dropping this invalid extra key made the normalized
    # remediation payload appear identical to the authorized one.
    blanked = tmp_path / "confirmed_blanked.json"
    blanked.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cso", "source_row_key": "10",
    }]}), encoding="utf-8")
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cso", "source_row_key": "10",
        "approved_override": {"company_legacy_id": 1},
    }]}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", blanked)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approved)
    snapshot = sample_snapshot()
    snapshot["db.cso"][0]["ID Cty"] = ""
    original_source = json.loads(json.dumps(snapshot))
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(
        ConfirmedBlankedResurrectionError, match="invalid remediation override"
    ) as exc:
        import_snapshot(
            session, snapshot,
            remediation_overrides={"db.cso": {"10": {
                "company_legacy_id": "1.0",
                "site_legacy_id": invalid_value,
            }}},
            options=ImportExecutionOptions(strict_certificate_case_source_links=strict),
        )
    assert "db.cso:10" in str(exc.value)
    assert inspect(engine).has_table("site") is False
    assert snapshot == original_source


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("source_fk", ["1", ""])
def test_approved_resurrection_rejects_nonimportable_signed_parent_even_if_source_fk_resolves(
    monkeypatch, tmp_path, strict, source_fk
):
    blanked = tmp_path / "blanked.json"
    blanked.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cso", "source_row_key": "10",
    }]}), encoding="utf-8")
    approvals = tmp_path / "approvals.json"
    approvals.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cso", "source_row_key": "10",
        "approved_override": {"company_legacy_id": 999},
    }]}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", blanked)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approvals)
    snapshot = sample_snapshot()
    snapshot["db.cso"][0]["ID Cty"] = source_fk
    before = json.loads(json.dumps(snapshot))
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(
        ConfirmedBlankedResurrectionError, match="not importable"
    ) as exc:
        import_snapshot(
            session, snapshot,
            remediation_overrides={"db.cso": {"10": {"company_legacy_id": 999}}},
            options=ImportExecutionOptions(strict_certificate_case_source_links=strict),
        )
    assert "db.cso:10" in str(exc.value)
    assert inspect(engine).has_table("company") is False
    assert inspect(engine).has_table("site") is False
    assert snapshot == before


@pytest.mark.parametrize("strict", [False, True])
def test_approved_resurrection_rejects_requested_row_absent_from_source_snapshot(
    monkeypatch, tmp_path, strict
):
    # The signed contract belongs to the independent blanked list but cannot
    # authorize a restoration of an identity absent from the current snapshot.
    blanked = tmp_path / "blanked.json"
    blanked.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cso", "source_row_key": "999",
    }]}), encoding="utf-8")
    approvals = tmp_path / "approvals.json"
    approvals.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cso", "source_row_key": "999",
        "approved_override": {"company_legacy_id": 1},
    }]}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", blanked)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approvals)
    snapshot = sample_snapshot()
    before = json.loads(json.dumps(snapshot))
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(
        ConfirmedBlankedResurrectionError, match="not found in the supplied snapshot"
    ) as exc:
        import_snapshot(
            session, snapshot,
            remediation_overrides={"db.cso": {"999": {"company_legacy_id": 1}}},
            options=ImportExecutionOptions(strict_certificate_case_source_links=strict),
        )
    assert "db.cso:999" in str(exc.value)
    assert inspect(engine).has_table("company") is False
    assert snapshot == before


@pytest.mark.parametrize("strict", [False, True])
def test_unused_signed_approval_without_submitted_restoration_is_not_an_import_order(
    monkeypatch, tmp_path, strict
):
    blanked = tmp_path / "blanked.json"
    blanked.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cso", "source_row_key": "999",
    }]}), encoding="utf-8")
    approvals = tmp_path / "approvals.json"
    approvals.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cso", "source_row_key": "999",
        "approved_override": {"company_legacy_id": 1},
    }]}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", blanked)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approvals)
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(
            session, sample_snapshot(),
            options=ImportExecutionOptions(strict_certificate_case_source_links=strict),
        )
        assert session.query(Company).count() == 1
        assert session.query(Site).count() == 1


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize(
    ("approved_sheet", "approved_row_key", "irrelevant_fk_key"),
    [
        ("db.cso", "10", "case_legacy_id"),
        ("db.ktra", "100", "company_legacy_id"),
        ("db.cc", "200", "company_legacy_id"),
        ("db.dkkd", "300", "case_legacy_id"),
        ("db.Tdoi", "400", "company_legacy_id"),
        ("db.Tdoi2", "500", "site_legacy_id"),
    ],
)
def test_signed_resurrection_rejects_valid_numeric_wrong_sheet_fk_owner_pre_schema(
    monkeypatch, tmp_path, strict, approved_sheet, approved_row_key, irrelevant_fk_key
):
    # The old code accepted a signed, numeric but unused key. With the raw
    # source FK already resolvable, that key could authorize resurrection
    # without matching any parent relationship for this sheet.
    blanked = tmp_path / "blanked.json"
    blanked.write_text(json.dumps({"rows": [{
        "source_sheet": approved_sheet,
        "source_row_key": approved_row_key,
    }]}), encoding="utf-8")
    approved = tmp_path / "approvals.json"
    approved.write_text(json.dumps({"rows": [{
        "source_sheet": approved_sheet,
        "source_row_key": approved_row_key,
        "approved_override": {irrelevant_fk_key: 10},
    }]}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", blanked)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approved)
    snapshot = sample_snapshot()
    snapshot_before = json.loads(json.dumps(snapshot))
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(
        ConfirmedBlankedContractError, match="unsupported approved_override key"
    ) as exc:
        import_snapshot(
            session,
            snapshot,
            remediation_overrides={approved_sheet: {
                approved_row_key: {irrelevant_fk_key: 10}
            }},
            options=ImportExecutionOptions(strict_certificate_case_source_links=strict),
        )
    assert f"{approved_sheet}:{approved_row_key}" in str(exc.value)
    assert irrelevant_fk_key in str(exc.value)
    assert inspect(engine).has_table("company") is False
    assert inspect(engine).has_table("certificate") is False
    assert snapshot == snapshot_before


def test_signed_resurrection_accepts_both_actual_certificate_fk_owner_keys(monkeypatch, tmp_path):
    approved = tmp_path / "approvals.json"
    approved.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cc",
        "source_row_key": "200",
        "approved_override": {"case_legacy_id": "100.0", "site_legacy_id": "0010.00"},
    }]}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approved)
    assert phase2_import_module.load_confirmed_blanked_resurrections() == {
        ("db.cc", "200"): {"case_legacy_id": 100, "site_legacy_id": 10}
    }


def test_signed_resurrection_accepts_literal_integer_with_zero_decimal_suffix(monkeypatch, tmp_path):
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cso", "source_row_key": "10",
        "approved_override": {"company_legacy_id": "0001.00"},
    }]}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approved)
    assert phase2_import_module.load_confirmed_blanked_resurrections() == {
        ("db.cso", "10"): {"company_legacy_id": 1}
    }


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


def test_import_preserves_disconnected_inspection_segments_without_a_fake_envelope():
    snapshot = sample_snapshot()
    snapshot["db.ktra"][0]["Ngày K.tra"] = "20/01/2021; 22-23/01/2021"
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, snapshot)
        outcome = session.scalars(select(InspectionOutcome)).one()
        segments = list(session.scalars(select(InspectionPeriodSegment).order_by(InspectionPeriodSegment.ordinal)))
        assert outcome.inspected_on is None
        assert outcome.inspected_to_on is None
        assert [(segment.ordinal, segment.started_on.isoformat(), segment.ended_on.isoformat()) for segment in segments] == [
            (1, "2021-01-20", "2021-01-20"),
            (2, "2021-01-22", "2021-01-23"),
        ]


def test_import_preserves_each_zero_segment_source_state():
    cases = {
        "???": "PENDING_INPUT",
        "-": "NOT_APPLICABLE",
        "": "MISSING",
        "Xét hồ sơ": "NON_DATE_EXPRESSION",
        "24-01/2018": "UNRESOLVED",
    }
    for raw_value, expected_state in cases.items():
        snapshot = sample_snapshot()
        snapshot["db.ktra"][0]["Ngày K.tra"] = raw_value
        engine = create_engine("sqlite:///:memory:", future=True)
        with Session(engine) as session:
            import_snapshot(session, snapshot)
            outcome = session.scalars(select(InspectionOutcome)).one()
            assert outcome.inspection_period_state == expected_state
            assert session.scalars(select(InspectionPeriodSegment)).all() == []


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


@pytest.mark.parametrize("case_ref", ["100", ""])
def test_strict_preflight_blocks_importable_confirmed_blanked_certificate_without_schema_write(
    monkeypatch, tmp_path, case_ref
):
    # An approved blanked-row source identity is not permission to resurrect
    # the row merely because its parent keys now resolve.
    snapshot = sample_snapshot()
    snapshot["db.cc"][0]["ID ĐỢT KTRA"] = case_ref
    contract_path = tmp_path / "confirmed_blanked.json"
    contract_path.write_text(
        json.dumps({"rows": [{"source_sheet": "db.cc", "source_row_key": "200"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", contract_path)
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(CertificateCaseSourceIntegrityError) as exc:
        import_snapshot(
            session, snapshot,
            options=ImportExecutionOptions(strict_certificate_case_source_links=True),
        )
    report = exc.value.report
    assert report["effective_anomalies"] == []
    assert report["effective_parent_anomalies"] == []
    assert len(report["excluded_importable_certificate_rows"]) == 1
    assert "1 importable confirmed-blanked Certificate row(s)" in str(exc.value)
    assert inspect(engine).has_table("certificate") is False
    assert inspect(engine).has_table("site") is False


@pytest.mark.parametrize(
    ("confirmed_sheet", "confirmed_key"),
    [
        ("db.cty", "1"),
        ("db.cso", "10"),
        ("db.ktra", "100"),
        ("db.cc", "200"),
        ("db.dkkd", "300"),
        ("db.Tdoi", "400"),
        ("db.Tdoi2", "500"),
    ],
)
def test_default_import_cannot_resurrect_materializable_confirmed_blanked_rows(
    monkeypatch, tmp_path, confirmed_sheet, confirmed_key
):
    contract_path = tmp_path / "confirmed_blanked.json"
    contract_path.write_text(
        json.dumps({"rows": [{
            "source_sheet": confirmed_sheet, "source_row_key": confirmed_key
        }]}), encoding="utf-8"
    )
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", contract_path)
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(
        ConfirmedBlankedResurrectionError, match="no explicit owner-approved resurrection override"
    ) as exc:
        import_snapshot(session, sample_snapshot())
    assert f"{confirmed_sheet}:{confirmed_key}" in str(exc.value)
    assert inspect(engine).has_table("company") is False
    assert inspect(engine).has_table("certificate") is False


def test_approved_restoration_of_materializable_blanked_row_requires_exact_override(
    monkeypatch, tmp_path
):
    contract = tmp_path / "confirmed_blanked.json"
    contract.write_text(
        json.dumps({"rows": [{
            "source_sheet": "db.cso", "source_row_key": "10"
        }]}), encoding="utf-8"
    )
    approved = tmp_path / "approved_resurrections.json"
    approved.write_text(
        json.dumps({"rows": [{
            "source_sheet": "db.cso", "source_row_key": "10",
            "approved_override": {"company_legacy_id": 1},
        }]}), encoding="utf-8"
    )
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", contract)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approved)
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(
            session, sample_snapshot(),
            remediation_overrides={"db.cso": {"10": {"company_legacy_id": 1}}},
        )
        assert session.query(Site).count() == 1


def test_invalid_resurrection_override_rejected_before_schema_mutation(monkeypatch, tmp_path):
    contract = tmp_path / "confirmed_blanked.json"
    contract.write_text(json.dumps({"rows": [
        {"source_sheet": "db.cso", "source_row_key": "10"}
    ]}), encoding="utf-8")
    approved = tmp_path / "approved_resurrections.json"
    approved.write_text(json.dumps({"rows": []}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", contract)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approved)
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(ConfirmedBlankedResurrectionError):
        import_snapshot(
            session, sample_snapshot(),
            remediation_overrides={"db.cso": {"10": {"company_legacy_id": 1}}},
        )
    assert inspect(engine).has_table("site") is False


@pytest.mark.parametrize(
    ("case_ref", "case_site", "case_gxp", "expected_error"),
    [
        ("100", "10", "GMP", None),
        ("", "10", "GMP", None),
        ("100", "11", "GMP", "SITE_MISMATCH"),
        ("100", "10", "GLP", "GXP_MISMATCH"),
    ],
)
def test_strict_import_reviews_approved_certificate_resurrection_as_effective_source(
    monkeypatch, tmp_path, case_ref, case_site, case_gxp, expected_error
):
    # Exact owner approval restores an effective row; it does not exempt that
    # row from the Case/Site/GxP integrity invariant.
    blanked = tmp_path / "blanked.json"
    blanked.write_text(
        json.dumps({"rows": [{"source_sheet": "db.cc", "source_row_key": "200"}]}),
        encoding="utf-8",
    )
    approved = tmp_path / "resurrections.json"
    approved.write_text(
        json.dumps({"rows": [{
            "source_sheet": "db.cc", "source_row_key": "200",
            "approved_override": {"site_legacy_id": 10},
        }]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", blanked)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approved)

    snapshot = sample_snapshot()
    snapshot["db.cc"][0]["ID ĐỢT KTRA"] = case_ref
    snapshot["db.ktra"][0]["ID CƠ SỞ"] = case_site
    snapshot["db.ktra"][0]["LOẠI KT"] = case_gxp
    if case_site == "11":
        second_site = dict(snapshot["db.cso"][0])
        second_site.update({"ID": "11", "TÊN CƠ SỞ": "Site B"})
        snapshot["db.cso"].append(second_site)
    overrides = {"db.cc": {"200": {"site_legacy_id": 10}}}
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        if expected_error is not None:
            with pytest.raises(CertificateCaseSourceIntegrityError) as exc:
                import_snapshot(
                    session, snapshot,
                    remediation_overrides=overrides,
                    options=ImportExecutionOptions(strict_certificate_case_source_links=True),
                )
            assert [row["classification"] for row in exc.value.report["effective_anomalies"]] == [expected_error]
            assert exc.value.report["excluded_importable_certificate_rows"] == []
            assert inspect(engine).has_table("certificate") is False
            assert inspect(engine).has_table("site") is False
        else:
            import_snapshot(
                session, snapshot,
                remediation_overrides=overrides,
                options=ImportExecutionOptions(strict_certificate_case_source_links=True),
            )
            certificates = session.scalars(select(Certificate)).all()
            assert len(certificates) == 1
            assert (certificates[0].case_id is None) is (case_ref == "")
            assert certificates[0].issuance_basis == (
                "administrative_no_inspection" if case_ref == "" else "inspection_case"
            )


def test_strict_certificate_resurrection_requires_exact_owner_approval_before_schema(
    monkeypatch, tmp_path
):
    blanked = tmp_path / "blanked.json"
    blanked.write_text(
        json.dumps({"rows": [{"source_sheet": "db.cc", "source_row_key": "200"}]}),
        encoding="utf-8",
    )
    approved = tmp_path / "resurrections.json"
    approved.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cc", "source_row_key": "200",
        "approved_override": {"site_legacy_id": 10},
    }]}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", blanked)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approved)
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(
        ConfirmedBlankedResurrectionError, match="does not match"
    ):
        import_snapshot(
            session, sample_snapshot(),
            remediation_overrides={"db.cc": {"200": {"site_legacy_id": 11}}},
            options=ImportExecutionOptions(strict_certificate_case_source_links=True),
        )
    assert inspect(engine).has_table("certificate") is False
    assert inspect(engine).has_table("company") is False



@pytest.mark.parametrize(
    ("raw_site", "raw_case", "approved_values", "case_site", "expected_classification"),
    [
        ("", "100", {"site_legacy_id": 10}, "10", None),
        ("10", "999", {"case_legacy_id": 100}, "10", None),
        ("", "100", {"site_legacy_id": 10}, "11", "SITE_MISMATCH"),
        # An already-importable Case FK must not be silently remapped by an
        # override, even when its replacement Case belongs to the Site.
        ("10", "100", {"case_legacy_id": 101}, "11", "SITE_MISMATCH"),
    ],
)
def test_strict_approved_resurrection_uses_only_effective_fk_and_keeps_raw_provenance(
    monkeypatch, tmp_path, raw_site, raw_case, approved_values, case_site, expected_classification
):
    snapshot = sample_snapshot()
    snapshot["db.cc"][0]["ID CƠ SỞ"] = raw_site
    snapshot["db.cc"][0]["ID ĐỢT KTRA"] = raw_case
    snapshot["db.ktra"][0]["ID CƠ SỞ"] = case_site
    if case_site == "11":
        second_site = dict(snapshot["db.cso"][0])
        second_site.update({"ID": "11", "TÊN CƠ SỞ": "Site B"})
        snapshot["db.cso"].append(second_site)
    if "case_legacy_id" in approved_values:
        snapshot["db.ktra"].append({
            "ID": "101", "ID CƠ SỞ": "10", "LOẠI KT": "GMP"
        })
    original = json.loads(json.dumps(snapshot))
    blanked = tmp_path / "blanked.json"
    blanked.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cc", "source_row_key": "200"
    }]}), encoding="utf-8")
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cc", "source_row_key": "200",
        "approved_override": approved_values,
    }]}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", blanked)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approved)
    override = {"db.cc": {"200": approved_values}}
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        if expected_classification:
            with pytest.raises(CertificateCaseSourceIntegrityError) as exc:
                import_snapshot(
                    session, snapshot, remediation_overrides=override,
                    options=ImportExecutionOptions(strict_certificate_case_source_links=True),
                )
            assert [r["classification"] for r in exc.value.report["effective_anomalies"]] == [
                expected_classification
            ]
            if raw_site == "":
                assert exc.value.report["approved_source_fk_provenance"] == [{
                    "source_sheet": "db.cc",
                    "source_row_key": "200",
                    "source_field": "site_legacy_id_ref",
                    "raw_fk_value": "",
                    "effective_fk_value": 10,
                    "approved_override_key": "site_legacy_id",
                }]
            else:
                assert "approved_source_fk_provenance" not in exc.value.report
            assert inspect(engine).has_table("certificate") is False
        else:
            projected, evidence = phase2_import_module._validate_confirmed_blanked_source_materialization(
                snapshot,
                confirmed_blanked_row_keys={("db.cc", "200")},
                overrides=override,
            )
            assert len(evidence) == 1
            assert evidence[0]["raw_fk_value"] == ("" if raw_site == "" else "999")
            assert evidence[0]["effective_fk_value"] in (10, 100)
            assert projected["db.cc"][0][evidence[0]["source_field"]] == str(evidence[0]["effective_fk_value"])
            import_snapshot(
                session, snapshot, remediation_overrides=override,
                options=ImportExecutionOptions(strict_certificate_case_source_links=True),
            )
            cert = session.scalars(select(Certificate)).one()
            assert cert.case_id is not None
    assert snapshot == original


def test_strict_approved_parent_chain_fk_projection_propagates_to_certificate(
    monkeypatch, tmp_path
):
    snapshot = sample_snapshot()
    snapshot["db.ktra"][0]["ID CƠ SỞ"] = ""
    original = json.loads(json.dumps(snapshot))
    blanked = tmp_path / "blanked.json"
    blanked.write_text(json.dumps({"rows": [{
        "source_sheet": "db.ktra", "source_row_key": "100",
    }]}), encoding="utf-8")
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps({"rows": [{
        "source_sheet": "db.ktra", "source_row_key": "100",
        "approved_override": {"site_legacy_id": 10},
    }]}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", blanked)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approved)
    override = {"db.ktra": {"100": {"site_legacy_id": 10}}}
    projected, evidence = phase2_import_module._validate_confirmed_blanked_source_materialization(
        snapshot,
        confirmed_blanked_row_keys={("db.ktra", "100")}, overrides=override,
    )
    assert [(e["source_sheet"], e["raw_fk_value"], e["effective_fk_value"]) for e in evidence] == [
        ("db.ktra", "", 10)
    ]
    assert projected["db.ktra"][0]["site_legacy_id_ref"] == "10"
    assert snapshot == original
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(
            session, snapshot, remediation_overrides=override,
            options=ImportExecutionOptions(strict_certificate_case_source_links=True),
        )
        assert session.query(Certificate).count() == 1


def test_strict_rejects_nonapproved_generic_fk_projection_even_if_default_import_accepts_it(
    monkeypatch, tmp_path
):
    snapshot = sample_snapshot()
    snapshot["db.ktra"][0]["ID CƠ SỞ"] = ""
    contract = tmp_path / "blanked.json"
    contract.write_text(json.dumps({"rows": []}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", contract)
    override = {"db.ktra": {"100": {"site_legacy_id": 10}}}
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(CertificateCaseSourceIntegrityError) as exc:
        import_snapshot(
            session, snapshot, remediation_overrides=override,
            options=ImportExecutionOptions(strict_certificate_case_source_links=True),
        )
    assert exc.value.report["effective_parent_anomalies"]
    assert inspect(engine).has_table("certificate") is False



@pytest.mark.parametrize("strict", [False, True])
def test_approved_case_fk_override_cannot_silently_convert_blank_administrative_source(
    monkeypatch, tmp_path, strict
):
    # The existing optional-FK owner intentionally treats an empty source
    # reference as administrative. An approved case_legacy_id would be
    # ignored by the actual importer and must fail before any schema write.
    snapshot = sample_snapshot()
    snapshot["db.cc"][0]["ID ĐỢT KTRA"] = ""
    original_snapshot = json.loads(json.dumps(snapshot))
    blanked = tmp_path / "confirmed_blanked.json"
    blanked.write_text(json.dumps({"rows": [
        {"source_sheet": "db.cc", "source_row_key": "200"}
    ]}), encoding="utf-8")
    approved = tmp_path / "approved_resurrections.json"
    approved.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cc", "source_row_key": "200",
        "approved_override": {"case_legacy_id": 100},
    }]}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", blanked)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approved)
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(
        ConfirmedBlankedResurrectionError, match="empty optional inspection_case_legacy_id_ref"
    ) as exc:
        import_snapshot(
            session, snapshot,
            remediation_overrides={"db.cc": {"200": {"case_legacy_id": 100}}},
            options=ImportExecutionOptions(strict_certificate_case_source_links=strict),
        )
    assert "db.cc:200" in str(exc.value)
    assert inspect(engine).has_table("certificate") is False
    assert inspect(engine).has_table("company") is False
    assert snapshot == original_snapshot


@pytest.mark.parametrize("strict", [False, True])
def test_approved_administrative_certificate_with_site_only_remediation_keeps_null_case(
    monkeypatch, tmp_path, strict
):
    # A signed Site override is independent of the optional Case. Keep the
    # previously supported administrative Certificate behavior unchanged.
    snapshot = sample_snapshot()
    snapshot["db.cc"][0]["ID ĐỢT KTRA"] = ""
    snapshot["db.cc"][0]["ID CƠ SỞ"] = ""
    blanked = tmp_path / "confirmed_blanked.json"
    blanked.write_text(json.dumps({"rows": [
        {"source_sheet": "db.cc", "source_row_key": "200"}
    ]}), encoding="utf-8")
    approved = tmp_path / "approved_resurrections.json"
    approved.write_text(json.dumps({"rows": [{
        "source_sheet": "db.cc", "source_row_key": "200",
        "approved_override": {"site_legacy_id": 10},
    }]}), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_ROWS_PATH", blanked)
    monkeypatch.setattr(phase2_import_module, "CONFIRMED_BLANKED_RESURRECTIONS_PATH", approved)
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(
            session, snapshot,
            remediation_overrides={"db.cc": {"200": {"site_legacy_id": 10}}},
            options=ImportExecutionOptions(strict_certificate_case_source_links=strict),
        )
        certificate = session.scalars(select(Certificate)).one()
        assert certificate.case_id is None
        assert certificate.issuance_basis == "administrative_no_inspection"
