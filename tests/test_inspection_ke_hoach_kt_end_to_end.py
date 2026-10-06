from __future__ import annotations

import hashlib
from datetime import date
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import backend.app.document.service as document_service_module
import backend.app.document.template_binary as template_binary_module
from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState, DocumentVariantType
from backend.app.db.models.phase1 import (
    Case,
    CaseEvaluationScope,
    CaseEvaluationScopeBlock,
    CaseEvaluationScopeSelection,
    Company,
    EvaluationScopeTaxonomyNode,
    EvaluationScopeTaxonomyVersion,
    InspectionPlan,
    InspectionTeam,
    InspectionTeamMember,
    InspectorProfile,
    Person,
    Site,
    StorageBinding,
    TemplateBinding,
    TemplateDefinition,
)
from backend.app.document.inspection_ke_hoach_kt_payload_input import (
    InspectionKeHoachKtPayloadInput,
)
from backend.app.document.inspection_ke_hoach_kt_team_projection import (
    InspectionKeHoachKtTeamMemberInput,
)
from backend.app.document.inspection_ke_hoach_kt_template_asset_contract import (
    InspectionKeHoachKtTemplateAssetContractError,
)
from backend.app.document.template_binary_binding import assign_template_binary_binding
from backend.app.project_paths import repo_root
from backend.app.services.document_api import DocumentWorkflowService
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.types import StorageConfig


GLP_BOOKMARKS = (
    "Fulldate", "TenCoSo1", "DiaChiCoSo", "QDKT", "NgayQDKT", "DayChuyen",
    "TT1x", "TT2x", "TT3x", "TT3Del", "TT_ext", "TT_VKNx", "VKNx",
    "TT_SYTx", "Diadiemx", "Diadiemx1",
)


def _storage() -> tuple[FilesystemStorageService, Path]:
    root = Path(tempfile.mkdtemp(prefix="khkt-e2e-"))
    inspection_root = root / "inspection"
    dkkd_root = root / "dkkd"
    template_root = root / "templates"
    inspection_root.mkdir(parents=True)
    dkkd_root.mkdir(parents=True)
    template_root.mkdir(parents=True)
    return (
        FilesystemStorageService(
            StorageConfig(
                inspection_root=inspection_root,
                dkkd_root=dkkd_root,
                template_root=template_root,
            )
        ),
        root,
    )


def _build_glp_template(path: Path) -> bytes:
    paragraphs = []
    for index, name in enumerate(GLP_BOOKMARKS, start=1):
        value = " – Thành viên;" if name == "TT_ext" else f"SOURCE-{name}"
        paragraphs.append(
            f'<w:p><w:bookmarkStart w:id="{index}" w:name="{name}"/>'
            f'<w:r><w:t>{value}</w:t></w:r>'
            f'<w:bookmarkEnd w:id="{index}"/></w:p>'
        )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(paragraphs)
        + "</w:body></w:document>"
    ).encode("utf-8")
    content_types = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)
    return path.read_bytes()


GMP_BOOKMARKS = (
    "Fulldate", "TenCoSo1", "DiaChiCoSo", "QDKT", "NgayQDKT", "DayChuyen",
    "GioiHanPvi", "GhPviDG", "TieuchuanKT", "TT1x", "TT2x", "TT3x", "TT3Del",
    "TT_ext", "TT_VKNx", "VKNx", "TT_SYTx", "Diadiemx", "Diadiemx1", "DGMoi",
    "PVDuoclieu1", "PVCepha1", "PVPeni1", "PVSuibot", "PVNangmem1", "PVDuoclieu2",
    "PVNangmem2", "PVTiem1", "PVNhomat", "PVCepha2", "PVTiem2", "PVPeni2", "PVTiem3",
)


def _build_gmp_structural_template(path: Path) -> bytes:
    scalar_prefix = GMP_BOOKMARKS[:12]
    structural_scope = GMP_BOOKMARKS[20:]
    parts: list[str] = []
    for index, name in enumerate(scalar_prefix, start=1):
        parts.append(
            f'<w:p><w:bookmarkStart w:id="{index}" w:name="{name}"/>'
            f'<w:r><w:t>SOURCE-{name}</w:t></w:r>'
            f'<w:bookmarkEnd w:id="{index}"/></w:p>'
        )

    parts.append(
        '<w:p><w:bookmarkStart w:id="13" w:name="TT3Del"/>'
        '<w:r><w:t>DELETE-THIRD-MEMBER</w:t></w:r></w:p>'
        '<w:p><w:bookmarkEnd w:id="13"/>'
        '<w:bookmarkStart w:id="14" w:name="TT_ext"/>'
        '<w:r><w:t> – Thành viên;</w:t></w:r>'
        '<w:bookmarkEnd w:id="14"/></w:p>'
    )

    for index, name in enumerate(GMP_BOOKMARKS[14:20], start=15):
        parts.append(
            f'<w:p><w:bookmarkStart w:id="{index}" w:name="{name}"/>'
            f'<w:r><w:t>SOURCE-{name}</w:t></w:r>'
            f'<w:bookmarkEnd w:id="{index}"/></w:p>'
        )

    for index, name in enumerate(structural_scope, start=21):
        parts.append(
            '<w:tbl><w:tr><w:tc>'
            f'<w:p><w:bookmarkStart w:id="{index}" w:name="{name}"/>'
            f'<w:r><w:t>DELETE-{name}-A</w:t></w:r></w:p>'
            f'<w:p><w:r><w:t>DELETE-{name}-B</w:t></w:r></w:p>'
            f'<w:bookmarkEnd w:id="{index}"/>'
            f'<w:p><w:r><w:t>KEEP-{name}</w:t></w:r></w:p>'
            '</w:tc></w:tr></w:tbl>'
        )

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>' + ''.join(parts) + '</w:body></w:document>'
    ).encode("utf-8")
    content_types = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)
    return path.read_bytes()


def _seed_canonical_khkt(session: Session) -> tuple[str, str]:
    company = Company(legacy_company_id=901, legal_name="Cong ty KHKT", short_name="KHKT")
    session.add(company)
    session.flush()
    site = Site(
        legacy_site_id=902,
        company_id=company.id,
        site_name="Cơ sở GLP A",
        site_address="Số 1 Đường Kiểm nghiệm",
        province_name="Hà Nội",
    )
    session.add(site)
    session.flush()
    case = Case(
        legacy_inspection_id=903,
        legacy_inspection_code="KT-2026-GLP-E2E",
        site_id=site.id,
        gxp_type="GLP",
        applicable_standard="WHO GLP",
        state=CaseState.PLANNED,
        opened_year=2026,
    )
    session.add(case)
    session.flush()
    session.add(
        InspectionPlan(
            case_id=case.id,
            decision_reference="123/QĐ-QLD",
            decision_date=__import__("datetime").date(2026, 10, 1),
        )
    )

    taxonomy = EvaluationScopeTaxonomyVersion(
        taxonomy_content_sha256="a" * 64,
        source_workbook_sha256="b" * 64,
        schema_version="khkt-e2e-v1",
    )
    session.add(taxonomy)
    session.flush()
    root_node = EvaluationScopeTaxonomyNode(
        taxonomy_version_id=taxonomy.id,
        parent_node_id=None,
        gxp_type="GLP",
        source_name="test",
        node_key="1",
        description="Root",
        hint=None,
        main_topic=None,
        short_render="* Root",
        no_expand=None,
        source_order=1,
        source_excel_row=1,
    )
    session.add(root_node)
    session.flush()
    child_node = EvaluationScopeTaxonomyNode(
        taxonomy_version_id=taxonomy.id,
        parent_node_id=root_node.id,
        gxp_type="GLP",
        source_name="test",
        node_key="1.1",
        description="Child",
        hint=None,
        main_topic=None,
        short_render="Child $$",
        no_expand=None,
        source_order=2,
        source_excel_row=2,
    )
    session.add(child_node)
    session.flush()
    scope = CaseEvaluationScope(
        case_id=case.id,
        taxonomy_version_id=taxonomy.id,
        source_classification="STRUCTURED_VALID",
        raw_legacy_value="legacy",
        rendered_prose=None,
        limitation_text="",
    )
    session.add(scope)
    session.flush()
    block = CaseEvaluationScopeBlock(
        case_evaluation_scope_id=scope.id,
        ordinal=1,
        name=None,
        note=None,
        raw_block_value=None,
    )
    session.add(block)
    session.flush()
    session.add(
        CaseEvaluationScopeSelection(
            block_id=block.id,
            taxonomy_node_id=child_node.id,
            source_order=1,
            custom_description="beta lactam",
            node_key_snapshot="1.1",
            taxonomy_description_snapshot="Child",
        )
    )

    team = InspectionTeam(case_id=case.id, display_text=None)
    session.add(team)
    session.flush()
    for sort_order, (display_name, role_code, role_label) in enumerate(
        (
            ("Trưởng đoàn A", "LEADER", "Trưởng đoàn"),
            ("Thư ký B", "SECRETARY", "Thư ký"),
            ("Thành viên C", "MEMBER", "Thành viên"),
        ),
        start=1,
    ):
        person = Person(full_name=display_name, display_name=display_name)
        session.add(person)
        session.flush()
        profile = InspectorProfile(
            person_id=person.id,
            is_active=True,
            roster_group="DRUG_ADMINISTRATION_AND_TRADITIONAL_MEDICINE",
        )
        session.add(profile)
        session.flush()
        session.add(
            InspectionTeamMember(
                team_id=team.id,
                inspector_profile_id=profile.id,
                person_id=None,
                participant_catalog_id=None,
                identity_kind="INSPECTOR_PROFILE",
                display_name=display_name,
                role_code=role_code,
                role_label=role_label,
                sort_order=sort_order,
            )
        )
    session.flush()
    return case.id, site.id


def test_khkt_binary_end_to_end_renders_canonical_db_payload_and_writes_output(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    storage, root = _storage()
    service = DocumentWorkflowService()
    try:
        monkeypatch.setenv("GXP_ARTIFACTS_ROOT", str(repo_root() / "artifacts"))
        template_relative = "test/3. Kế hoạch kiểm tra GLP.dotx"
        template_path = root / "templates" / template_relative
        template_path.parent.mkdir(parents=True)
        template_bytes = _build_glp_template(template_path)
        checksum = hashlib.sha256(template_bytes).hexdigest()

        expected_asset = SimpleNamespace(
            gxp_type="GLP",
            filename="3. Kế hoạch kiểm tra GLP.dotx",
            storage_root="template",
            storage_relative_path=template_relative,
            checksum_sha256=checksum,
        )
        original_loader = template_binary_module._EXACT_INSPECTION_GXP_ASSET_LOADERS[
            "INSPECTION_KE_HOACH_KT"
        ]
        monkeypatch.setitem(
            template_binary_module._EXACT_INSPECTION_GXP_ASSET_LOADERS,
            "INSPECTION_KE_HOACH_KT",
            (
                lambda gxp_type: expected_asset
                if gxp_type == "GLP"
                else (_ for _ in ()).throw(
                    InspectionKeHoachKtTemplateAssetContractError("unexpected GxP")
                ),
                InspectionKeHoachKtTemplateAssetContractError,
            ),
        )

        with Session(engine) as session:
            case_id, _ = _seed_canonical_khkt(session)
            definition = TemplateDefinition(
                family_code="INSPECTION_KE_HOACH_KT",
                document_type_code="INSPECTION_KE_HOACH_KT",
                source_application="Word",
                storage_scope="inspection_folder",
                legacy_host_procedure="RecordForm.CreateFile",
                legacy_case_number=3,
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                template_name="3. Ke hoach kiem tra {GP}.dotx",
                template_pattern="3. Ke hoach kiem tra {GP}.dotx",
                bookmark_contract=None,
                notes=None,
                is_active=True,
            )
            session.add(definition)
            session.flush()
            binding = TemplateBinding(
                family_code="INSPECTION_KE_HOACH_KT",
                template_definition_id=definition.id,
                gxp_type="GLP",
                legacy_mode=None,
                storage_scope="inspection_folder",
                is_active=True,
            )
            session.add(binding)
            session.flush()
            assign_template_binary_binding(
                session,
                template_binding_id=binding.id,
                storage_root="template",
                storage_relative_path=template_relative,
                original_filename=expected_asset.filename,
                checksum_sha256=checksum,
            )
            output_folder = "2026/902-KT-2026-GLP-E2E"
            (root / "inspection" / output_folder).mkdir(parents=True)
            session.add(
                StorageBinding(
                    case_id=case_id,
                    year=2026,
                    site_legacy_id=902,
                    inspection_legacy_code="KT-2026-GLP-E2E",
                    relative_path=output_folder,
                    observed_folder_label="902-KT-2026-GLP-E2E",
                    storage_class="synology_legacy",
                )
            )
            session.commit()

            result = service.render_template_docx(
                session,
                storage=storage,
                payload={
                    "family_code": "INSPECTION_KE_HOACH_KT",
                    "case_id": case_id,
                    "gxp_type": "GLP",
                    "storage_scope": "inspection_folder",
                    "idempotency_key": "khkt-e2e-glp-001",
                    "output_filename": "3. Kế hoạch kiểm tra GLP.docx",
                    "payload": {},
                    "strict_payload": True,
                },
                user=build_authenticated_user(
                    "khkt-e2e",
                    permissions={"document.read", "document.write"},
                ),
            )
            session.commit()

        assert result["generation_status"] == "succeeded"
        assert result["scalar_replacement_mode"] == "khkt_contract_exact"
        assert result["template_variant_key"] == "GLP"
        assert result["output_original_filename"] == "3. Kế hoạch kiểm tra GLP.docx"
        assert "TenCoSo1" in result["replaced_bookmarks"]
        assert "TT3Del" not in result["replaced_bookmarks"]

        output_path = (
            root
            / "inspection"
            / "2026/902-KT-2026-GLP-E2E"
            / "3. Kế hoạch kiểm tra GLP.docx"
        )
        assert output_path.exists()
        with ZipFile(output_path, "r") as archive:
            xml = archive.read("word/document.xml").decode("utf-8")
        assert "Cơ sở GLP A" in xml
        assert "Số 1 Đường Kiểm nghiệm" in xml
        assert "123/QĐ-QLD" in xml
        assert "Trưởng đoàn A" in xml
        assert "Thư ký B" in xml
        assert "Thành viên C" in xml
        assert "β-Lactam" in xml
        assert "SOURCE-TT3Del" in xml
        assert "SOURCE-TenCoSo1" not in xml

        monkeypatch.setitem(
            template_binary_module._EXACT_INSPECTION_GXP_ASSET_LOADERS,
            "INSPECTION_KE_HOACH_KT",
            original_loader,
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_khkt_gmp_end_to_end_applies_structural_team_and_scope_deletions(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    storage, root = _storage()
    service = DocumentWorkflowService()
    try:
        template_relative = "test/3. Kế hoạch kiểm tra GMP.dotx"
        template_path = root / "templates" / template_relative
        template_path.parent.mkdir(parents=True)
        template_bytes = _build_gmp_structural_template(template_path)
        checksum = hashlib.sha256(template_bytes).hexdigest()
        expected_asset = SimpleNamespace(
            gxp_type="GMP",
            filename="3. Kế hoạch kiểm tra GMP.dotx",
            storage_root="template",
            storage_relative_path=template_relative,
            checksum_sha256=checksum,
        )
        monkeypatch.setitem(
            template_binary_module._EXACT_INSPECTION_GXP_ASSET_LOADERS,
            "INSPECTION_KE_HOACH_KT",
            (
                lambda gxp_type: expected_asset
                if gxp_type == "GMP"
                else (_ for _ in ()).throw(
                    InspectionKeHoachKtTemplateAssetContractError("unexpected GxP")
                ),
                InspectionKeHoachKtTemplateAssetContractError,
            ),
        )

        with Session(engine) as session:
            company = Company(legacy_company_id=911, legal_name="Cong ty GMP", short_name="GMP")
            session.add(company)
            session.flush()
            site = Site(
                legacy_site_id=912,
                company_id=company.id,
                site_name="Cơ sở GMP A",
                site_address="Số 2 Đường GMP",
                province_name="Hà Nội",
            )
            session.add(site)
            session.flush()
            case = Case(
                legacy_inspection_id=913,
                legacy_inspection_code="KT-2026-GMP-STRUCT",
                site_id=site.id,
                gxp_type="GMP",
                applicable_standard="WHO GMP",
                state=CaseState.PLANNED,
                opened_year=2026,
            )
            session.add(case)
            session.flush()

            definition = TemplateDefinition(
                family_code="INSPECTION_KE_HOACH_KT",
                document_type_code="INSPECTION_KE_HOACH_KT",
                source_application="Word",
                storage_scope="inspection_folder",
                legacy_host_procedure="RecordForm.CreateFile",
                legacy_case_number=3,
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                template_name="3. Ke hoach kiem tra {GP}.dotx",
                template_pattern="3. Ke hoach kiem tra {GP}.dotx",
                bookmark_contract=None,
                notes=None,
                is_active=True,
            )
            session.add(definition)
            session.flush()
            binding = TemplateBinding(
                family_code="INSPECTION_KE_HOACH_KT",
                template_definition_id=definition.id,
                gxp_type="GMP",
                legacy_mode=None,
                storage_scope="inspection_folder",
                is_active=True,
            )
            session.add(binding)
            session.flush()
            assign_template_binary_binding(
                session,
                template_binding_id=binding.id,
                storage_root="template",
                storage_relative_path=template_relative,
                original_filename=expected_asset.filename,
                checksum_sha256=checksum,
            )
            output_folder = "2026/912-KT-2026-GMP-STRUCT"
            (root / "inspection" / output_folder).mkdir(parents=True)
            session.add(
                StorageBinding(
                    case_id=case.id,
                    year=2026,
                    site_legacy_id=912,
                    inspection_legacy_code="KT-2026-GMP-STRUCT",
                    relative_path=output_folder,
                    observed_folder_label="912-KT-2026-GMP-STRUCT",
                    storage_class="synology_legacy",
                )
            )
            session.commit()

            typed_payload = InspectionKeHoachKtPayloadInput(
                case_id=case.id,
                gxp_type="GMP",
                site_name="Cơ sở GMP A",
                site_address="Số 2 Đường GMP",
                province_name="Hà Nội",
                dossier_code=None,
                submitted_on=None,
                decision_reference="456/QĐ-QLD",
                decision_date=date(2026, 10, 2),
                applicable_standard="WHO GMP",
                daychuyen="Cephalosporin",
                gioi_han_pvi="Không",
                diadiemx="thành phố Hà Nội",
                vknx="Viện Kiểm nghiệm thuốc Trung ương",
                team_members=(
                    InspectionKeHoachKtTeamMemberInput(
                        display_name="Trưởng đoàn duy nhất",
                        sort_order=1,
                        role_code="LEADER",
                        identity_kind="INSPECTOR_PROFILE",
                        roster_group="DRUG_ADMINISTRATION_AND_TRADITIONAL_MEDICINE",
                    ),
                ),
                generated_on=date(2026, 10, 6),
                fulldate="ngày 06 tháng 10 năm 2026",
            )
            monkeypatch.setattr(
                document_service_module,
                "load_inspection_ke_hoach_kt_payload_input",
                lambda _session, *, case_id, generated_at: typed_payload,
            )

            result = service.render_template_docx(
                session,
                storage=storage,
                payload={
                    "family_code": "INSPECTION_KE_HOACH_KT",
                    "case_id": case.id,
                    "gxp_type": "GMP",
                    "storage_scope": "inspection_folder",
                    "idempotency_key": "khkt-e2e-gmp-struct-001",
                    "output_filename": "3. Kế hoạch kiểm tra GMP.docx",
                    "payload": {},
                    "strict_payload": True,
                },
                user=build_authenticated_user(
                    "khkt-e2e-struct",
                    permissions={"document.read", "document.write"},
                ),
            )
            session.commit()

        assert result["generation_status"] == "succeeded"
        assert result["scalar_replacement_mode"] == "khkt_contract_exact"
        output_path = (
            root
            / "inspection"
            / "2026/912-KT-2026-GMP-STRUCT"
            / "3. Kế hoạch kiểm tra GMP.docx"
        )
        with ZipFile(output_path, "r") as archive:
            xml = archive.read("word/document.xml").decode("utf-8")

        assert "DELETE-THIRD-MEMBER" not in xml
        for deleted_name in (
            "PVDuoclieu1", "PVPeni1", "PVSuibot", "PVNangmem1", "PVDuoclieu2",
            "PVNangmem2", "PVTiem1", "PVNhomat", "PVTiem2", "PVPeni2", "PVTiem3",
        ):
            assert f"DELETE-{deleted_name}-A" not in xml
            assert f"DELETE-{deleted_name}-B" not in xml
            assert f"KEEP-{deleted_name}" in xml

        for kept_name in ("PVCepha1", "PVCepha2"):
            assert f"DELETE-{kept_name}-A" in xml
            assert f"DELETE-{kept_name}-B" in xml
            assert f"KEEP-{kept_name}" in xml
    finally:
        shutil.rmtree(root, ignore_errors=True)
