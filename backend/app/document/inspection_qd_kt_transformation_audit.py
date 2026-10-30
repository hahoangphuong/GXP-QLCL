"""Deterministic repository-only audit projection, not a payload/approval schema.

Extends the captured legacy inventory by reference; never replaces its historical
8 BLOCKED / 6 PARTIAL owner classifications or reads live business data.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from backend.app.document.inspection_qd_kt_provenance_gate import (
    SOURCE, INVENTORY_SEMANTIC_SHA256, TRACE_SEMANTIC_SHA256,
    EXPECTED_FIELDS, load_qdkt_source_provenance, read_provenance_json, semantic_sha256,
)
from backend.app.document.inspection_qd_kt_template_asset_contract import load_inspection_qd_kt_template_assets
from backend.app.document.inspection_qd_kt_vba_bookmark_series import reconcile_qdkt_i2_bookmarks
from backend.app.document.inspection_qd_kt_runtime_provenance import load_runtime_source_evidence, RUNTIME_EVIDENCE_SHA256
from backend.app.document.inspection_qd_kt_runtime_identity import runtime_identity_chain

ROOT = Path(__file__).resolve().parents[3]
OBSERVATION = ROOT / "tests/fixtures/inspection_qd_kt_observed_template_binaries.json"
REPORT = ROOT / "artifacts/legacy_audit/inspection_qd_kt_transformation_audit.json"
OBSERVATION_SHA256 = "3bbd80effa08441c565e44ff25b98ead46a065f6f08d9c18e242b2ab45ec0ad5"
HELPERS = ROOT / "tests/fixtures/inspection_qd_kt_transform_helper_evidence.json"
HELPERS_SHA256 = "50e09014a07f265f5c2bca8619b0062438bed827582db1a56592e014dda4fb9a"
_HELPER_FOR = {"Tencoso": "DelLastIf_Ins", "Diadiemx": "LCase_FirstChar", "Diachicoso": "Del_LastPeriod"}


class QdKtTransformationAuditBlocked(ValueError):
    pass


# Reviewed source-to-current-contract annotations, not executable transforms.
# A status describes full current source/transform equivalence, never Word UAT.
_SPECS = {
    "Fulldate": {
        "status": "CONTRADICTED", "groups": ["DATES"],
        "canonical_candidate": "No Process A issuance date source is authorized.",
        "ownership": "VBA workstation intrinsic Date has no Case/Site/Plan owner; do not substitute Case dates or server clock.",
        "transform": "Module1.FormatDateS(Date, 1): IsDate then dd tháng MM năm yyyy; invalid date returns NulStr. RecordForm calls the exact unnumbered target.",
        "missing": "Process A preserves the template's blank issuance date; absence of Fulldate does not prove a visually blank date line.",
        "multiple": "No latest record or file creation timestamp may supply an issuance date.",
        "date_time": "Workstation calendar Date is distinct from backend clock, generated_at, Case dates and legal issuance. Business timezone is unproven.",
        "difference": "Legacy attempts a workstation-date write; confirmed current Process A policy requires blank issuance date. All four observed templates lack this target.",
        "blockers": ["QDKT_DRAFT_DATE_POLICY_CONFLICT", "BLANK_ISSUANCE_DATE_BOOKMARK_UNVERIFIED", "QDKT_BUSINESS_TIMEZONE_UNPROVEN"],
        "needed": ["Owner-approved blank-date layout and handling of literal template year", "Actual Word visual evidence for four variants"],
        "refs": ["Module1.bas:2042-2052", "RecordForm.frm:743", "docs/INSPECTION_QD_KT_CONFIRMED_BUSINESS_RULES_20261022.md:Ngày trên bản dự thảo"],
    },
    "Tencoso": {
        "status": "PARTIAL", "groups": ["SITE_NAME"],
        "canonical_candidate": "Site.site_name via persisted Case.site_id; candidate only, not a complete QĐKT name atom.",
        "ownership": "Primary Module1 entry uses merged planning-row cell 4; MainForm alternate uses db_cso. Modern Case-to-Site is canonical, but name/format selection is not closed.",
        "transform": "DelLastIf_Ins(cell 4, vbCrLf); supplementary add-in helper removes trailing characters in the CR/LF set, not embedded lines/general whitespace. Replace_Bookmark bounds 1..8 repeats the same TenCtydd value.",
        "missing": "Legacy empty text exits without replacement. No backend default to company name, parent company or another Site is approved.",
        "multiple": "Read one Case-linked Site; series target count is not a multi-Site selection rule.",
        "date_time": "Not a date field.",
        "difference": "Three observed numbered targets receive identical text; source-row/name/title equivalence and Word line wrapping remain partial.",
        "blockers": ["QDKT_SITE_NAME_SOURCE_EQUIVALENCE_PARTIAL", "QDKT_NAME_FORMATTING_UNPROVEN"],
        "needed": ["Owner-approved current Site-name snapshot/normalization rule", "Four-variant Word name/line-wrap acceptance"],
        "refs": ["Module1.bas:607", "MainForm.frm:4151", "RecordForm.frm:744", "RecordForm.frm:589-603"],
    },
    "Diadiem": {
        "status": "BLOCKED", "groups": ["LOCATION"],
        "canonical_candidate": "Case-linked Site.province_name is a candidate province, not automatically a legal locality string.",
        "ownership": "Legacy selected planning-row cell 10; modern registered province is Case -> Site. Their live-value equivalence is not proven.",
        "transform": "Only when a comma exists: take suffix, trim, remove province/city prefixes and periods case-insensitively; then HCM alias rewrite; Dia_danh Match index.",
        "missing": "Legacy missing Match becomes 0; modern unknown/absent province blocks, never defaults to a northern province.",
        "multiple": "Require exactly one legacy-reference match; no first match or alphabetic comparison.",
        "date_time": "Not a date field.",
        "difference": "Attested-legacy locality projection exists but does not establish current Case equivalence; legal locality and registered address are different concepts. Exact Diadiem is absent in all originals.",
        "blockers": ["LOCATION_BOOKMARK_FORMAT_UNPROVEN", "LEGACY_PROVINCE_MAPPING_UNPROVEN"],
        "needed": ["Owner-approved Case locality source and prefix/alias/character rules", "Evidence for current versus historical province mapping"],
        "refs": ["Module1.bas:614-632", "RecordForm.frm:745", "backend/app/document/inspection_qd_kt_locality_projection.py:project_qdkt_locality_from_attested_legacy"],
    },
    "Diadiemx": {
        "status": "BLOCKED", "groups": ["LOCATION"],
        "canonical_candidate": "Attested legacy Dia_danh_x prefix plus province; no approved Site-to-legal-place display contract.",
        "ownership": "Planning province lookup via Dia_danh/Dia_danh_x, not address parsing or a free-text plan fallback.",
        "transform": "If Match > 0, Index(Dia_danh_x,index,2) + province, else raw province; replace TP prefix; LCase_FirstChar call; numbered targets 1..3. Supplementary add-in helper lowercases only the first character and preserves the rest.",
        "missing": "Legacy falls back to province on missing lookup; backend does not certify that fallback for a modern Case.",
        "multiple": "One unique source reference entry; missing numbered target is a legacy no-op, not a reason to choose another province.",
        "date_time": "Not a date field.",
        "difference": "GLP/GMP have three effective targets; GMPbb/GSP have two. Existing attested projection leaves case_source_equivalence_verified=false.",
        "blockers": ["LOCATION_BOOKMARK_FORMAT_UNPROVEN", "QDKT_PLANNING_ROW_PROVINCE_UNATTESTED"],
        "needed": ["Owner-approved current locality display and Case binding", "Word acceptance of numbered target formatting"],
        "refs": ["Module1.bas:626-632", "RecordForm.frm:746", "backend/app/document/inspection_qd_kt_locality_projection.py:project_qdkt_locality_from_attested_legacy"],
    },
    "Diachicoso": {
        "status": "CONTRADICTED", "groups": ["LOCATION"],
        "canonical_candidate": "Persisted Site.site_address via Case.site_id and read_qdkt_registered_site.",
        "ownership": "Current owner explicitly selected registered Site address; legacy primary entry reads planning-row cell 11.",
        "transform": "Replace CRLF with semicolon, then Del_LastPeriod. Supplementary add-in helper removes exactly one trailing period, without Trim or lone-LF cleanup. This is not approved current address normalization.",
        "missing": "Current reader blocks missing/untrimmed registered address or absent Case/Site join; never falls back to plan cells.",
        "multiple": "One Case-linked Site; no address concatenation or selection from another Case.",
        "date_time": "Not a date field.",
        "difference": "The legacy and approved current source owners differ by design. Exact target is absent in all four originals; no current punctuation/layout acceptance exists.",
        "blockers": ["QDKT_ADDRESS_SOURCE_POLICY_CONFLICT", "LOCATION_BOOKMARK_FORMAT_UNPROVEN"],
        "needed": ["Owner-approved registered-address presentation without importing planning-row assumptions", "Word layout acceptance or intentional no-op decision"],
        "refs": ["Module1.bas:612", "RecordForm.frm:747", "backend/app/document/inspection_qd_kt_registered_site.py:read_qdkt_registered_site", "docs/INSPECTION_QD_KT_CONFIRMED_BUSINESS_RULES_20261022.md:Địa chỉ và địa danh"],
    },
    "HsDK": {
        "status": "PARTIAL", "groups": ["DOSSIER"],
        "canonical_candidate": "Current persisted CaseApplication.dossier_code, through read_dossier_snapshot.",
        "ownership": "Case/Application/Site canonical UUID/version join is separate from historical selected Rg3 row identity. Module1 entry does not reload this public variable.",
        "transform": "Exact unnumbered HsDK write of s_MaHsDk; GetTT_Ktra reads the selected db_ktra row column ColDB_HSDK_Ktra+1 (I). No coercion from a similar field name.",
        "missing": "Legacy empty text is silently skipped; current dossier gate blocks absent/blank code and identity/version conflicts.",
        "multiple": "Current CaseApplication snapshot only; no legacy row, prior Case or latest unrelated application fallback.",
        "date_time": "Dossier code is not a date or issuance number.",
        "difference": "Dossier semantics are source-proven; public-state freshness at the planning entry is not. Target absent in all originals; A/B owner choice still required.",
        "blockers": ["QDKT_DOSSIER_TARGET_ABSENT", "QDKT_LEGACY_PUBLIC_STATE_LIFETIME_UNPROVEN"],
        "needed": ["Legal A/B wording/placement or intentional omission approval", "Candidate version/checksum and Word UAT"],
        "refs": ["RecordForm.frm:334-343", "RecordForm.frm:748", "backend/app/document/inspection_qd_kt_renderer_contract.py:read_dossier_snapshot", "artifacts/legacy_audit/inspection_qd_kt_dossier_bookmark_source_evidence.json"],
    },
    "NgaynopHsDK": {
        "status": "PARTIAL", "groups": ["DOSSIER", "DATES"],
        "canonical_candidate": "Current persisted CaseApplication.submitted_on: timestamp with timezone, not date-only.",
        "ownership": "Same Case/Application/Site/version snapshot as dossier code; db_ktra H is submission date, not automatically receipt date.",
        "transform": "GetTT_Ktra reads H; writer only replaces '-' with '/'. It does not define business timezone or normalize a backend timestamp.",
        "missing": "Missing/naive/ambiguous timestamp or UNDECIDED rule blocks. Never use today, file time, received_at or created_at.",
        "multiple": "Require the matching application snapshot/version; no mixed code/date from different records.",
        "date_time": "Date-only and aware timestamp are separate representations; recorded-offset date is only an explicit proposal. PostgreSQL session offset can change calendar day; timezone remains unproven.",
        "difference": "Semantic submission-date evidence exists, but DB representation/display policy and absent target prevent full equivalence.",
        "blockers": ["QDKT_DOSSIER_TARGET_ABSENT", "QDKT_BUSINESS_TIMEZONE_UNPROVEN", "QDKT_DATE_NORMALIZATION_UNAPPROVED"],
        "needed": ["Business owner date normalization/display decision", "Legal A/B decision and actual Word UAT"],
        "refs": ["RecordForm.frm:343", "RecordForm.frm:749", "backend/app/document/inspection_qd_kt_renderer_contract.py:normalize_submission_date", "docs/QDKT_RENDERER_DECISION_WORD_UAT.md:Confirmed lineage and date contract"],
    },
    "QDKT": {
        "status": "CONTRADICTED", "groups": ["DECISION"],
        "canonical_candidate": "Process B only: Case/Plan-bound InspectionDecision.reference selected by proven REPLACES lineage.",
        "ownership": "Persisted Case -> InspectionPlan -> source decision, never scalar projection fallback or identity-map state. No such atom belongs in Process A.",
        "transform": "GetTT_Ktra splits combined db_ktra decision cell into first token and trailing date; malformed/no separator leaves reference string. Writer attempts exact QDKT.",
        "missing": "No source rows or incomplete/ambiguous chain blocks. Process A must not inherit an existing reference; planning entry does not reload this public variable.",
        "multiple": "Use #191 complete single-root/REPLACES chain, no MAX(id), MAX(date), insertion order, unknown amendments or scalar projection.",
        "date_time": "Reference text is not evidence of legal issuance.",
        "difference": "Legacy i=2 attempts a reference write while current draft policy excludes issued reference/date. Exact target absent; persisted source is not external issuance proof.",
        "blockers": ["QDKT_DRAFT_ISSUED_REFERENCE_POLICY_CONFLICT", "QDKT_LEGAL_ISSUANCE_EVIDENCE_UNPROVEN"],
        "needed": ["Approved external issuance evidence contract for Process B", "Keep Process A reference absent; resolve unsupported lifecycle policy"],
        "refs": ["RecordForm.frm:374-384", "RecordForm.frm:790", "backend/app/document/inspection_qd_kt_decision_source.py:read_latest_qdkt_reference_for_case", "backend/app/document/inspection_qd_kt_case_readiness.py:inspect_qdkt_case_readiness"],
    },
    "NgayQDKT": {
        "status": "CONTRADICTED", "groups": ["DECISION", "DATES"],
        "canonical_candidate": "Process B only: date-only InspectionDecision.decision_on from the same selected source as reference.",
        "ownership": "Same Case/Plan/decision atoms and lineage; never Case creation date, file date, backend clock or prior Case.",
        "transform": "Trailing token of legacy combined cell, or empty string when no delimiter; exact NgayQDKT write. No timestamp/date-only conversion is justified by this split.",
        "missing": "Process A has no issuance-date atom; Process B missing date blocks. Empty legacy text skips replacement without proving a blank Word date.",
        "multiple": "Reference and date stay paired to one source ID; replacement date cannot precede predecessor; same-day requires explicit lineage.",
        "date_time": "Source decision_on is date-only and distinct from aware CaseApplication submission time. Legal issuance is still unverified.",
        "difference": "Legacy attempted write conflicts with blank draft-date policy; exact target absent in originals. No automatic legal-issued status follows from persistence.",
        "blockers": ["QDKT_DRAFT_DATE_POLICY_CONFLICT", "QDKT_LEGAL_ISSUANCE_EVIDENCE_UNPROVEN"],
        "needed": ["External issuance evidence for Process B", "Owner/Word proof of Process A blank administrative date"],
        "refs": ["RecordForm.frm:374-384", "RecordForm.frm:790", "backend/app/document/inspection_qd_kt_decision_source.py:require_latest_qdkt_reference"],
    },
    "VKNx": {
        "status": "BLOCKED", "groups": ["AUTHORITY"],
        "canonical_candidate": "Dedicated manufacture-kind + source-proven province-zone atoms; no canonical classification extraction owner is established.",
        "ownership": "Case/Site manufacturing classification remains unresolved; never infer from facility name, team or free-text scope. Legacy primary entry sets Daychuyen, while Get_VKN reads public DaychuyenDD.",
        "transform": "For Sel_GPs 1/2: Get_VKN detects four vaccine strings in DaychuyenDD, else legacy province index <=32 versus >32; generates full institute prose.",
        "missing": "Legacy missing Match index 0 falls into north branch; current unknown classification/mapping blocks. No northern default.",
        "multiple": "One uniquely mapped province and explicit classification; no first mapping, lexical ordering or current administrative-code substitution.",
        "date_time": "Historical 63-province reference is not a current administrative-date policy.",
        "difference": "Pure authority text and legacy geography helpers exist, but their source atoms are not thereby owner-approved. GMPbb target exists yet branch is not reached; GSP has no target.",
        "blockers": ["MANUFACTURING_CLASSIFICATION_SOURCE_UNPROVEN", "LEGACY_PROVINCE_MAPPING_UNPROVEN", "QDKT_LEGACY_PUBLIC_STATE_LIFETIME_UNPROVEN"],
        "needed": ["Approved canonical vaccine/biological classification source and variant applicability", "Accepted historical/current geography and exact institute prose"],
        "refs": ["Module1.bas:626,637", "RecordForm.frm:750-752", "RecordForm.frm:1854-1871", "backend/app/document/inspection_qd_kt_vkn_authority.py:select_qdkt_vkn_authority", "backend/app/document/inspection_qd_kt_legacy_province_band.py:classify_qdkt_legacy_province_zone"],
    },
    "VKN": {
        "status": "BLOCKED", "groups": ["AUTHORITY"],
        "canonical_candidate": "Same dedicated authority atoms as VKNx; abbreviated institution text, not an inspector name.",
        "ownership": "No manufacture enum may be inferred from company names or accepted from a counterfeit Python equality callback.",
        "transform": "Get_VKN second output s2; Sel_GPs 1/2 and i=2; helper bounds 1..2 writes VKN1/VKN2, not the unnumbered VKN bookmark.",
        "missing": "Missing manufacturing classification or medicine province mapping blocks; vaccine may use declared UNPROVEN geography, never an unknown enum.",
        "multiple": "Same exact classification/zone selection as VKNx; no independent institution guess for the abbreviation.",
        "date_time": "Not a date field.",
        "difference": "GLP/GMP numbered targets are effective; base VKN is not used by this helper invocation. GMPbb/GSP branch is not applicable even if a similarly named bookmark exists.",
        "blockers": ["MANUFACTURING_CLASSIFICATION_SOURCE_UNPROVEN", "QDKT_AUTHORITY_PROSE_ACCEPTANCE_UNPROVEN"],
        "needed": ["Canonical classification owner", "Owner acceptance of exact abbreviation/full-name pair and variant policy"],
        "refs": ["RecordForm.frm:752", "RecordForm.frm:1854-1871", "backend/app/document/inspection_qd_kt_vba_bookmark_series.py:reconcile_qdkt_i2_bookmarks"],
    },
    "TT3x": {
        "status": "PARTIAL", "groups": ["TEAM"],
        "canonical_candidate": "Case-owned ordered InspectionTeamMember rows plus separately reviewed draft roster/version/title evidence.",
        "ownership": "Case team is not an approved decision-specific roster. Member identity/order does not prove titles, positions or Word text.",
        "transform": "TTVForm.Get_TTV_List3 composes degree/prefix + cleaned name (remove '*' and 'PCT. ') + ' - ' + title + ', ' + unit. Writer splits TTVdd by '|', trims third entry, adds TT_ext + CRLF for later entries and writes TT3x only when UBound >1.",
        "missing": "Legacy On Error Resume Next/empty text can leave placeholders. Modern missing/empty/unstable team or absent required extension blocks.",
        "multiple": "Exactly one Case team and unique ordered members; preserve source order, do not reorder by name/title/ID.",
        "date_time": "Roster-at-draft/version evidence is separate from current team and issue date.",
        "difference": "Legacy formatted TTVdd comes through TTVForm; modern display_name/role_code alone cannot reproduce degree/title/position and template fragment formatting.",
        "blockers": ["INSPECTION_TEAM_BOOKMARK_CONTRACT_UNRESOLVED", "QDKT_TEAM_WORD_FORMAT_UNPROVEN"],
        "needed": ["Source-attested TTVForm formatting/title provenance", "Exact TT_ext fragment and real Word roster/layout acceptance"],
        "refs": ["Module1.bas:639-645", "TTVForm.frm:148-155,329-340,380-428,494-527", "RecordForm.frm:754-765", "backend/app/document/inspection_qd_kt_team_layout_instructions.py:plan_qdkt_team_layout"],
    },
    "TT3Del": {
        "status": "PARTIAL", "groups": ["TEAM"],
        "canonical_candidate": "Same ordered Case team and draft roster evidence; no write payload is a deletion instruction.",
        "ownership": "Deletion predicate must bind to the same reviewed roster/version and template span, never another decision's team.",
        "transform": "When UBound(Split(TTVdd,'|'))<=1, Delete_Bookmark.Range.Delete of TT3Del; DELETE has no value expression.",
        "missing": "Missing target is silently ignored in VBA; current deletion span/format must remain fail-closed until verified.",
        "multiple": "Member count/order and third-member span evidence are required; a current count does not approve a prior draft.",
        "date_time": "Not an issuance-date source.",
        "difference": "Physical presence and count predicate are proven facts; deleting a Word range with legal surrounding text still requires span/visual acceptance.",
        "blockers": ["INSPECTION_TEAM_BOOKMARK_CONTRACT_UNRESOLVED", "QDKT_THIRD_MEMBER_DELETION_ACCEPTANCE_UNPROVEN"],
        "needed": ["Approved deletion span and roster binding", "Word proof for short and extended rosters"],
        "refs": ["RecordForm.frm:576-587", "RecordForm.frm:754-766", "backend/app/document/inspection_qd_kt_third_member_span.py"],
    },
    "TTx": {
        "status": "PARTIAL", "groups": ["TEAM"],
        "canonical_candidate": "Ordered Case team members with separately attested legacy formatted display/title provenance.",
        "ownership": "Process A uses proposed Case team; Process B needs approved decision-specific evidence. No automatic conversion between them.",
        "transform": "k=0..1 while within UBound: exact dynamic names TT1x/TT2x and Trim(Ds_TTV(k)). TTx itself is not a physical target.",
        "missing": "Legacy may leave later placeholders when tokens are missing; modern pure layout gate conservatively requires a complete attested display, not guessed blank members.",
        "multiple": "Backend requires explicit stable sort_order/unique identities. Legacy Get_TTV_Index follows comma-token order and picks the first normalized name match; unmatched names are omitted by Get_TTV_List3. Do not import that name lookup as canonical identity.",
        "date_time": "Draft snapshot/version is distinct from legal issuance and current member metadata.",
        "difference": "Physical target mapping is proven; formatted legacy role/title strings and Word paragraph layout remain unresolved despite correct DB membership.",
        "blockers": ["INSPECTION_TEAM_BOOKMARK_CONTRACT_UNRESOLVED", "QDKT_TEAM_TITLE_PROVENANCE_UNPROVEN"],
        "needed": ["Owner-approved identity/title/position composition", "Version-bound roster and four-variant Word acceptance"],
        "refs": ["Module1.bas:639-645", "TTVForm.frm:148-155,329-340,380-397", "RecordForm.frm:754-759", "backend/app/document/inspection_qd_kt_team_source.py:read_qdkt_team_source", "backend/app/document/inspection_qd_kt_team_snapshot_review.py"],
    },
}

_BACKEND_FILES = [
    "inspection_qd_kt_runtime_identity.py",
    "inspection_qd_kt_vba_bookmark_series.py", "inspection_qd_kt_runtime_provenance.py",
    "inspection_qd_kt_case_readiness.py", "inspection_qd_kt_case_source_bundle.py",
    "inspection_qd_kt_registered_site.py", "inspection_qd_kt_team_source.py",
    "inspection_qd_kt_decision_source.py", "inspection_qd_kt_vkn_authority.py",
    "inspection_qd_kt_legacy_province_band.py", "inspection_qd_kt_locality_projection.py",
    "inspection_qd_kt_renderer_contract.py", "inspection_qd_kt_team_layout_instructions.py",
]

# Reuse existing owner regressions instead of rebuilding #186/#191 contracts.
_REGRESSIONS = [
    ("CROSS_CASE", "HIGH", "Decision from another Case", "test_inspection_qd_kt_lifecycle_integrity.py::test_cross_case_decision_cannot_be_composed_with_local_site_and_team", "Reject mismatched source scope", "Persisted Case/Plan ownership"),
    ("WRONG_SITE", "HIGH", "Registered Site association differs", "test_inspection_qd_kt_registered_site.py::test_qdkt_case_uses_only_its_registered_site_address", "Read only the Case-linked Site; no fallback", "Canonical registered Site relation"),
    ("STALE_PROJECTION", "HIGH", "Scalar projection disagrees or source row is absent", "test_inspection_qd_kt_decision_source.py::test_missing_or_stale_scalar_projection_never_silently_falls_back", "DECISION_PROJECTION_MISMATCH or missing-source blocker", "Matching persisted source row and projection"),
    ("MULTIPLE_DECISIONS", "HIGH", "Ambiguous decision lineage", "test_inspection_qd_kt_latest_reference.py::test_missing_or_ambiguous_replacement_history_blocks", "Reject incomplete/branched/circular histories", "Owner-approved explicit lifecycle; no MAX/date heuristic"),
    ("MISSING_ATOM", "HIGH", "Canonical application atom absent", "test_inspection_qd_kt_renderer_contract.py::test_canonical_provenance_negative_paths", "Block before dispatch; never manufacture values", "Matching Case/Application/Site/version source"),
    ("NULL_DEFAULT", "HIGH", "Missing registered address", "test_inspection_qd_kt_registered_site.py::test_missing_or_unapproved_address_cannot_be_guessed", "REGISTERED_SITE_ADDRESS_MISSING", "Approved registered address; no plan default"),
    ("UNKNOWN_ENUM", "HIGH", "Unknown geography or counterfeit classification", "test_inspection_qd_kt_transformation_audit.py::test_foreign_classification_cannot_masquerade_as_vaccine", "Reject invalid enum/type before comparisons", "Explicit canonical manufacturing classification"),
    ("DATE_ONLY_TIMESTAMP", "HIGH", "Date-only/timestamp representation conflict", "test_inspection_qd_kt_renderer_contract.py::test_ambiguous_or_unsupported_date_transform_is_rejected", "No implicit date-to-timestamp conversion", "Owner-approved source date/display policy"),
    ("TIMEZONE", "HIGH", "Equal instants have different recorded calendar days", "test_inspection_qd_kt_renderer_contract.py::test_equal_instants_with_different_recorded_calendar_days_conflict", "No server timezone or guessed conversion", "Business timezone decision and boundary-case UAT"),
    ("UNKNOWN_PROVINCE", "HIGH", "No unique legacy province mapping", "test_inspection_qd_kt_legacy_province_band.py::test_unsupported_classification_or_legacy_location_fails_closed", "LEGACY_PROVINCE_MAPPING_UNPROVEN", "Source-proven applicable geography; no alphabetic rule"),
    ("MISSING_MANUFACTURE", "HIGH", "Manufacturing classification UNPROVEN", "test_inspection_qd_kt_vkn_authority.py::test_unproven_source_classification_never_guesses_institution", "MANUFACTURE_CLASSIFICATION_UNPROVEN", "Canonical classification owner; not company-name guessing"),
    ("TEAM_ORDER", "HIGH", "Ambiguous or unsorted member order", "test_inspection_qd_kt_team_source.py::test_unproven_source_fails_closed", "Reject unstable order/identity/role", "Explicit ordered roster and draft/version link"),
    ("UNPROVEN_FORMAT", "HIGH", "Correct DB members do not prove formatted Word strings", "test_inspection_qd_kt_transformation_audit.py::test_all_14_fields_remain_unverified_and_have_complete_audit_dimensions", "No VERIFIED or legal-equivalence promotion", "Title/position/unit/paragraph evidence plus Word UAT"),
    ("MISSING_TARGET", "HIGH", "VBA attempts target absent from original DOTX", "test_inspection_qd_kt_transformation_audit.py::test_exact_absence_and_numbered_target_facts_are_not_conflated", "Report source no-op, keep owner blocker", "A/B wording/placement or omission acceptance"),
    ("DUPLICATE_TARGET", "HIGH", "Duplicate physical bookmark name", "test_inspection_qd_kt_dotx_binary_audit.py::test_duplicate_bookmark_names_across_ids_fail_closed", "Reject ambiguous physical structure", "Independent valid primary byte audit"),
    ("FALSE_VERIFIED", "HIGH", "Audit status/ready flag edited without evidence", "test_inspection_qd_kt_transformation_audit.py::test_committed_report_cannot_self_promote", "QDKT_TRANSFORMATION_AUDIT_REPORT_DRIFT", "Reviewed source changes, owner approval and actual Word UAT"),
]


def build_qdkt_transformation_audit(*, source_path: Path = SOURCE, observation_path: Path = OBSERVATION, helper_path: Path = HELPERS) -> dict:
    """Repository evidence only. No Case queries, clock defaults or render calls."""
    inventory = load_qdkt_source_provenance(source_path)
    runtime = load_runtime_source_evidence()
    helpers = read_provenance_json(helper_path)
    if semantic_sha256(helpers) != HELPERS_SHA256:
        raise QdKtTransformationAuditBlocked("QDKT_AUDIT_HELPER_SOURCE_DRIFT")
    observed = read_provenance_json(observation_path)
    rows = observed.get("templates")
    assets = {a.gxp_type: a for a in load_inspection_qd_kt_template_assets()}
    if type(rows) is not list or len(rows) != 4 or any(type(row) is not dict for row in rows):
        raise QdKtTransformationAuditBlocked("QDKT_AUDIT_TEMPLATE_SET_INVALID")
    if any(type(row.get("gxp_type")) is not str for row in rows) or {row["gxp_type"] for row in rows} != set(assets):
        raise QdKtTransformationAuditBlocked("QDKT_AUDIT_TEMPLATE_SET_INVALID")
    for row in rows:
        names = row.get("bookmark_names")
        if type(names) is not list or any(type(n) is not str for n in names) or len(set(names)) != len(names):
            raise QdKtTransformationAuditBlocked("QDKT_AUDIT_PHYSICAL_TARGET_AMBIGUOUS")
        if row.get("sha256") != assets[row["gxp_type"]].checksum_sha256:
            raise QdKtTransformationAuditBlocked("QDKT_AUDIT_TEMPLATE_SHA_CONFLICT")
    if semantic_sha256(observed) != OBSERVATION_SHA256:
        raise QdKtTransformationAuditBlocked("QDKT_AUDIT_PHYSICAL_OBSERVATION_DRIFT")
    result = []
    for name in sorted(EXPECTED_FIELDS):
        legacy, spec = inventory["fields"][name], deepcopy(_SPECS[name])
        active = [op for op in legacy["vba_rendered_operations"] if op["reachability_i2"] != "UNREACHABLE_I2"][0]
        physical = []
        for row in sorted(rows, key=lambda r: r["gxp_type"]):
            operations = reconcile_qdkt_i2_bookmarks(row["gxp_type"], row["bookmark_names"])
            if name in operations:
                op = operations[name]
                candidates, effective, reachable = op.candidate_targets, op.effective_targets, op.branch_reachable
            else:
                candidates, reachable = (name,), True
                effective = tuple(n for n in candidates if n in row["bookmark_names"])
            physical.append({"gxp_type": row["gxp_type"], "candidate_targets": list(candidates), "effective_targets": list(effective), "branch_reachable": reachable,
                "missing_targets": [n for n in candidates if reachable and n not in effective], "word_equivalence_verified": False})
        source_refs = sorted({f"{step['file']}:{step['line']}" for chain in legacy["provenance_chain"] for step in chain["steps"]})
        if name in _HELPER_FOR:
            helper = helpers["functions"][_HELPER_FOR[name]]
            source_refs.append(f"legacy/GPs.xlam!WinAPI.bas:{helper['start_line']}-{helper['end_line']} (supplementary version)")
        result.append({
            "logical_operation": name, "operation_type": active["operation_type"],
            "legacy_source_expression": active["expression"], "legacy_transformation": spec["transform"],
            "legacy_source_endpoint": legacy["source_semantic_endpoint"], "legacy_owner_classification": legacy["owner_classification"],
            "canonical_candidate": spec["canonical_candidate"], "ownership": spec["ownership"],
            "null_missing_behavior": spec["missing"], "multiple_record_behavior": spec["multiple"], "date_time_handling": spec["date_time"],
            "differences": spec["difference"], "status": spec["status"], "groups": spec["groups"],
            "blocker_codes": sorted(spec["blockers"]), "owner_evidence_needed": spec["needed"],
            "evidence_refs": sorted(set(source_refs + spec["refs"])), "physical_targets": physical,
            "runtime_source_reference": runtime["operation_source_lines"][name],
            "ready_to_render": False,
        })
    groups, blockers = defaultdict(list), defaultdict(list)
    for row in result:
        for group in row["groups"]:
            groups[group].append(row["logical_operation"])
        for code in row["blocker_codes"]:
            blockers[code].append(row["logical_operation"])
    try:
        # Source identity must survive Git's Windows CRLF checkout conversion.
        module_hashes = {f"backend/app/document/{name}": sha256((Path(__file__).parent / name).read_text(encoding="utf-8").encode("utf-8")).hexdigest() for name in _BACKEND_FILES}
    except OSError as exc:
        raise QdKtTransformationAuditBlocked("QDKT_AUDIT_BACKEND_SOURCE_UNAVAILABLE") from exc
    return {
        "schema_version": "inspection-qd-kt-input-provenance-audit/v1",
        "extends_inventory": "artifacts/legacy_audit/inspection_qd_kt_input_provenance.json",
        "inventory_semantic_sha256": INVENTORY_SEMANTIC_SHA256, "trace_semantic_sha256": TRACE_SEMANTIC_SHA256,
        "source_zip_sha256": inventory["source_zip_sha256"], "physical_observation_semantic_sha256": OBSERVATION_SHA256,
        "supplementary_helper_evidence": {"path": "tests/fixtures/inspection_qd_kt_transform_helper_evidence.json", "semantic_sha256": HELPERS_SHA256, "source_binary_sha256": helpers["source_binary_sha256"], "limitation": helpers["limitation"]},
        "runtime_source_provenance": {"evidence_class": "PINNED_STATIC_PRIMARY_CAPTURE_NOT_CURRENT_LOCAL_VERIFICATION",
            "path": "tests/fixtures/inspection_qd_kt_runtime_source_evidence.json", "semantic_sha256": RUNTIME_EVIDENCE_SHA256,
            "capture": runtime},
        "runtime_identity_chain": runtime_identity_chain(),
        "call_chain": inventory["call_chain"], "logical_operation_count": len(result),
        "physical_evidence_kind": "COMMITTED_PRIMARY_BINARY_OBSERVATION_NOT_FRESH_BINARY_OR_WORD_EXECUTION",
        "backend_source_utf8_lf_sha256": module_hashes,
        "fields": result,
        "status_counts": {s: sum(row["status"] == s for row in result) for s in ("VERIFIED", "PARTIAL", "BLOCKED", "CONTRADICTED")},
        "legacy_owner_counts": dict(sorted(Counter(row["legacy_owner_classification"] for row in result).items())),
        "groups": dict(sorted(groups.items())), "blocker_inventory": dict(sorted(blockers.items())),
        "adversarial_regressions": [{"case": name, "risk": risk, "defect_or_unproven_behavior": problem, "test_reference": "tests/" + test,
            "expected_fail_closed_outcome": outcome, "evidence_required": evidence} for name, risk, problem, test, outcome, evidence in _REGRESSIONS],
        "process_a": "No issued reference/date; preserve blank administrative date; no latest decision inheritance.",
        "process_b": "Case/Plan-bound lineage is diagnostic; external legal issuance remains unverified.",
        "decision": "UNDECIDED", "word_uat": "NOT_EXECUTED", "business_timezone": "PARTIAL_UNPROVEN_BUSINESS_TIMEZONE",
        "ready_to_render": False, "legal_equivalence_verified": False,
        "limitations": ["Static source evidence is not a live Case mapping or authorization", "Physical presence/absence is not visual Word parity", "No owner A/B, date/timezone, wording or placement approval supplied", "No production DB/NAS/GCS/Word access", "Public-variable lifetime at Module1 entry is unproven; no fabricated initialization"],
    }


def validate_qdkt_transformation_report(path: Path = REPORT) -> dict:
    report = read_provenance_json(path)
    expected = build_qdkt_transformation_audit()
    if semantic_sha256(report) != semantic_sha256(expected):
        raise QdKtTransformationAuditBlocked("QDKT_TRANSFORMATION_AUDIT_REPORT_DRIFT")
    return report


def transformation_audit_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def transformation_audit_markdown(report: dict) -> str:
    lines = ["# QĐKT — 14-operation source and transformation audit", "", "Generated read-only from pinned repository evidence. Not a payload, approval or renderer contract.", "", "14 logical VBA symbols are not 14 exact Word names; numbered targets and dynamic TTx are listed below.", "", f"Status counts: {json.dumps(report['status_counts'], sort_keys=True)}. Legacy ownership stays 8 BLOCKED / 6 PARTIAL.", "", "| Logical operation | Status | Effective physical targets (GLP / GMP / GMPbb / GSP) |", "|---|---|---|"]
    for row in report["fields"]:
        targets = [", ".join(r["effective_targets"]) if r["branch_reachable"] else "N/A (branch)" for r in row["physical_targets"]]
        lines.append(f"| {row['logical_operation']} | {row['status']} | {' / '.join(t or 'absent' for t in targets)} |")
    runtime = report["runtime_source_provenance"]["capture"]
    chain = report["runtime_identity_chain"]
    lines.extend(["", "## Runtime identity chain and operator protocol", "",
        "This extends the captured facts without changing any original semantic pin. UNVERIFIED_VERSION_BINDING remains a blocker; no live Excel observation has been supplied or performed by the agent.", "",
        "| Stage | Category | Scope |", "|---|---|---|"])
    for stage in chain["stages"]:
        lines.append(f"| {stage['stage']} | {stage['category']} | {stage['scope']} |")
    lines.extend(["", "Acceptance dimensions (not approvals):", "", "| Dimension | Category |", "|---|---|"])
    for dimension, category in sorted(chain["acceptance_matrix"].items()):
        lines.append(f"| {dimension} | {category} |")
    lines.extend(["", "Detailed operator-only protocol: `docs/QDKT_RUNTIME_OBSERVATION_PROTOCOL.md`. It separates observed COM path, on-disk snapshot, in-memory executed code and reviewed source. Unsigned, even internally consistent, PID/path/hash metadata never authenticates a collector or closes runtime identity.", "",
        "Encoding evidence: `tests/fixtures/inspection_qd_kt_runtime_identity_evidence.json` records original line hex/SHA, cp1258 and cp1252 codepoints, and exact ZIP/add-in lines. Get_Tpl has nine differing lines in Cases 7/8/11/12/13, outside Case 2. Get_TTV2 has one differing error-message line in its Fail handler: this CAN be reached on the i=2 call's failure path, not proven executed, and is not a direct Word text write. Neither ambiguity is silently normalized or treated as an approved export encoding.", "",
        "The add-in docProps/app.xml records producer Application=Microsoft Excel and AppVersion=16.0300, with no custom properties or manifest/build/release/version-named member observed. This is Office producer metadata, not a VBA build/distribution mapping or the version of an observed Excel session. The byte-anchored companion records the metadata XML SHA without collecting author/private core properties.", "",
        "Verifier boundary review: changed bytes and changed expected metadata cannot pass the independent capture pin; symlink/alternate-root acquisition is delegated to the existing bounded evidence reader. Known binary pins are checked before ZIP/VBA parsing. Malformed foreign projects or case-colliding module attacks are not reachable past unchanged byte pins; parser defense tests do not claim such a bypass was found. Static capture never substitutes for requested fresh extraction. Repository-code/dependency compromise is outside this input-only trust claim.", "",
        "New demonstrated gap: escaped lone UTF-16 surrogates were accepted by the JSON reader and failed only during later UTF-8 canonicalization. They now fail at the shared parser owner, including nested values/keys; valid Unicode and all old pins remain unchanged. The observation assessor is a diagnostic contract, not an approval or memory-attestation API.",
    ])
    lines.extend(["", "## Runtime/source evidence hardening", "",
        "Evidence classes remain separate: approved business policy; reviewed ZIP source; captured add-in source; exact original binary bytes; Word output/legal acceptance. The new capture is pinned static evidence, not a claim that local files were freshly verified by the normal audit.", "",
        "### Artifact and acquisition inventory", "",
        "All six inputs were supplied in the local workspace. Original acquisition/build/distribution chain is not attested. No timestamp, filename, excerpt or matching JSON hash field proves version identity.", "",
        "| Artifact | Exact byte SHA-256 |", "|---|---|"])
    for record in runtime["artifact_inputs"].values():
        lines.append(f"| `{record['location']}` | `{record['sha256']}` |")
    lines.extend(["", "Extraction: " + runtime["extraction"] + ". Normalization is LF only; no trim, case-fold, NFC/NFD or punctuation changes.", "",
        "The add-in physically contains `xl/vbaProject.bin`, SHA `" + runtime["addin_project_embedding"]["sha256"] + "`. BYTE_IDENTICAL_BINDING_PROVEN applies only to that embedded binary member and its containing add-in bytes. It does not prove the ZIP exports came from that binary, that Excel loaded it, or that compiled p-code matches extracted source.", "",
        "The reviewed ZIP has 51 exports/FRX entries and no WinAPI module or runtime add-in. The add-in contains QĐKT source procedures and all three uniquely declared WinAPI helpers in the same captured project. Static call references resolve in that source snapshot, not in a proven live execution.", "",
        "PROJECTCODEPAGE in the add-in is 1252. The historic ZIP trace uses `_decode` with cp1258 fallback; the ZIP does not attest its export codepage. Full Get_Tpl and Get_TTV2 text differs under the reviewed decoder in non-i2/error-message literals; cp1252 comparison matches. This is an encoding ambiguity, not proof of an actual changed business implementation. Existing reviewed source and semantic pins are preserved.", "",
        "| Procedure | ZIP lines | Add-in source lines | Reviewed-decoder comparison |", "|---|---|---|---|"])
    for proc in runtime["procedures"]:
        location = proc["module"] + "!" + proc["procedure"]
        comparison = proc.get("reviewed_decoder_comparison", {}).get("comparison", "ARTIFACT_UNAVAILABLE_OR_EVIDENCE_INSUFFICIENT")
        lines.append(f"| `{location}` | {proc.get('zip_lines', 'absent')} | {proc['addin_lines']} | {comparison} |")
    lines.extend(["", "All 14 operation source lines match in the captured writer (ZIP 739–818 versus add-in 732–811). Each field's `runtime_source_reference` records exact paired line numbers and LF source hashes. Business ownership, variable initialization and actual values remain unproven by this source match.", "",
        "Supplementary workbook observed separately: `legacy/Danh sách Kiểm tra GPs.xlsb`, exact SHA `c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d`. Static oletools extraction of `Module1.Load_Lib`, lines 20–40, shows reuse of an already-open workbook named GPs.xlam, then local Addins and configured fallback opening at 32–33. Module1:73 invokes `Application.Run` by add-in name. No checksum/build identity is checked on this path. An already-loaded or different path copy is a competing explanation; this supplementary workbook is not one of the six fresh-verifier inputs. No workbook/add-in was opened in Excel.", "",
        "### Unresolved evidence matrix", "",
        "| Relationship | Result | Still needed |", "|---|---|---|",
        "| Add-in to embedded project bytes | BYTE_IDENTICAL_BINDING_PROVEN (container-member scope only) | Loaded-runtime and p-code/source attestation |",
        "| Reviewed ZIP to captured QĐKT source lines | CONTENT_EQUIVALENT_VERSION_UNPROVEN | Attested export/build/distribution manifest, including codepage |",
        "| WinAPI helper to ZIP | ARTIFACT_UNAVAILABLE_OR_EVIDENCE_INSUFFICIENT | Original helper export/runtime-package provenance; no invented ZIP body |",
        "| Full Get_Tpl/Get_TTV2 reviewed-decoder text | IMPLEMENTATION_DIFFERS as text, encoding cause unresolved | Export codepage evidence; do not infer active i=2 change |",
        "| Template filename formula to original bytes selected at runtime | UNVERIFIED_VERSION_BINDING | Resolved Template_Path/version capture and actual Word UAT |",
        "| All source evidence to legal/business equivalence | Not established | Existing owner decisions/date/timezone/Word acceptance |", "",
        "Fresh local reproduction: with the reviewed optional analyst tool `oletools==0.60.2`, run `python -m tools.audit_qdkt_source_transformations --verify-local-artifacts --format json`. The flag reads the six fixed local inputs through the existing bounded offline evidence reader, checks actual immutable bytes before extraction, re-extracts source and scans every word/*.xml (including notes), then compares the entire capture with the independent pin. Missing/substituted bytes, extractor absence/version change or metadata drift blocks; there is no fallback to captured evidence labelled as fresh. Stdout only and exit 2 remain intentional because render readiness is blocked.", "",
        "New RED→GREEN cases reject foreign GxP objects, duplicate/malformed physical names, bool/float numbered bounds and JSON exponent overflow. Valid target ordering/missing-target no-op behavior is preserved; Unicode, casing and punctuation are not normalized away. No renderer or business source owner was added.",
    ])
    lines.extend([
        "", "## New findings and validation boundary", "",
        "Last-correct: operation line/reachability and the 8/6 ownership set were already checked. First-incorrect: assignment, formatting, candidate-owner and invariant metadata could change without rejection; matching edits to both archive hashes could substitute the reviewed source. Full semantic pins now reject those changes while allowing JSON whitespace/key ordering differences.", "",
        "Separate RED cases showed duplicate JSON keys taking the last value, malformed reachability escaping as TypeError, an unknown geography enum ignored by the vaccine branch, and a foreign equality object masquerading as vaccine in both selector and wrapper. Minimal fixes reject these at their source owners. They do not establish manufacture-source provenance.", "",
        "The planning entry assigns Daychuyen, but authority logic reads DaychuyenDD; CreateFile(i=2) does not reload GetTT_Ktra. No fresh assignment of dossier/decision public variables is proven on that entry. This is unproven variable lifetime, not a claim that a particular runtime document used stale data.", "",
        "Backend module hashes use UTF-8 with LF-normalized source to survive Windows Git checkout conversion. Original template/source-binary hashes remain exact byte hashes. The report is deterministic but pins are review anchors, not signatures or independent owner attestations.",
    ])
    for row in report["fields"]:
        lines.extend(["", f"## {row['logical_operation']} — {row['status']}", "", f"Legacy expression: `{row['legacy_source_expression'] or '(DELETE: no value)'}`.", "", f"Legacy transform: {row['legacy_transformation']}", "", f"Candidate canonical source: {row['canonical_candidate']}", "", f"Ownership: {row['ownership']}", "", f"Null/missing: {row['null_missing_behavior']}", "", f"Multiple records: {row['multiple_record_behavior']}", "", f"Date/time: {row['date_time_handling']}", "", f"Difference: {row['differences']}", "", "Blockers: " + ", ".join(f"`{code}`" for code in row["blocker_codes"]) + ".", "", "Owner evidence: " + "; ".join(row["owner_evidence_needed"]) + ".", "", "Evidence refs: " + "; ".join(f"`{ref}`" for ref in row["evidence_refs"]) + "."])
    lines.extend(["", "## Adversarial evidence matrix", ""])
    for case in report["adversarial_regressions"]:
        lines.extend([f"- {case['case']} ({case['risk']}): {case['defect_or_unproven_behavior']}. Test: `{case['test_reference']}`. Expected: {case['expected_fail_closed_outcome']}. Required evidence: {case['evidence_required']}.", ""])
    lines.extend(["", "## Reproduce and limitations", "", "Run `python -m tools.audit_qdkt_source_transformations --format json` or `--format markdown` from repo root. Stdout only; exit 2 always because readiness is blocked. The existing legacy inventory is preserved; this companion projection adds current contract analysis without replacing its source classifications.", "", f"Inventory semantic SHA: `{report['inventory_semantic_sha256']}`. Trace semantic SHA: `{report['trace_semantic_sha256']}`. Source archive SHA: `{report['source_zip_sha256']}`.", "", "Machine report: `artifacts/legacy_audit/inspection_qd_kt_transformation_audit.json` includes all attempted/effective physical names, module hashes, group summaries and deterministic blocker inventory. Effective targets are committed primary binary observations, not a fresh read or proof of Word rendering.", "", "Supplementary helper evidence: `" + report["supplementary_helper_evidence"]["path"] + "`, source binary SHA `" + report["supplementary_helper_evidence"]["source_binary_sha256"] + "`. " + report["supplementary_helper_evidence"]["limitation"], "", "A CONTRADICTED status identifies a source/attempt-policy conflict, not proof that a missing bookmark actually changed a Word document. No field is VERIFIED. Source facts and helper regression success do not establish live Case provenance, legal acceptance or Word equivalence.", "", "Process A: " + report["process_a"], "", "Process B: " + report["process_b"], "", "Required adversarial coverage reuses #191 lifecycle tests (Case/Plan ownership, stale projection, multiple references, no issued reads), #186 renderer/date tests (missing atoms, date-only/timestamp separation, no timezone inference), and existing Site/team/locality/physical gates. New audit tests cover metadata pin drift, duplicate/missing physical targets, unknown/counterfeit classification and self-promoted reports. No production data or Word execution is involved.", "", "Runtime gate hardening pins full reviewed inventory/trace semantic contents and rejects duplicate JSON keys. Updates to assignment/format/owner metadata require explicit source review and new pins. VKN input validation rejects unknown enum/object values while preserving the valid vaccine + UNPROVEN-geography rule; it does not supply a missing canonical manufacture owner.", "", "Remaining owner decisions: legal A/B, wording/placement or intentional omission, current address/locality/name formatting, canonical manufacture classification and geography applicability, roster/title/position/layout evidence, date/timezone policy and external legal issuance. Actual four-variant Word UAT and trusted owner acceptance remain required.", "", "`decision=UNDECIDED`; Word UAT `NOT_EXECUTED`; business timezone `PARTIAL_UNPROVEN_BUSINESS_TIMEZONE`; `ready_to_render=False`. Keep #74 and #144 OPEN.", ""])
    return "\n".join(lines)
