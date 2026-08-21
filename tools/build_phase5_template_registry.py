from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_CONTRACT_PATH = ROOT / "artifacts/phase5/document_contract.json"
OUTPUT_JSON = ROOT / "artifacts/phase5/template_registry.curated.json"
OUTPUT_MD = ROOT / "artifacts/phase5/template_registry.curated.md"


ENTRY_DEFINITIONS = [
    {
        "family_code": "INSPECTION_BBTD_HOSO_DK",
        "logical_name": "Bien ban tham dinh ho so dang ky",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [1],
        "template_pattern": "1. BBTD Ho so DK - {GP} - Moi/Tai.dotx",
        "selection_legacy_mode": "moi_or_tai",
        "population_procedures": ["RecordForm.Tao_BBTD"],
        "bookmark_procedures": ["RecordForm.Tao_BBTD"],
        "copy_forward_dependencies": [],
        "notes": "Template branch depends on Moi/Tai state from Get_Tpl.",
    },
    {
        "family_code": "INSPECTION_QD_KT",
        "logical_name": "Quyet dinh kiem tra",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [2],
        "template_pattern": "2. QD KT - {GP}.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_QDKT_KHKT_BBKT"],
        "bookmark_procedures": ["RecordForm.Tao_QDKT_KHKT_BBKT"],
        "copy_forward_dependencies": [],
        "notes": "Shares payload builder with inspection plan and inspection minutes.",
    },
    {
        "family_code": "INSPECTION_KE_HOACH_KT",
        "logical_name": "Ke hoach kiem tra",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [3],
        "template_pattern": "3. Ke hoach kiem tra {GP}.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_QDKT_KHKT_BBKT"],
        "bookmark_procedures": ["RecordForm.Tao_QDKT_KHKT_BBKT"],
        "copy_forward_dependencies": [],
        "notes": "Uses same payload procedure with mode-specific bookmark deletion.",
    },
    {
        "family_code": "INSPECTION_BB_KT",
        "logical_name": "Bien ban kiem tra",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [4],
        "template_pattern": "4. BB KT - {GP}.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_QDKT_KHKT_BBKT"],
        "bookmark_procedures": ["RecordForm.Tao_QDKT_KHKT_BBKT"],
        "copy_forward_dependencies": [],
        "notes": "Same builder as cases 2 and 3 with additional reference-row suppression.",
    },
    {
        "family_code": "INSPECTION_CAPA_LAN_1",
        "logical_name": "Danh gia CAPA lan 1",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [5],
        "template_pattern": "5. Danh gia CAPA - {GP}.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_BB_CAPA"],
        "bookmark_procedures": ["RecordForm.Tao_BB_CAPA"],
        "copy_forward_dependencies": [
            {
                "source_family_code": "INSPECTION_BB_KT",
                "condition": "If prior BBKT exists and bookmark DsTT is present, copy deficiency table into CAPA document.",
                "source_bookmarks": ["DsTT"],
            }
        ],
        "notes": "Copy-forward from prior BBKT is evidenced by BBKT_goc and bookmark DsTT copy.",
    },
    {
        "family_code": "INSPECTION_CAPA_LAN_2",
        "logical_name": "Danh gia CAPA lan 2",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [6],
        "template_pattern": "5. Danh gia CAPA - {GP}.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_BB_CAPA"],
        "bookmark_procedures": ["RecordForm.Tao_BB_CAPA"],
        "copy_forward_dependencies": [
            {
                "source_family_code": "INSPECTION_CAPA_LAN_1",
                "condition": "If CopyPT is enabled and prior CAPA round 1 exists, copy CAPAx table into round 2 document.",
                "source_bookmarks": ["CAPAx"],
            }
        ],
        "notes": "Round 2 can reuse prior CAPA table when prior document exists.",
    },
    {
        "family_code": "INSPECTION_PT_PCT",
        "logical_name": "Phieu trinh PCT",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [7],
        "template_pattern": "6. PT.PCT - {GP}.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_PT_PCT_CT"],
        "bookmark_procedures": ["RecordForm.Tao_PT_PCT_CT"],
        "copy_forward_dependencies": [],
        "notes": "Primary PCT document does not require copy-forward in observed path.",
    },
    {
        "family_code": "INSPECTION_PT_CT",
        "logical_name": "Phieu trinh CT",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [8],
        "template_pattern": "7. PT.CT - {GP}.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_PT_PCT_CT"],
        "bookmark_procedures": ["RecordForm.Tao_PT_PCT_CT"],
        "copy_forward_dependencies": [
            {
                "source_family_code": "INSPECTION_PT_PCT",
                "condition": "If CopyPT is enabled and prior PCT exists, copy bookmark Noidung from prior PCT document.",
                "source_bookmarks": ["Noidung"],
            }
        ],
        "notes": "Observed bookmark-level copy-forward from PT.PCT into PT.CT.",
    },
    {
        "family_code": "CERTIFICATE_DECISION",
        "logical_name": "Quyet dinh cap chung chi",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [9],
        "template_pattern": "8. QD cap CC - {GP}.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_QD_CapCC"],
        "bookmark_procedures": ["RecordForm.Tao_QD_CapCC"],
        "copy_forward_dependencies": [],
        "notes": "Decision document contains conditional suppression for product-type sections and corrective-action timing.",
    },
    {
        "family_code": "CERTIFICATE_ISSUANCE_WORD",
        "logical_name": "Chung chi GPs (Word-scoped baseline)",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [10],
        "template_pattern": "9. Chung chi {GP} (moi).dotx",
        "selection_legacy_mode": "moi",
        "population_procedures": [
            "RecordForm.Tao_CC_GPs_moi",
            "RecordForm.Tao_CC_Thongtinchung",
            "RecordForm.Tao_CC_ThongtinKT",
        ],
        "bookmark_procedures": [
            "RecordForm.Tao_CC_GPs_moi",
            "RecordForm.Tao_CC_Thongtinchung",
            "RecordForm.Tao_CC_ThongtinKT",
        ],
        "copy_forward_dependencies": [],
        "notes": "PowerPoint-backed legacy branch is excluded; current baseline keeps only Word-backed issuance contract.",
    },
    {
        "family_code": "RISK_MANAGEMENT_WORKSHEET",
        "logical_name": "Bang cong cu quan ly rui ro",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [11],
        "template_pattern": "10. Bang cong cu quan ly rui ro.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_BB_QLRR"],
        "bookmark_procedures": ["RecordForm.Tao_BB_QLRR"],
        "copy_forward_dependencies": [],
        "notes": "Only enabled for selected GPs path in observed VBA.",
    },
    {
        "family_code": "STATUS_CONFIRMATION_LETTER",
        "logical_name": "Cong van xac nhan tinh trang",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [12],
        "template_pattern": "a. CV xac nhan tinh trang.dotx",
        "selection_legacy_mode": "cho_kiem_tra_or_cho_cap_chung_chi",
        "population_procedures": ["RecordForm.Tao_CV_XNTT"],
        "bookmark_procedures": ["RecordForm.Tao_CV_XNTT"],
        "copy_forward_dependencies": [],
        "notes": "Template naming branches depend on whether inspection is pending or certificate issuance already exists.",
    },
    {
        "family_code": "NAME_ADDRESS_CHANGE_LETTER",
        "logical_name": "Cong van dong y doi ten dia chi",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [13],
        "template_pattern": "b. CV tra loi dong y doi ten, dia chi.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_CV_Doiten_diachi"],
        "bookmark_procedures": ["RecordForm.Tao_CV_Doiten_diachi"],
        "copy_forward_dependencies": [],
        "notes": "Uses certificate identity and translated company/address text.",
    },
    {
        "family_code": "CHANGE_REPORT_ROUTE_LETTER",
        "logical_name": "Cong van chuyen ho so thay doi cho phong kinh doanh",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [14],
        "template_pattern": "11. Danh gia bao cao thay doi.dotx / c-family legacy letter path",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_CV_ChuyenKD"],
        "bookmark_procedures": ["RecordForm.Tao_CV_ChuyenKD"],
        "copy_forward_dependencies": [],
        "notes": "Observed comments indicate historical ambiguity between change-evaluation minutes and routing letter; treat as review-required family.",
    },
    {
        "family_code": "ASSESSMENT_MINUTES",
        "logical_name": "Bien ban danh gia",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [15],
        "template_pattern": "3.2. Bien ban danh gia {GP}.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_BB_Danhgia"],
        "bookmark_procedures": ["RecordForm.Tao_BB_DGTD"],
        "copy_forward_dependencies": [],
        "notes": "Raw parser misses direct writes in Tao_BB_Danhgia path; nearest proven payload shape comes from assessment-style builder procedures and should be revalidated when templates are available.",
    },
    {
        "family_code": "CONSENT_CHANGE_LETTER",
        "logical_name": "Cong van dong y thay doi",
        "source_application": "Word",
        "storage_scope": "inspection_folder",
        "legacy_host_procedure": "RecordForm.CreateFile",
        "legacy_case_numbers": [16],
        "template_pattern": "d. CV dong y thay doi.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_CV_XNTT"],
        "bookmark_procedures": ["RecordForm.Tao_CV_XNTT"],
        "copy_forward_dependencies": [],
        "notes": "Shares payload builder with status-confirmation letter but uses a different template family.",
    },
    {
        "family_code": "DDKD_PRESENTATION",
        "logical_name": "Phieu trinh cap DDK",
        "source_application": "Word",
        "storage_scope": "dkkd_folder",
        "legacy_host_procedure": "RecordForm.CreateFilez",
        "legacy_case_numbers": [1],
        "template_pattern": "DDKD presentation template family from Get_Tplz case 1",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_PT_cap_DDK"],
        "bookmark_procedures": ["RecordForm.Tao_PT_cap_DDK"],
        "copy_forward_dependencies": [],
        "notes": "Template literal is partially obscured by ChrW concatenation in VBA; bookmark contract is proven.",
    },
    {
        "family_code": "DDKD_CERTIFICATE",
        "logical_name": "Giay DDK",
        "source_application": "Word",
        "storage_scope": "dkkd_folder",
        "legacy_host_procedure": "RecordForm.CreateFilez",
        "legacy_case_numbers": [2],
        "template_pattern": "DDKD certificate template family from Get_Tplz case 2",
        "selection_legacy_mode": None,
        "population_procedures": ["RecordForm.Tao_Giay_DDK"],
        "bookmark_procedures": ["RecordForm.Tao_Giay_DDK"],
        "copy_forward_dependencies": [],
        "notes": "Contains responsible-person and operating-scope bookmarks.",
    },
    {
        "family_code": "DDKD_APPENDIX_OR_DECISION",
        "logical_name": "Phu luc Giay DDK",
        "source_application": "Word",
        "storage_scope": "dkkd_folder",
        "legacy_host_procedure": "RecordForm.CreateFilez",
        "legacy_case_numbers": [3],
        "template_pattern": "z3. Phụ lục GCN ĐĐKKDD.dotx",
        "selection_legacy_mode": "appendix",
        "population_procedures": [
            "RecordForm.Tao_PL_QD_GiayDDK",
            "RecordForm.Tao_PL_QD_GiayDDK_Thongtinchung",
        ],
        "bookmark_procedures": [
            "RecordForm.Tao_PL_QD_GiayDDK",
            "RecordForm.Tao_PL_QD_GiayDDK_Thongtinchung",
        ],
        "copy_forward_dependencies": [],
        "notes": "CreateFilez case 3 resolves the active appendix template.",
    },
    {
        "family_code": "DDKD_APPENDIX_OR_DECISION",
        "logical_name": "Quyet dinh cap DDK",
        "source_application": "Word",
        "storage_scope": "dkkd_folder",
        "legacy_host_procedure": "RecordForm.CreateFilez",
        "legacy_case_numbers": [4],
        "template_pattern": "z4. QĐ cấp ĐĐKKDD.dotx",
        "selection_legacy_mode": "issuance_decision",
        "population_procedures": [
            "RecordForm.Tao_PL_QD_GiayDDK",
            "RecordForm.Tao_PL_QD_GiayDDK_Thongtinchung",
        ],
        "bookmark_procedures": [
            "RecordForm.Tao_PL_QD_GiayDDK",
            "RecordForm.Tao_PL_QD_GiayDDK_Thongtinchung",
        ],
        "copy_forward_dependencies": [],
        "notes": "CreateFilez case 4 resolves the active issuance-decision template.",
    },
    {
        "family_code": "SUPPORT_TRAVEL_AUTHORIZATION",
        "logical_name": "Giay di duong",
        "source_application": "Word",
        "storage_scope": "support_document",
        "legacy_host_procedure": "ExtRecordForm.CreateFile",
        "legacy_case_numbers": [1],
        "template_pattern": "Giay di duong.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["ExtRecordForm.CreateFile"],
        "bookmark_procedures": ["ExtRecordForm.CreateFile"],
        "copy_forward_dependencies": [],
        "notes": "One document can be generated per selected inspector.",
    },
    {
        "family_code": "SUPPORT_FLIGHT_REQUEST",
        "logical_name": "Giay xin di may bay",
        "source_application": "Word",
        "storage_scope": "support_document",
        "legacy_host_procedure": "ExtRecordForm.CreateFile",
        "legacy_case_numbers": [2],
        "template_pattern": "Xin di may bay.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["ExtRecordForm.CreateFile"],
        "bookmark_procedures": ["ExtRecordForm.CreateFile"],
        "copy_forward_dependencies": [],
        "notes": "Uses airport and team composition bookmarks.",
    },
    {
        "family_code": "SUPPORT_ATTENDEE_LIST",
        "logical_name": "Danh sach tham du dot kiem tra",
        "source_application": "Word",
        "storage_scope": "support_document",
        "legacy_host_procedure": "ExtRecordForm.CreateFile",
        "legacy_case_numbers": [3],
        "template_pattern": "Ds tham du dot kiem tra.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["ExtRecordForm.CreateFile"],
        "bookmark_procedures": ["ExtRecordForm.CreateFile"],
        "copy_forward_dependencies": [],
        "notes": "Expands row sections for inspector, VKN, and SYT lists.",
    },
    {
        "family_code": "SUPPORT_DOSSIER_CHECKLIST",
        "logical_name": "Checklist ho so GPs",
        "source_application": "Word",
        "storage_scope": "support_document",
        "legacy_host_procedure": "ExtRecordForm.CreateFile",
        "legacy_case_numbers": [4, 7],
        "template_pattern": "Checklist ho so GPs.dotx / Checklist kiem tra GPs.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["ExtRecordForm.CreateFile"],
        "bookmark_procedures": ["ExtRecordForm.CreateFile"],
        "copy_forward_dependencies": [],
        "notes": "Case 4 and 7 are separate checklist families within ExtRecordForm.",
    },
    {
        "family_code": "SUPPORT_PAYMENT_TRANSFER",
        "logical_name": "Giay xin sec chuyen khoan",
        "source_application": "Word",
        "storage_scope": "support_document",
        "legacy_host_procedure": "ExtRecordForm.CreateFile",
        "legacy_case_numbers": [5, 9],
        "template_pattern": "Giay xin sec chuyen khoan.dotx / Uy quyen thanh toan CTP.dotx",
        "selection_legacy_mode": None,
        "population_procedures": ["ExtRecordForm.CreateFile"],
        "bookmark_procedures": ["ExtRecordForm.CreateFile"],
        "copy_forward_dependencies": [],
        "notes": "Payment-support family covers transfer request and authorization letter variants.",
    },
    {
        "family_code": "SUPPORT_PAYMENT_WORKBOOK",
        "logical_name": "Thanh toan tam ung / De nghi thanh toan",
        "source_application": "Excel",
        "storage_scope": "support_document",
        "legacy_host_procedure": "ExtRecordForm.CreateFile",
        "legacy_case_numbers": [6, 8],
        "template_pattern": "Thanh toan tam ung.xltx / De nghi thanh toan.xltx",
        "selection_legacy_mode": None,
        "population_procedures": ["ExtRecordForm.CreateFile"],
        "bookmark_procedures": [],
        "copy_forward_dependencies": [],
        "notes": "Excel template branch in ExtRecordForm; kept in registry because it is still an active legacy support flow.",
    },
]


def load_raw_contract() -> dict:
    return json.loads(RAW_CONTRACT_PATH.read_text(encoding="utf-8"))


def bookmark_index(raw_contract: dict) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for procedure in raw_contract["procedures"]:
        proc_id = f"{procedure['module']}.{procedure['procedure']}"
        index[proc_id] = sorted(
            {
                *procedure.get("bookmark_writes", []),
                *procedure.get("bookmark_deletes", []),
                *procedure.get("bookmark_exists_checks", []),
                *procedure.get("bookmark_copy_sources", []),
                *procedure.get("bookmark_paste_targets", []),
            },
            key=str.lower,
        )
    return index


def build_entries(raw_contract: dict) -> list[dict]:
    bookmarks_by_procedure = bookmark_index(raw_contract)
    entries: list[dict] = []
    for definition in ENTRY_DEFINITIONS:
        bookmarks: list[str] = []
        for procedure in definition["bookmark_procedures"]:
            bookmarks.extend(bookmarks_by_procedure.get(procedure, []))
        entry = {
            key: value
            for key, value in definition.items()
            if key not in {"bookmark_procedures"}
        }
        entry["bookmarks"] = sorted(set(bookmarks), key=str.lower)
        entries.append(entry)
    return entries


def render_markdown(entries: list[dict]) -> str:
    lines = [
        "# Curated Phase 5 Template Registry",
        "",
        "## Scope",
        "- Evidence source: legacy VBA in `RecordForm.frm`, `ExtRecordForm.frm`, and workbook dispatchers.",
        "- Exclusion: PowerPoint-backed certificate branch is intentionally out of scope.",
        "",
        "## Families",
    ]
    for entry in entries:
        cases = ", ".join(str(value) for value in entry["legacy_case_numbers"])
        population = ", ".join(entry["population_procedures"])
        copy_info = "none"
        if entry["copy_forward_dependencies"]:
            copy_info = "; ".join(
                f"{item['source_family_code']} ({item['condition']})"
                for item in entry["copy_forward_dependencies"]
            )
        lines.append(
            f"- `{entry['family_code']}`: {entry['logical_name']} | host=`{entry['legacy_host_procedure']}` "
            f"| case=`{cases}` | template=`{entry['template_pattern']}` | population=`{population}` "
            f"| legacy_mode=`{entry['selection_legacy_mode'] or '*'}` "
            f"| bookmarks={len(entry['bookmarks'])} | copy-forward={copy_info}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    raw_contract = load_raw_contract()
    entries = build_entries(raw_contract)
    payload = {
        "scope_exclusions": ["PowerPoint-backed certificate flow"],
        "entries": entries,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_MD.write_text(render_markdown(entries), encoding="utf-8")


if __name__ == "__main__":
    main()
