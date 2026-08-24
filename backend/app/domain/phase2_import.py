from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import json

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.app.db.enums import (
    AuditActorType,
    CaseState,
    ChangeRequestState,
    InspectionEventType,
    LegacyEntityType,
)
from backend.app.db.models.phase1 import (
    AuditEvent,
    Base as ModelsBase,
    BusinessEligibilityCertificate,
    BusinessEligibilityCertificateLink,
    BusinessEligibilityVersion,
    Case,
    CaseApplication,
    CaseAssessment,
    Certificate,
    CertificateVersion,
    ChangeApproval,
    ChangeRequest,
    ChangeRequestDetail,
    Company,
    InspectionEvent,
    InspectionOutcome,
    LegacyIdMap,
    MigrationAnomaly,
    Site,
)
from backend.app.domain.legacy_snapshot import read_core_sheet_rows

CONFIRMED_BLANKED_ROWS_PATH = Path(__file__).resolve().parents[3] / "artifacts" / "phase3q" / "confirmed_blanked_rows.json"


PRIMARY_TARGET_MAP = {
    "db.cty": Company,
    "db.cso": Site,
    "db.ktra": Case,
    "db.cc": Certificate,
    "db.dkkd": BusinessEligibilityCertificate,
    "db.Tdoi": ChangeRequest,
    "db.Tdoi2": ChangeRequestDetail,
}


FIELD_ALIASES = {
    "company_code_gmp": {"MÃƒÆ’ CTY GMP", "MÃƒÆ’Ã†â€™ CTY GMP", "MÃ CTY GMP"},
    "company_code_glp": {"MÃƒÆ’ CTY GLP", "MÃƒÆ’Ã†â€™ CTY GLP", "MÃ CTY GLP"},
    "company_code_gmpbb": {"MÃƒÆ’ CTY GMPbb", "MÃƒÆ’Ã†â€™ CTY GMPbb", "MÃ CTY GMPbb"},
    "company_name": {"TÃƒÅ N CÃƒâ€NG TY", "TÃƒÆ’Ã…Â N CÃƒÆ’Ã¢â‚¬ÂNG TY", "TÃŠN CÃ”NG TY", "TÊN CÔNG TY"},
    "company_short_name": {"TÃƒÅ N VIÃ¡ÂºÂ¾T TÃ¡ÂºÂ®T", "TÃƒÆ’Ã…Â N VIÃƒÂ¡Ã‚ÂºÃ‚Â¾T TÃƒÂ¡Ã‚ÂºÃ‚Â®T", "TÃŠN VIáº¾T Táº®T", "TÊN VIẾT TẮT"},
    "company_address": {"Ã„ÂÃ¡Â»Å A CHÃ¡Â»Ë† TRÃ¡Â»Â¤ SÃ¡Â»Å¾", "Ãƒâ€žÃ‚ÂÃƒÂ¡Ã‚Â»Ã…Â A CHÃƒÂ¡Ã‚Â»Ã‹â€  TRÃƒÂ¡Ã‚Â»Ã‚Â¤ SÃƒÂ¡Ã‚Â»Ã…Â¾", "Äá»ŠA CHá»ˆ TRá»¤ Sá»ž", "ĐỊA CHỈ TRỤ SỞ"},
    "company_inactive_flag": {"NGÃ¡Â»ÂªNG HOÃ¡ÂºÂ T Ã„ÂÃ¡Â»ËœNG", "NGÃƒÂ¡Ã‚Â»Ã‚ÂªNG HOÃƒÂ¡Ã‚ÂºÃ‚Â T Ãƒâ€žÃ‚ÂÃƒÂ¡Ã‚Â»Ã‹Å“NG", "NGƯNG HOẠT ĐỘNG"},
    "company_legacy_id_ref": {"ID Cty", "ID CTY"},
    "site_code_gmp": {"MÃƒÆ’ CS GMP", "MÃƒÆ’Ã†â€™ CS GMP", "MÃ CS GMP"},
    "site_code_glp": {"MÃƒÆ’ CS GLP", "MÃƒÆ’Ã†â€™ CS GLP", "MÃ CS GLP"},
    "site_code_gmpbb": {"MÃƒÆ’ CS GMPbb", "MÃƒÆ’Ã†â€™ CS GMPbb", "MÃ CS GMPbb"},
    "site_name": {"TÃƒÅ N CÃ†Â  SÃ¡Â»Å¾", "TÃƒÆ’Ã…Â N CÃƒâ€ Ã‚Â  SÃƒÂ¡Ã‚Â»Ã…Â¾", "TÃŠN CÆ  Sá»ž", "TÊN CƠ SỞ"},
    "site_address": {"Ã„ÂÃ¡Â»Å A CHÃ¡Â»Ë† CÃ†Â  SÃ¡Â»Å¾", "Ãƒâ€žÃ‚ÂÃƒÂ¡Ã‚Â»Ã…Â A CHÃƒÂ¡Ã‚Â»Ã‹â€  CÃƒâ€ Ã‚Â  SÃƒÂ¡Ã‚Â»Ã…Â¾", "Äá»ŠA CHá»ˆ CÆ  Sá»ž", "ĐỊA CHỈ CƠ SỞ"},
    "province_name": {"TÃ¡Â»Ë†NH/TP", "TÃƒÂ¡Ã‚Â»Ã‹â€ NH/TP", "Tá»ˆNH/TP", "TỈNH/TP"},
    "site_legacy_id_ref": {"ID CÃ†Â  SÃ¡Â»Å¾", "ID CÃƒâ€ Ã‚Â  SÃƒÂ¡Ã‚Â»Ã…Â¾", "ID CÆ  Sá»ž", "ID CƠ SỞ"},
    "inspection_gxp_type": {"LOÃ¡ÂºÂ I KT", "LOÃƒÂ¡Ã‚ÂºÃ‚Â I KT", "LOẠI KT"},
    "scope_code": {"MÃƒÆ’ DC", "MÃƒÆ’Ã†â€™ DC", "MÃ DC"},
    "applicable_standard": {"TIÃƒÅ U CHUÃ¡ÂºÂ¨N ÃƒÂP DÃ¡Â»Â¤NG", "TIÃƒÆ’Ã…Â U CHUÃƒÂ¡Ã‚ÂºÃ‚Â¨N ÃƒÆ’Ã‚ÂP DÃƒÂ¡Ã‚Â»Ã‚Â¤NG", "TIÃŠU CHUáº¨N ÃP Dá»¤NG", "TIÊU CHUẨN ÁP DỤNG"},
    "inspection_type": {"LOÃ¡ÂºÂ I KIÃ¡Â»â€šM TRA", "LOÃƒÂ¡Ã‚ÂºÃ‚Â I KIÃƒÂ¡Ã‚Â»Ã¢â‚¬Å¡M TRA", "LOáº I KIá»‚M TRA", "LOẠI KIỂM TRA"},
    "submitted_at": {"NgÃƒÂ y nÃ¡Â»â„¢p", "NgÃƒÆ’Ã‚Â y nÃƒÂ¡Ã‚Â»Ã¢â€žÂ¢p", "NgÃ y ná»™p", "Ngày nộp"},
    "dossier_code": {"MÃƒÂ£ hÃ¡Â»â€œ sÃ†Â¡", "MÃƒÆ’Ã‚Â£ hÃƒÂ¡Ã‚Â»Ã¢â‚¬Å“ sÃƒâ€ Ã‚Â¡", "MÃ£ há»“ sÆ¡", "Mã hồ sơ"},
    "assessed_at": {"NgÃƒÂ y thÃ¡ÂºÂ©m Ã„â€˜Ã¡Â»â€¹nh", "NgÃƒÆ’Ã‚Â y thÃƒÂ¡Ã‚ÂºÃ‚Â©m Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¹nh", "NgÃ y tháº©m Ä‘á»‹nh", "Ngày thẩm định"},
    "assessor_name": {"NgÃ†Â°Ã¡Â»Âi thÃ¡ÂºÂ©m Ã„â€˜Ã¡Â»â€¹nh", "NgÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Âi thÃƒÂ¡Ã‚ÂºÃ‚Â©m Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¹nh", "NgÆ°á»i tháº©m Ä‘á»‹nh", "Người thẩm định"},
    "assessment_result": {"KÃ¡ÂºÂ¿t quÃ¡ÂºÂ£", "KÃƒÂ¡Ã‚ÂºÃ‚Â¿t quÃƒÂ¡Ã‚ÂºÃ‚Â£", "Káº¿t quáº£", "Kết quả"},
    "inspected_at": {"NgÃƒÂ y K.tra", "NgÃƒÆ’Ã‚Â y K.tra", "NgÃ y K.tra", "Ngày K.tra"},
    "decision_reference": {"Q. Ã„â€˜Ã¡Â»â€¹nh", "Q. Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¹nh", "Q. Ä‘á»‹nh", "Q. định"},
    "bbkt_reference": {"B. bÃ¡ÂºÂ£n", "B. bÃƒÂ¡Ã‚ÂºÃ‚Â£n", "B. báº£n", "B. bản"},
    "inspection_case_legacy_id_ref": {"ID Ã„ÂÃ¡Â»Â¢T KTRA", "ID Ãƒâ€žÃ‚ÂÃƒÂ¡Ã‚Â»Ã‚Â¢T KTRA", "ID Äá»¢T KTRA", "ID ĐỢT KTRA"},
    "certificate_type": {"LOÃ¡ÂºÂ I CC", "LOÃƒÂ¡Ã‚ÂºÃ‚Â I CC", "LOẠI CC"},
    "latest_flag": {"MÃ¡Â»Å¡I NHÃ¡ÂºÂ¤T", "MÃƒÂ¡Ã‚Â»Ã…Â¡I NHÃƒÂ¡Ã‚ÂºÃ‚Â¤T", "Má»šI NHáº¤T", "MỚI NHẤT"},
    "latest_legacy_id": {"ID MÃ¡Â»Å¡I NHÃ¡ÂºÂ¤T", "ID MÃƒÂ¡Ã‚Â»Ã…Â¡I NHÃƒÂ¡Ã‚ÂºÃ‚Â¤T", "ID Má»šI NHáº¤T", "ID MỚI NHẤT"},
    "professional_responsible_person_name": {"NGÃ†Â¯Ã¡Â»Å’I CHÃ¡Â»Å U TRÃƒÂCH NHIÃ¡Â»â€ M CHUYÃƒÅ N MÃƒâ€N", "NGÃƒâ€ Ã‚Â¯ÃƒÂ¡Ã‚Â»Ã…â€™I CHÃƒÂ¡Ã‚Â»Ã…Â U TRÃƒÆ’Ã‚ÂCH NHIÃƒÂ¡Ã‚Â»Ã¢â‚¬Â M CHUYÃƒÆ’Ã…Â N MÃƒÆ’Ã¢â‚¬ÂN", "NGÆ¯á»ŒI CHá»ŠU TRÃCH NHIá»†M CHUYÃŠN MÃ”N", "NGƯỜI CHỊU TRÁCH NHIỆM CHUYÊN MÔN"},
    "linked_certificate_ids": {"ID CC"},
    "change_scope_label": {"PHÃ¡ÂºÂ M VI", "PHÃƒÂ¡Ã‚ÂºÃ‚Â M VI", "PHáº M VI", "PHẠM VI"},
    "change_description": {"MÃƒâ€ TÃ¡ÂºÂ¢", "MÃƒÆ’Ã¢â‚¬Â TÃƒÂ¡Ã‚ÂºÃ‚Â¢", "MÃ” Táº¢", "MÔ TẢ"},
    "requester_name": {"Ã„ÂÃ†Â N VÃ¡Â»Å  Ã„ÂÃ¡Â»â‚¬ NGHÃ¡Â»Å ", "Ãƒâ€žÃ‚ÂÃƒâ€ Ã‚Â N VÃƒÂ¡Ã‚Â»Ã…Â  Ãƒâ€žÃ‚ÂÃƒÂ¡Ã‚Â»Ã¢â€šÂ¬ NGHÃƒÂ¡Ã‚Â»Ã…Â ", "ÄÆ N Vá»Š Äá»€ NGHá»Š", "ĐƠN VỊ ĐỀ NGHỊ"},
    "handled_on": {"NgÃƒÂ y xÃ¡Â»Â­ lÃƒÂ½", "NgÃƒÆ’Ã‚Â y xÃƒÂ¡Ã‚Â»Ã‚Â­ lÃƒÆ’Ã‚Â½", "NgÃ y xá»­ lÃ½", "Ngày xử lý"},
    "handled_by_name": {"NgÃ†Â°Ã¡Â»Âi xÃ¡Â»Â­ lÃƒÂ½", "NgÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Âi xÃƒÂ¡Ã‚Â»Ã‚Â­ lÃƒÆ’Ã‚Â½", "NgÆ°á»i xá»­ lÃ½", "Người xử lý"},
    "effective_on": {"NgÃƒÂ y hiÃ¡Â»â€¡u lÃ¡Â»Â±c cÃ¡Â»Â§a TÃ„Â", "NgÃƒÆ’Ã‚Â y hiÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡u lÃƒÂ¡Ã‚Â»Ã‚Â±c cÃƒÂ¡Ã‚Â»Ã‚Â§a TÃƒâ€žÃ‚Â", "NgÃ y hiá»‡u lá»±c cá»§a TÄ", "Ngày hiệu lực của TĐ"},
    "approval_reference": {"CV chÃ¡ÂºÂ¥p nhÃ¡ÂºÂ­n & ngÃƒÂ y", "CV chÃƒÂ¡Ã‚ÂºÃ‚Â¥p nhÃƒÂ¡Ã‚ÂºÃ‚Â­n & ngÃƒÆ’Ã‚Â y", "CV cháº¥p nháº­n & ngÃ y", "CV chấp nhận & ngày"},
    "change_request_legacy_id_ref": {"ID GÃ¡Â»â€˜c", "ID GÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœc", "ID Gá»‘c", "ID Gốc"},
    "classification_id": {"ID PhÃƒÂ¢n loÃ¡ÂºÂ¡i", "ID PhÃƒÆ’Ã‚Â¢n loÃƒÂ¡Ã‚ÂºÃ‚Â¡i", "ID PhÃ¢n loáº¡i", "ID Phân loại"},
    "classification_label": {"PHÃƒâ€šN LOÃ¡ÂºÂ I", "PHÃƒÆ’Ã¢â‚¬Å¡N LOÃƒÂ¡Ã‚ÂºÃ‚Â I", "PHÃ‚N LOáº I", "PHÂN LOẠI"},
    "approval_status": {"TÃƒÅ’NH TRÃ¡ÂºÂ NG CHÃ¡ÂºÂ¤P NHÃ¡ÂºÂ¬N", "TÃƒÆ’Ã…â€™NH TRÃƒÂ¡Ã‚ÂºÃ‚Â NG CHÃƒÂ¡Ã‚ÂºÃ‚Â¤P NHÃƒÂ¡Ã‚ÂºÃ‚Â¬N", "TÃŒNH TRáº NG CHáº¤P NHáº¬N", "TÌNH TRẠNG CHẤP NHẬN"},
    "old_value": {"THÃƒâ€NG TIN CÃ…Â¨", "THÃƒÆ’Ã¢â‚¬ÂNG TIN CÃƒâ€¦Ã‚Â¨", "THÃ”NG TIN CÅ¨", "THÔNG TIN CŨ"},
    "new_value": {"THÃƒâ€NG TIN MÃ¡Â»Å¡I", "THÃƒÆ’Ã¢â‚¬ÂNG TIN MÃƒÂ¡Ã‚Â»Ã…Â¡I", "THÃ”NG TIN Má»šI", "THÔNG TIN MỚI"},
    "note": {"GHI CHÃƒÅ¡", "GHI CHÃƒÆ’Ã…Â¡", "GHI CHÃš", "GHI CHÚ"},
}


REMEDIATION_KEY_BY_REASON = {
    "missing_company_fk": "company_legacy_id",
    "missing_site_fk": "site_legacy_id",
    "missing_case_fk": "case_legacy_id",
    "missing_change_request_fk": "change_request_legacy_id",
}


class ImportCollisionError(RuntimeError):
    """Raised when production-safe import detects conflicting existing data."""


@dataclass(frozen=True)
class ImportExecutionOptions:
    ensure_schema: bool = True
    reset_existing_data: bool = True
    allow_existing_records: bool = False
    persist_audit_event: bool = True


@dataclass
class ImportStats:
    inserted_counts: dict[str, int] = field(default_factory=dict)
    existing_counts: dict[str, int] = field(default_factory=dict)

    def record_inserted(self, table: str) -> None:
        self.inserted_counts[table] = self.inserted_counts.get(table, 0) + 1

    def record_existing(self, table: str) -> None:
        self.existing_counts[table] = self.existing_counts.get(table, 0) + 1


def normalize_row(row: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in row.items():
        mapped_key = key
        for canonical_key, aliases in FIELD_ALIASES.items():
            if key in aliases:
                mapped_key = canonical_key
                break
        normalized[mapped_key] = value
    return normalized


def parse_int(value: str | int | None) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def source_row_number(row: dict[str, str]) -> int | None:
    return parse_int(row.get("__excel_row_number"))


def source_row_key(*, legacy_row_id: int | None, source_row_number_value: int | None) -> str | None:
    if legacy_row_id is not None:
        return str(legacy_row_id)
    if source_row_number_value is not None:
        return f"row:{source_row_number_value}"
    return None


def parse_dt(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text or text == "-":
        return None
    normalized = text.replace("+00:00", "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def parse_date(value: str):
    dt = parse_dt(value)
    return dt.date() if dt else None


def is_latest_flag(value: str) -> bool:
    text = (value or "").strip()
    return bool(text and text != "-")


def create_schema(session: Session) -> None:
    engine = session.get_bind()
    ModelsBase.metadata.create_all(engine)


def _normalize_comparable(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return value


def _assert_fields_match(
    entity: Any,
    expected_fields: dict[str, Any],
    *,
    context: str,
) -> None:
    mismatches: list[str] = []
    for field_name, expected_value in expected_fields.items():
        actual_value = getattr(entity, field_name)
        if _normalize_comparable(actual_value) != _normalize_comparable(expected_value):
            mismatches.append(
                f"{field_name}: expected {_normalize_comparable(expected_value)!r}, got {_normalize_comparable(actual_value)!r}"
            )
    if mismatches:
        raise ImportCollisionError(f"{context} has conflicting existing data: {'; '.join(mismatches)}")


def _source_identity_key(legacy_id: int | None, row_number: int | None) -> str | None:
    return source_row_key(legacy_row_id=legacy_id, source_row_number_value=row_number)


def _load_existing_entity(
    session: Session,
    *,
    model: type[Any],
    entity_type: LegacyEntityType | None,
    legacy_field_name: str | None,
    identity_key: str | None,
) -> Any | None:
    if identity_key is None:
        return None

    legacy_map = None
    if entity_type is not None:
        legacy_map = session.scalar(
            select(LegacyIdMap).where(
                LegacyIdMap.entity_type == entity_type,
                LegacyIdMap.legacy_id == identity_key,
            )
        )
    if legacy_map is not None:
        entity = session.get(model, legacy_map.target_entity_id)
        if entity is None:
            raise ImportCollisionError(
                f"LegacyIdMap for {entity_type.value}:{identity_key} points to missing {model.__tablename__} id={legacy_map.target_entity_id}."
            )
        if legacy_map.target_table != model.__tablename__:
            raise ImportCollisionError(
                f"LegacyIdMap for {entity_type.value}:{identity_key} points to unexpected table {legacy_map.target_table!r}."
            )
        return entity

    if legacy_field_name is None or identity_key.startswith("row:"):
        return None

    try:
        legacy_numeric = int(identity_key)
    except ValueError:
        return None

    entity = session.scalar(select(model).where(getattr(model, legacy_field_name) == legacy_numeric))
    if entity is not None:
        if entity_type is None:
            return entity
        raise ImportCollisionError(
            f"Existing {model.__tablename__} row with legacy identity {identity_key} is missing LegacyIdMap lineage."
        )
    return None


def _ensure_legacy_map(
    session: Session,
    *,
    entity_type: LegacyEntityType | None,
    identity_key: str | None,
    target_table: str,
    target_entity_id: str,
) -> None:
    if entity_type is None or identity_key is None:
        return

    existing = session.scalar(
        select(LegacyIdMap).where(
            LegacyIdMap.entity_type == entity_type,
            LegacyIdMap.legacy_id == identity_key,
        )
    )
    if existing is not None:
        if existing.target_table != target_table or existing.target_entity_id != target_entity_id:
            raise ImportCollisionError(
                f"LegacyIdMap collision for {entity_type.value}:{identity_key}; "
                f"expected {target_table}:{target_entity_id}, found {existing.target_table}:{existing.target_entity_id}."
            )
        return

    note = "source_row_key_fallback" if identity_key.startswith("row:") else None
    session.add(
        LegacyIdMap(
            entity_type=entity_type,
            legacy_id=identity_key,
            target_table=target_table,
            target_entity_id=target_entity_id,
            note=note,
        )
    )


def _ensure_entity(
    session: Session,
    stats: ImportStats,
    *,
    table_name: str,
    model: type[Any],
    entity_type: LegacyEntityType | None,
    legacy_field_name: str | None,
    identity_key: str | None,
    expected_fields: dict[str, Any],
    build_entity: Any,
    options: ImportExecutionOptions,
) -> Any:
    if options.allow_existing_records and entity_type is None and identity_key is not None and identity_key.startswith("row:"):
        raise ImportCollisionError(
            f"{table_name}[{identity_key}] cannot be replayed idempotently because no canonical LegacyEntityType lineage exists."
        )
    if options.allow_existing_records:
        existing = _load_existing_entity(
            session,
            model=model,
            entity_type=entity_type,
            legacy_field_name=legacy_field_name,
            identity_key=identity_key,
        )
        if existing is not None:
            _assert_fields_match(existing, expected_fields, context=f"{table_name}[{identity_key}]")
            _ensure_legacy_map(
                session,
                entity_type=entity_type,
                identity_key=identity_key,
                target_table=table_name,
                target_entity_id=existing.id,
            )
            stats.record_existing(table_name)
            return existing

    entity = build_entity()
    session.add(entity)
    session.flush()
    _ensure_legacy_map(
        session,
        entity_type=entity_type,
        identity_key=identity_key,
        target_table=table_name,
        target_entity_id=entity.id,
    )
    stats.record_inserted(table_name)
    return entity


def _ensure_single_child(
    session: Session,
    stats: ImportStats,
    *,
    table_name: str,
    model: type[Any],
    filters: dict[str, Any],
    expected_fields: dict[str, Any],
    build_entity: Any,
    options: ImportExecutionOptions,
) -> Any:
    existing = session.scalar(select(model).filter_by(**filters))
    if existing is not None:
        if not options.allow_existing_records:
            raise ImportCollisionError(f"{table_name} already contains a row for {filters!r} during reset import mode.")
        _assert_fields_match(existing, expected_fields, context=f"{table_name}{filters!r}")
        stats.record_existing(table_name)
        return existing

    entity = build_entity()
    session.add(entity)
    session.flush()
    stats.record_inserted(table_name)
    return entity


def _ensure_inspection_event(
    session: Session,
    stats: ImportStats,
    *,
    case_id: str,
    event_type: InspectionEventType,
    occurred_at: datetime | None,
    payload: str | None,
    options: ImportExecutionOptions,
) -> None:
    matching = session.scalars(
        select(InspectionEvent).where(
            InspectionEvent.case_id == case_id,
            InspectionEvent.event_type == event_type,
        )
    ).all()
    for event in matching:
        if event.occurred_at == occurred_at and event.payload == payload:
            stats.record_existing("inspection_event")
            return
    if matching and options.allow_existing_records:
        raise ImportCollisionError(
            f"inspection_event[{case_id},{event_type.value}] has conflicting existing data."
        )
    session.add(
        InspectionEvent(
            case_id=case_id,
            event_type=event_type,
            occurred_at=occurred_at,
            payload=payload,
        )
    )
    session.flush()
    stats.record_inserted("inspection_event")


def _ensure_business_eligibility_link(
    session: Session,
    stats: ImportStats,
    *,
    business_eligibility_version_id: str,
    certificate_id: str,
    options: ImportExecutionOptions,
) -> None:
    existing = session.scalar(
        select(BusinessEligibilityCertificateLink).where(
            BusinessEligibilityCertificateLink.business_eligibility_version_id == business_eligibility_version_id,
            BusinessEligibilityCertificateLink.certificate_id == certificate_id,
        )
    )
    if existing is not None:
        stats.record_existing("business_eligibility_certificate_link")
        return
    session.add(
        BusinessEligibilityCertificateLink(
            business_eligibility_version_id=business_eligibility_version_id,
            certificate_id=certificate_id,
        )
    )
    session.flush()
    stats.record_inserted("business_eligibility_certificate_link")


def _ensure_migration_anomaly(
    session: Session,
    stats: ImportStats,
    *,
    payload: dict[str, Any],
    options: ImportExecutionOptions,
) -> None:
    existing = session.scalar(
        select(MigrationAnomaly).where(
            MigrationAnomaly.source_sheet == payload["source_sheet"],
            MigrationAnomaly.legacy_row_id == payload["legacy_row_id"],
            MigrationAnomaly.reason == payload["reason"],
            MigrationAnomaly.required_field == payload["required_field"],
            MigrationAnomaly.raw_fk_value == (payload["raw_fk_value"] or None),
            MigrationAnomaly.override_value == (payload["override_value"] or None),
            MigrationAnomaly.status == payload["status"],
        )
    )
    if existing is not None:
        if options.allow_existing_records:
            detail_json = existing.detail_json or ""
            expected_detail = json.dumps(payload, ensure_ascii=False)
            if detail_json != expected_detail:
                raise ImportCollisionError(
                    f"migration_anomaly[{payload['source_sheet']}:{payload['source_row_key']}] has conflicting existing detail_json."
                )
            stats.record_existing("migration_anomaly")
            return
        raise ImportCollisionError("migration_anomaly row already exists during reset import mode.")
    session.add(
        MigrationAnomaly(
            source_sheet=payload["source_sheet"],
            legacy_row_id=payload["legacy_row_id"],
            reason=payload["reason"],
            required_field=payload["required_field"],
            raw_fk_value=payload["raw_fk_value"] or None,
            override_value=payload["override_value"],
            status=payload["status"],
            detail_json=json.dumps(payload, ensure_ascii=False),
        )
    )
    session.flush()
    stats.record_inserted("migration_anomaly")


def _ensure_audit_event(session: Session, stats: ImportStats, *, options: ImportExecutionOptions) -> None:
    if not options.persist_audit_event:
        return
    payload = "Read-only import from legacy workbook snapshot"
    existing = session.scalar(
        select(AuditEvent).where(
            AuditEvent.actor_type == AuditActorType.MIGRATION,
            AuditEvent.action == "phase2_import_completed",
            AuditEvent.entity_type == "legacy_workbook_snapshot",
            AuditEvent.entity_id == "Danh sach Kiem tra GPs.xlsb",
            AuditEvent.payload_redacted == payload,
        )
    )
    if existing is not None:
        if not options.allow_existing_records:
            raise ImportCollisionError("phase2_import audit event already exists during reset import mode.")
        stats.record_existing("audit_event")
        return
    session.add(
        AuditEvent(
            actor_type=AuditActorType.MIGRATION,
            action="phase2_import_completed",
            entity_type="legacy_workbook_snapshot",
            entity_id="Danh sach Kiem tra GPs.xlsb",
            payload_redacted=payload,
        )
    )
    session.flush()
    stats.record_inserted("audit_event")


def _validate_snapshot_source_keys(snapshot: dict[str, list[dict[str, str]]]) -> None:
    for source_sheet, rows in snapshot.items():
        seen: set[str] = set()
        for raw_row in rows:
            row = normalize_row(raw_row)
            row_key = _source_identity_key(parse_int(row.get("ID", "")), source_row_number(row))
            if row_key is None:
                continue
            if row_key in seen:
                raise ImportCollisionError(f"Duplicate source row key {row_key!r} detected in sheet {source_sheet}.")
            seen.add(row_key)


def _add_legacy_map(session: Session, entity_type: LegacyEntityType, legacy_id: int | None, target_table: str, target_entity_id: str):
    if legacy_id is None:
        return
    session.add(
        LegacyIdMap(
            entity_type=entity_type,
            legacy_id=str(legacy_id),
            target_table=target_table,
            target_entity_id=target_entity_id,
        )
    )


def _reset_import_tables(session: Session) -> None:
    for model in [
        AuditEvent,
        BusinessEligibilityCertificateLink,
        BusinessEligibilityVersion,
        BusinessEligibilityCertificate,
        CertificateVersion,
        Certificate,
        InspectionEvent,
        InspectionOutcome,
        CaseAssessment,
        CaseApplication,
        Case,
        ChangeApproval,
        ChangeRequestDetail,
        ChangeRequest,
        Site,
        Company,
        LegacyIdMap,
        MigrationAnomaly,
    ]:
        session.execute(delete(model))
    session.flush()


def _get_override(
    overrides: dict[str, dict[str, dict[str, Any]]] | None,
    sheet: str,
    row_key: str | None,
    remediation_key: str,
) -> int | None:
    if overrides is None or row_key is None:
        return None
    row_override = overrides.get(sheet, {}).get(row_key, {})
    return parse_int(row_override.get(remediation_key))


def load_confirmed_blanked_row_keys() -> set[tuple[str, str]]:
    if not CONFIRMED_BLANKED_ROWS_PATH.exists():
        return set()
    payload = json.loads(CONFIRMED_BLANKED_ROWS_PATH.read_text(encoding="utf-8"))
    row_keys: set[tuple[str, str]] = set()
    for row in payload.get("rows", []):
        source_sheet = str(row.get("source_sheet", "")).strip()
        source_row_key = str(row.get("source_row_key", "")).strip()
        if source_sheet and source_row_key:
            row_keys.add((source_sheet, source_row_key))
    return row_keys


def load_confirmed_blanked_null_key_budgets() -> dict[str, int]:
    if not CONFIRMED_BLANKED_ROWS_PATH.exists():
        return {}
    payload = json.loads(CONFIRMED_BLANKED_ROWS_PATH.read_text(encoding="utf-8"))
    budgets: dict[str, int] = {}
    for row in payload.get("rows", []):
        source_sheet = str(row.get("source_sheet", "")).strip()
        source_row_key = str(row.get("source_row_key", "")).strip()
        if source_sheet and source_row_key.startswith("row:"):
            budgets[source_sheet] = budgets.get(source_sheet, 0) + 1
    return budgets


def _record_anomaly(
    session: Session,
    stats: ImportStats,
    options: ImportExecutionOptions,
    anomaly_rows: list[dict[str, Any]],
    *,
    source_sheet: str,
    legacy_row_id: int | None,
    source_row_number_value: int | None,
    reason: str,
    required_field: str,
    raw_fk_value: str,
    override_value: int | None,
    status_override: str | None = None,
) -> None:
    row_key = source_row_key(legacy_row_id=legacy_row_id, source_row_number_value=source_row_number_value)
    status = status_override or ("overridden" if override_value is not None else "open")
    row = {
        "source_sheet": source_sheet,
        "legacy_row_id": None if legacy_row_id is None else str(legacy_row_id),
        "source_row_number": source_row_number_value,
        "source_row_key": row_key,
        "reason": reason,
        "required_field": required_field,
        "raw_fk_value": raw_fk_value,
        "override_value": None if override_value is None else str(override_value),
        "status": status,
    }
    if status == "excluded_confirmed_blanked":
        row["classification"] = "confirmed_blanked_row"
        row["migration_action"] = "exclude_from_business_import"
    anomaly_rows.append(row)
    _ensure_migration_anomaly(
        session,
        stats,
        payload=row,
        options=options,
    )


def _resolve_legacy_fk(
    session: Session,
    stats: ImportStats,
    options: ImportExecutionOptions,
    anomaly_rows: list[dict[str, Any]],
    overrides: dict[str, dict[str, dict[str, Any]]] | None,
    *,
    source_sheet: str,
    legacy_row_id: int | None,
    source_row_number_value: int | None,
    raw_value: str,
    reason: str,
    required_field: str,
    target_map: dict[int, str],
    confirmed_blanked_row_keys: set[tuple[str, str]],
    confirmed_blanked_null_key_budgets: dict[str, int],
) -> str | None:
    remediation_key = REMEDIATION_KEY_BY_REASON[reason]
    row_key = source_row_key(legacy_row_id=legacy_row_id, source_row_number_value=source_row_number_value)
    parsed_legacy_id = parse_int(raw_value)
    if parsed_legacy_id is not None and parsed_legacy_id in target_map:
        return target_map[parsed_legacy_id]

    override_legacy_id = _get_override(
        overrides,
        source_sheet,
        source_row_key(legacy_row_id=legacy_row_id, source_row_number_value=source_row_number_value),
        remediation_key,
    )
    if override_legacy_id is not None and override_legacy_id in target_map:
        _record_anomaly(
            session,
            stats,
            options,
            anomaly_rows,
            source_sheet=source_sheet,
            legacy_row_id=legacy_row_id,
            source_row_number_value=source_row_number_value,
            reason=reason,
            required_field=required_field,
            raw_fk_value=raw_value,
            override_value=override_legacy_id,
        )
        return target_map[override_legacy_id]

    status_override = None
    if (source_sheet, row_key or "") in confirmed_blanked_row_keys:
        status_override = "excluded_confirmed_blanked"
    elif row_key is None and legacy_row_id is None and not str(raw_value or "").strip():
        remaining_budget = confirmed_blanked_null_key_budgets.get(source_sheet, 0)
        if remaining_budget > 0:
            status_override = "excluded_confirmed_blanked"
            confirmed_blanked_null_key_budgets[source_sheet] = remaining_budget - 1
    _record_anomaly(
        session,
        stats,
        options,
        anomaly_rows,
        source_sheet=source_sheet,
        legacy_row_id=legacy_row_id,
        source_row_number_value=source_row_number_value,
        reason=reason,
        required_field=required_field,
        raw_fk_value=raw_value,
        override_value=override_legacy_id,
        status_override=status_override,
    )
    return None


def _resolve_optional_legacy_fk(
    session: Session,
    stats: ImportStats,
    options: ImportExecutionOptions,
    anomaly_rows: list[dict[str, Any]],
    overrides: dict[str, dict[str, dict[str, Any]]] | None,
    *,
    source_sheet: str,
    legacy_row_id: int | None,
    source_row_number_value: int | None,
    raw_value: str,
    reason: str,
    required_field: str,
    target_map: dict[int, str],
    confirmed_blanked_row_keys: set[tuple[str, str]],
    confirmed_blanked_null_key_budgets: dict[str, int],
) -> str | None:
    if not str(raw_value or "").strip():
        return None
    return _resolve_legacy_fk(
        session,
        stats,
        options,
        anomaly_rows,
        overrides,
        source_sheet=source_sheet,
        legacy_row_id=legacy_row_id,
        source_row_number_value=source_row_number_value,
        raw_value=raw_value,
        reason=reason,
        required_field=required_field,
        target_map=target_map,
        confirmed_blanked_row_keys=confirmed_blanked_row_keys,
        confirmed_blanked_null_key_budgets=confirmed_blanked_null_key_budgets,
    )


def import_snapshot(
    session: Session,
    snapshot: dict[str, list[dict[str, str]]],
    remediation_overrides: dict[str, dict[str, dict[str, Any]]] | None = None,
    *,
    options: ImportExecutionOptions | None = None,
) -> dict[str, Any]:
    resolved_options = options or ImportExecutionOptions()
    if resolved_options.ensure_schema:
        create_schema(session)
    if resolved_options.reset_existing_data:
        _reset_import_tables(session)
    _validate_snapshot_source_keys(snapshot)
    confirmed_blanked_row_keys = load_confirmed_blanked_row_keys()
    confirmed_blanked_null_key_budgets = load_confirmed_blanked_null_key_budgets()
    anomaly_rows: list[dict[str, Any]] = []
    skipped_rows: dict[str, list[dict[str, Any]]] = {sheet: [] for sheet in snapshot}
    stats = ImportStats()

    company_ids: dict[int, str] = {}
    site_ids: dict[int, str] = {}
    case_ids: dict[int, str] = {}
    certificate_ids: dict[int, str] = {}
    change_ids: dict[int, str] = {}

    for raw_row in snapshot["db.cty"]:
        row = normalize_row(raw_row)
        legacy_id = parse_int(row.get("ID", ""))
        row_number = source_row_number(row)
        identity_key = _source_identity_key(legacy_id, row_number)
        expected_fields = {
            "legacy_company_id": legacy_id,
            "legacy_gmp_company_code": row.get("company_code_gmp") or None,
            "legacy_glp_company_code": row.get("company_code_glp") or None,
            "legacy_gmpbb_company_code": row.get("company_code_gmpbb") or None,
            "legal_name": row.get("company_name") or "(missing legacy company name)",
            "english_name": row.get("COMPANY NAME") or None,
            "short_name": row.get("company_short_name") or None,
            "legal_address": row.get("company_address") or None,
            "legal_address_en": row.get("LEGAL ADDRESS") or None,
            "is_inactive": bool(row.get("company_inactive_flag")),
        }
        entity = _ensure_entity(
            session,
            stats,
            table_name="company",
            model=Company,
            entity_type=LegacyEntityType.COMPANY,
            legacy_field_name="legacy_company_id",
            identity_key=identity_key,
            expected_fields=expected_fields,
            build_entity=lambda expected_fields=expected_fields: Company(**expected_fields),
            options=resolved_options,
        )
        if legacy_id is not None:
            company_ids[legacy_id] = entity.id

    for raw_row in snapshot["db.cso"]:
        row = normalize_row(raw_row)
        legacy_id = parse_int(row.get("ID", ""))
        row_number = source_row_number(row)
        company_id = _resolve_legacy_fk(
            session,
            stats,
            resolved_options,
            anomaly_rows,
            remediation_overrides,
            source_sheet="db.cso",
            legacy_row_id=legacy_id,
            source_row_number_value=row_number,
            raw_value=row.get("company_legacy_id_ref", ""),
            reason="missing_company_fk",
            required_field="ID Cty",
            target_map=company_ids,
            confirmed_blanked_row_keys=confirmed_blanked_row_keys,
            confirmed_blanked_null_key_budgets=confirmed_blanked_null_key_budgets,
        )
        if company_id is None:
            skipped_rows["db.cso"].append({"legacy_id": legacy_id, "reason": "missing_company_fk", "raw_fk": row.get("company_legacy_id_ref", "")})
            continue
        identity_key = _source_identity_key(legacy_id, row_number)
        expected_fields = {
            "legacy_site_id": legacy_id,
            "company_id": company_id,
            "legacy_gmp_site_code": row.get("site_code_gmp") or None,
            "legacy_glp_site_code": row.get("site_code_glp") or None,
            "legacy_gmpbb_site_code": row.get("site_code_gmpbb") or None,
            "site_name": row.get("site_name") or "(missing legacy site name)",
            "site_name_en": row.get("SITE NAME") or None,
            "site_address": row.get("site_address") or None,
            "site_address_en": row.get("SITE ADDRESS") or None,
            "province_name": row.get("province_name") or None,
            "short_name": row.get("company_short_name") or None,
        }
        entity = _ensure_entity(
            session,
            stats,
            table_name="site",
            model=Site,
            entity_type=LegacyEntityType.SITE,
            legacy_field_name="legacy_site_id",
            identity_key=identity_key,
            expected_fields=expected_fields,
            build_entity=lambda expected_fields=expected_fields: Site(**expected_fields),
            options=resolved_options,
        )
        if legacy_id is not None:
            site_ids[legacy_id] = entity.id

    for raw_row in snapshot["db.ktra"]:
        row = normalize_row(raw_row)
        legacy_id = parse_int(row.get("ID", ""))
        row_number = source_row_number(row)
        site_id = _resolve_legacy_fk(
            session,
            stats,
            resolved_options,
            anomaly_rows,
            remediation_overrides,
            source_sheet="db.ktra",
            legacy_row_id=legacy_id,
            source_row_number_value=row_number,
            raw_value=row.get("site_legacy_id_ref", ""),
            reason="missing_site_fk",
            required_field="ID Cơ Sở",
            target_map=site_ids,
            confirmed_blanked_row_keys=confirmed_blanked_row_keys,
            confirmed_blanked_null_key_budgets=confirmed_blanked_null_key_budgets,
        )
        if site_id is None:
            skipped_rows["db.ktra"].append({"legacy_id": legacy_id, "reason": "missing_site_fk", "raw_fk": row.get("site_legacy_id_ref", "")})
            continue
        submitted_at = parse_dt(row.get("submitted_at", ""))
        assessed_at = parse_dt(row.get("assessed_at", ""))
        inspected_at = parse_dt(row.get("bbkt_reference", "")) or parse_dt(row.get("inspected_at", ""))
        identity_key = _source_identity_key(legacy_id, row_number)
        expected_fields = {
            "legacy_inspection_id": legacy_id,
            "site_id": site_id,
            "gxp_type": row.get("inspection_gxp_type") or "UNKNOWN",
            "scope_code": row.get("scope_code") or None,
            "applicable_standard": row.get("applicable_standard") or None,
            "inspection_type": row.get("inspection_type") or None,
            "state": CaseState.CERTIFIED if row.get("assessment_result") or row.get("bbkt_reference") else CaseState.APPLICATION_RECEIVED,
            "opened_year": submitted_at.year if submitted_at else None,
        }
        entity = _ensure_entity(
            session,
            stats,
            table_name="case",
            model=Case,
            entity_type=LegacyEntityType.CASE,
            legacy_field_name="legacy_inspection_id",
            identity_key=identity_key,
            expected_fields=expected_fields,
            build_entity=lambda expected_fields=expected_fields: Case(**expected_fields),
            options=resolved_options,
        )
        if legacy_id is not None:
            case_ids[legacy_id] = entity.id
        _ensure_single_child(
            session,
            stats,
            table_name="case_application",
            model=CaseApplication,
            filters={"case_id": entity.id},
            expected_fields={
                "case_id": entity.id,
                "submitted_on": submitted_at,
                "dossier_code": row.get("dossier_code") or None,
                "dossier_reference": row.get("decision_reference") or None,
                "applicant_name": None,
            },
            build_entity=lambda: CaseApplication(
                case_id=entity.id,
                submitted_on=submitted_at,
                dossier_code=row.get("dossier_code") or None,
                dossier_reference=row.get("decision_reference") or None,
            ),
            options=resolved_options,
        )
        _ensure_single_child(
            session,
            stats,
            table_name="case_assessment",
            model=CaseAssessment,
            filters={"case_id": entity.id},
            expected_fields={
                "case_id": entity.id,
                "assessed_on": assessed_at,
                "assessor_name": row.get("assessor_name") or None,
                "assessment_result": row.get("assessment_result") or None,
                "notes": None,
            },
            build_entity=lambda: CaseAssessment(
                case_id=entity.id,
                assessed_on=assessed_at,
                assessor_name=row.get("assessor_name") or None,
                assessment_result=row.get("assessment_result") or None,
            ),
            options=resolved_options,
        )
        _ensure_single_child(
            session,
            stats,
            table_name="inspection_outcome",
            model=InspectionOutcome,
            filters={"case_id": entity.id},
            expected_fields={
                "case_id": entity.id,
                "inspected_on": parse_date(row.get("bbkt_reference", "")) or parse_date(row.get("inspected_at", "")),
                "inspected_to_on": None,
                "decision_reference": row.get("decision_reference") or None,
                "bbkt_reference": row.get("bbkt_reference") or None,
                "outcome_result": row.get("assessment_result") or None,
            },
            build_entity=lambda: InspectionOutcome(
                case_id=entity.id,
                inspected_on=parse_date(row.get("bbkt_reference", "")) or parse_date(row.get("inspected_at", "")),
                decision_reference=row.get("decision_reference") or None,
                bbkt_reference=row.get("bbkt_reference") or None,
                outcome_result=row.get("assessment_result") or None,
            ),
            options=resolved_options,
        )
        if submitted_at:
            _ensure_inspection_event(
                session,
                stats,
                case_id=entity.id,
                event_type=InspectionEventType.APPLICATION_SUBMITTED,
                occurred_at=submitted_at,
                payload=row.get("dossier_code") or None,
                options=resolved_options,
            )
        if assessed_at:
            _ensure_inspection_event(
                session,
                stats,
                case_id=entity.id,
                event_type=InspectionEventType.ASSESSMENT_COMPLETED,
                occurred_at=assessed_at,
                payload=row.get("assessment_result") or None,
                options=resolved_options,
            )
        if inspected_at:
            _ensure_inspection_event(
                session,
                stats,
                case_id=entity.id,
                event_type=InspectionEventType.INSPECTION_EXECUTED,
                occurred_at=inspected_at,
                payload=row.get("decision_reference") or None,
                options=resolved_options,
            )

    for raw_row in snapshot["db.cc"]:
        row = normalize_row(raw_row)
        legacy_id = parse_int(row.get("ID", ""))
        row_number = source_row_number(row)
        raw_case_fk = row.get("inspection_case_legacy_id_ref", "")
        case_id = _resolve_optional_legacy_fk(
            session,
            stats,
            resolved_options,
            anomaly_rows,
            remediation_overrides,
            source_sheet="db.cc",
            legacy_row_id=legacy_id,
            source_row_number_value=row_number,
            raw_value=raw_case_fk,
            reason="missing_case_fk",
            required_field="ID Đợt KTRA",
            target_map=case_ids,
            confirmed_blanked_row_keys=confirmed_blanked_row_keys,
            confirmed_blanked_null_key_budgets=confirmed_blanked_null_key_budgets,
        )
        if str(raw_case_fk or "").strip() and case_id is None:
            skipped_rows["db.cc"].append({"legacy_id": legacy_id, "reason": "missing_case_fk", "raw_fk": raw_case_fk})
            continue
        site_id = _resolve_legacy_fk(
            session,
            stats,
            resolved_options,
            anomaly_rows,
            remediation_overrides,
            source_sheet="db.cc",
            legacy_row_id=legacy_id,
            source_row_number_value=row_number,
            raw_value=row.get("site_legacy_id_ref", ""),
            reason="missing_site_fk",
            required_field="ID Cơ Sở",
            target_map=site_ids,
            confirmed_blanked_row_keys=confirmed_blanked_row_keys,
            confirmed_blanked_null_key_budgets=confirmed_blanked_null_key_budgets,
        )
        if site_id is None:
            skipped_rows["db.cc"].append({"legacy_id": legacy_id, "reason": "missing_site_fk", "raw_fk": row.get("site_legacy_id_ref", "")})
            continue
        identity_key = _source_identity_key(legacy_id, row_number)
        expected_fields = {
            "legacy_certificate_id": legacy_id,
            "case_id": case_id,
            "site_id": site_id,
            "certificate_type": row.get("certificate_type") or "UNKNOWN",
            "issuance_basis": "inspection_case" if case_id is not None else "administrative_no_inspection",
            "latest_flag": is_latest_flag(row.get("latest_flag", "")),
            "latest_legacy_certificate_id": parse_int(row.get("latest_legacy_id", "")),
        }
        entity = _ensure_entity(
            session,
            stats,
            table_name="certificate",
            model=Certificate,
            entity_type=LegacyEntityType.CERTIFICATE,
            legacy_field_name="legacy_certificate_id",
            identity_key=identity_key,
            expected_fields=expected_fields,
            build_entity=lambda expected_fields=expected_fields: Certificate(**expected_fields),
            options=resolved_options,
        )
        if legacy_id is not None:
            certificate_ids[legacy_id] = entity.id
        _ensure_single_child(
            session,
            stats,
            table_name="certificate_version",
            model=CertificateVersion,
            filters={"certificate_id": entity.id, "version_no": 1},
            expected_fields={
                "certificate_id": entity.id,
                "version_no": 1,
                "issue_date": None,
                "expiry_date": None,
                "certificate_number": row.get("scope_code") or None,
                "is_latest_version": True,
            },
            build_entity=lambda: CertificateVersion(
                certificate_id=entity.id,
                version_no=1,
                issue_date=None,
                expiry_date=None,
                certificate_number=row.get("scope_code") or None,
                is_latest_version=True,
            ),
            options=resolved_options,
        )
        if entity.case_id is not None:
            _ensure_inspection_event(
                session,
                stats,
                case_id=entity.case_id,
                event_type=InspectionEventType.CERTIFICATE_ISSUED,
                occurred_at=None,
                payload=row.get("certificate_type") or None,
                options=resolved_options,
            )

    for raw_row in snapshot["db.dkkd"]:
        row = normalize_row(raw_row)
        legacy_id = parse_int(row.get("ID", ""))
        row_number = source_row_number(row)
        site_id = _resolve_legacy_fk(
            session,
            stats,
            resolved_options,
            anomaly_rows,
            remediation_overrides,
            source_sheet="db.dkkd",
            legacy_row_id=legacy_id,
            source_row_number_value=row_number,
            raw_value=row.get("site_legacy_id_ref", ""),
            reason="missing_site_fk",
            required_field="ID Cơ Sở",
            target_map=site_ids,
            confirmed_blanked_row_keys=confirmed_blanked_row_keys,
            confirmed_blanked_null_key_budgets=confirmed_blanked_null_key_budgets,
        )
        if site_id is None:
            skipped_rows["db.dkkd"].append({"legacy_id": legacy_id, "reason": "missing_site_fk", "raw_fk": row.get("site_legacy_id_ref", "")})
            continue
        company_id = _resolve_legacy_fk(
            session,
            stats,
            resolved_options,
            anomaly_rows,
            remediation_overrides,
            source_sheet="db.dkkd",
            legacy_row_id=legacy_id,
            source_row_number_value=row_number,
            raw_value=row.get("company_legacy_id_ref", ""),
            reason="missing_company_fk",
            required_field="ID CTY",
            target_map=company_ids,
            confirmed_blanked_row_keys=confirmed_blanked_row_keys,
            confirmed_blanked_null_key_budgets=confirmed_blanked_null_key_budgets,
        )
        if company_id is None:
            skipped_rows["db.dkkd"].append({"legacy_id": legacy_id, "reason": "missing_company_fk", "raw_fk": row.get("company_legacy_id_ref", "")})
            continue
        identity_key = _source_identity_key(legacy_id, row_number)
        expected_fields = {
            "legacy_dkkd_id": legacy_id,
            "site_id": site_id,
            "company_id": company_id,
            "latest_flag": is_latest_flag(row.get("latest_flag", "")),
            "latest_legacy_dkkd_id": parse_int(row.get("latest_legacy_id", "")),
        }
        entity = _ensure_entity(
            session,
            stats,
            table_name="business_eligibility_certificate",
            model=BusinessEligibilityCertificate,
            entity_type=LegacyEntityType.BUSINESS_ELIGIBILITY,
            legacy_field_name="legacy_dkkd_id",
            identity_key=identity_key,
            expected_fields=expected_fields,
            build_entity=lambda expected_fields=expected_fields: BusinessEligibilityCertificate(**expected_fields),
            options=resolved_options,
        )
        version = _ensure_single_child(
            session,
            stats,
            table_name="business_eligibility_version",
            model=BusinessEligibilityVersion,
            filters={"business_eligibility_certificate_id": entity.id, "version_no": 1},
            expected_fields={
                "business_eligibility_certificate_id": entity.id,
                "version_no": 1,
                "certificate_number": row.get("linked_certificate_ids") or None,
                "issued_on": None,
                "expires_on": None,
                "professional_responsible_person_name": row.get("professional_responsible_person_name") or None,
                "notes": None,
            },
            build_entity=lambda: BusinessEligibilityVersion(
                business_eligibility_certificate_id=entity.id,
                version_no=1,
                certificate_number=row.get("linked_certificate_ids") or None,
                professional_responsible_person_name=row.get("professional_responsible_person_name") or None,
            ),
            options=resolved_options,
        )
        for part in (row.get("linked_certificate_ids") or "").split(";"):
            cert_legacy_id = parse_int(part)
            if cert_legacy_id is None or cert_legacy_id not in certificate_ids:
                continue
            _ensure_business_eligibility_link(
                session,
                stats,
                business_eligibility_version_id=version.id,
                certificate_id=certificate_ids[cert_legacy_id],
                options=resolved_options,
            )

    for raw_row in snapshot["db.Tdoi"]:
        row = normalize_row(raw_row)
        legacy_id = parse_int(row.get("ID", ""))
        row_number = source_row_number(row)
        site_id = _resolve_legacy_fk(
            session,
            stats,
            resolved_options,
            anomaly_rows,
            remediation_overrides,
            source_sheet="db.Tdoi",
            legacy_row_id=legacy_id,
            source_row_number_value=row_number,
            raw_value=row.get("site_legacy_id_ref", ""),
            reason="missing_site_fk",
            required_field="ID Cơ Sở",
            target_map=site_ids,
            confirmed_blanked_row_keys=confirmed_blanked_row_keys,
            confirmed_blanked_null_key_budgets=confirmed_blanked_null_key_budgets,
        )
        if site_id is None:
            skipped_rows["db.Tdoi"].append({"legacy_id": legacy_id, "reason": "missing_site_fk", "raw_fk": row.get("site_legacy_id_ref", "")})
            continue
        identity_key = _source_identity_key(legacy_id, row_number)
        expected_fields = {
            "legacy_change_request_id": legacy_id,
            "site_id": site_id,
            "scope_label": row.get("change_scope_label") or None,
            "description": row.get("change_description") or None,
            "submitted_on": parse_date(row.get("submitted_at", "")),
            "requester_name": row.get("requester_name") or None,
            "state": ChangeRequestState.EFFECTIVE if row.get("effective_on") else ChangeRequestState.RECEIVED,
        }
        entity = _ensure_entity(
            session,
            stats,
            table_name="change_request",
            model=ChangeRequest,
            entity_type=LegacyEntityType.CHANGE_REQUEST,
            legacy_field_name="legacy_change_request_id",
            identity_key=identity_key,
            expected_fields=expected_fields,
            build_entity=lambda expected_fields=expected_fields: ChangeRequest(**expected_fields),
            options=resolved_options,
        )
        if legacy_id is not None:
            change_ids[legacy_id] = entity.id
        _ensure_single_child(
            session,
            stats,
            table_name="change_approval",
            model=ChangeApproval,
            filters={"change_request_id": entity.id},
            expected_fields={
                "change_request_id": entity.id,
                "handled_on": parse_date(row.get("handled_on", "")),
                "handled_by_name": row.get("handled_by_name") or None,
                "result_label": row.get("assessment_result") or None,
                "effective_on": parse_date(row.get("effective_on", "")),
                "approval_reference": row.get("approval_reference") or None,
            },
            build_entity=lambda: ChangeApproval(
                change_request_id=entity.id,
                handled_on=parse_date(row.get("handled_on", "")),
                handled_by_name=row.get("handled_by_name") or None,
                result_label=row.get("assessment_result") or None,
                effective_on=parse_date(row.get("effective_on", "")),
                approval_reference=row.get("approval_reference") or None,
            ),
            options=resolved_options,
        )

    for raw_row in snapshot["db.Tdoi2"]:
        row = normalize_row(raw_row)
        legacy_id = parse_int(row.get("ID", ""))
        row_number = source_row_number(row)
        change_request_id = _resolve_legacy_fk(
            session,
            stats,
            resolved_options,
            anomaly_rows,
            remediation_overrides,
            source_sheet="db.Tdoi2",
            legacy_row_id=legacy_id,
            source_row_number_value=row_number,
            raw_value=row.get("change_request_legacy_id_ref", ""),
            reason="missing_change_request_fk",
            required_field="ID Gốc",
            target_map=change_ids,
            confirmed_blanked_row_keys=confirmed_blanked_row_keys,
            confirmed_blanked_null_key_budgets=confirmed_blanked_null_key_budgets,
        )
        if change_request_id is None:
            skipped_rows["db.Tdoi2"].append({"legacy_id": legacy_id, "reason": "missing_change_request_fk", "raw_fk": row.get("change_request_legacy_id_ref", "")})
            continue
        identity_key = _source_identity_key(legacy_id, row_number)
        expected_fields = {
            "legacy_change_detail_id": legacy_id,
            "change_request_id": change_request_id,
            "classification_id": parse_int(row.get("classification_id", "")),
            "classification_label": row.get("classification_label") or None,
            "approval_status": row.get("approval_status") or None,
            "old_value": row.get("old_value") or None,
            "new_value": row.get("new_value") or None,
            "note": row.get("note") or None,
        }
        _ensure_entity(
            session,
            stats,
            table_name="change_request_detail",
            model=ChangeRequestDetail,
            entity_type=None,
            legacy_field_name="legacy_change_detail_id",
            identity_key=identity_key,
            expected_fields=expected_fields,
            build_entity=lambda expected_fields=expected_fields: ChangeRequestDetail(**expected_fields),
            options=resolved_options,
        )

    _ensure_audit_event(session, stats, options=resolved_options)
    session.flush()
    return build_reconciliation(
        session,
        snapshot,
        skipped_rows,
        anomaly_rows,
        remediation_overrides or {},
        stats=stats,
    )


def build_reconciliation(
    session: Session,
    snapshot: dict[str, list[dict[str, str]]],
    skipped_rows: dict[str, list[dict[str, Any]]],
    anomaly_rows: list[dict[str, Any]],
    remediation_overrides: dict[str, dict[str, dict[str, Any]]],
    *,
    stats: ImportStats | None = None,
) -> dict[str, Any]:
    resolved_stats = stats or ImportStats()
    excluded_rows_by_sheet: dict[str, list[dict[str, Any]]] = {}
    for row in anomaly_rows:
        if row.get("status") != "excluded_confirmed_blanked":
            continue
        excluded_rows_by_sheet.setdefault(row["source_sheet"], []).append(
            {
                "source_row_key": row.get("source_row_key"),
                "legacy_row_id": row.get("legacy_row_id"),
                "reason": row.get("reason"),
                "status": row.get("status"),
            }
        )

    target_counts = {
        source_name: session.scalar(select(func.count()).select_from(model))
        for source_name, model in PRIMARY_TARGET_MAP.items()
    }
    source_counts = {source_name: len(rows) for source_name, rows in snapshot.items()}
    excluded_row_counts = {sheet: len(rows) for sheet, rows in excluded_rows_by_sheet.items()}
    effective_source_counts = {
        source_name: source_counts[source_name] - excluded_row_counts.get(source_name, 0)
        for source_name in PRIMARY_TARGET_MAP
    }
    mismatches = {
        source_name: {"source_count": source_counts[source_name], "target_count": target_counts[source_name]}
        for source_name in PRIMARY_TARGET_MAP
        if source_counts[source_name] != target_counts[source_name]
    }
    effective_mismatches = {
        source_name: {
            "effective_source_count": effective_source_counts[source_name],
            "target_count": target_counts[source_name],
            "excluded_count": excluded_row_counts.get(source_name, 0),
        }
        for source_name in PRIMARY_TARGET_MAP
        if effective_source_counts[source_name] != target_counts[source_name]
    }
    applied_override_count = sum(1 for row in anomaly_rows if row["status"] == "overridden")
    unresolved_anomaly_counts = {
        source_name: sum(
            1
            for row in anomaly_rows
            if row["source_sheet"] == source_name and row.get("status") not in {"excluded_confirmed_blanked", "overridden"}
        )
        for source_name in PRIMARY_TARGET_MAP
    }
    imported_row_counts = {
        source_name: source_counts[source_name] - len(skipped_rows.get(source_name, []))
        for source_name in PRIMARY_TARGET_MAP
    }
    source_balance = {
        source_name: {
            "source_count": source_counts[source_name],
            "imported_count": imported_row_counts[source_name],
            "intentionally_skipped_count": excluded_row_counts.get(source_name, 0),
            "unresolved_count": unresolved_anomaly_counts.get(source_name, 0),
            "skipped_count": len(skipped_rows.get(source_name, [])),
            "balanced": imported_row_counts[source_name] + len(skipped_rows.get(source_name, [])) == source_counts[source_name],
        }
        for source_name in PRIMARY_TARGET_MAP
    }
    return {
        "source_counts": source_counts,
        "effective_source_counts": effective_source_counts,
        "target_counts": target_counts,
        "mismatches": mismatches,
        "effective_mismatches": effective_mismatches,
        "skipped_rows": {sheet: len(rows) for sheet, rows in skipped_rows.items() if rows},
        "skipped_row_samples": {sheet: rows[:10] for sheet, rows in skipped_rows.items() if rows},
        "excluded_rows": excluded_row_counts,
        "excluded_row_samples": {sheet: rows[:10] for sheet, rows in excluded_rows_by_sheet.items()},
        "anomaly_rows": anomaly_rows,
        "applied_override_count": applied_override_count,
        "remediation_override_keys": sorted(remediation_overrides.keys()),
        "inserted_counts": dict(sorted(resolved_stats.inserted_counts.items())),
        "existing_counts": dict(sorted(resolved_stats.existing_counts.items())),
        "source_balance": source_balance,
        "derived_counts": {
            "case_application": session.scalar(select(func.count()).select_from(CaseApplication)),
            "case_assessment": session.scalar(select(func.count()).select_from(CaseAssessment)),
            "inspection_outcome": session.scalar(select(func.count()).select_from(InspectionOutcome)),
            "inspection_event": session.scalar(select(func.count()).select_from(InspectionEvent)),
            "certificate_version": session.scalar(select(func.count()).select_from(CertificateVersion)),
            "business_eligibility_version": session.scalar(select(func.count()).select_from(BusinessEligibilityVersion)),
            "business_eligibility_certificate_link": session.scalar(select(func.count()).select_from(BusinessEligibilityCertificateLink)),
            "change_approval": session.scalar(select(func.count()).select_from(ChangeApproval)),
            "legacy_id_map": session.scalar(select(func.count()).select_from(LegacyIdMap)),
            "migration_anomaly": session.scalar(select(func.count()).select_from(MigrationAnomaly)),
        },
    }


@dataclass
class Phase2Result:
    database_url: str
    reconciliation: dict[str, Any]
    report_path: Path


def import_workbook_to_database(
    session: Session,
    workbook_path: str | Path,
    report_path: str | Path,
    remediation_overrides: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> Phase2Result:
    snapshot = read_core_sheet_rows(workbook_path)
    reconciliation = import_snapshot(session, snapshot, remediation_overrides=remediation_overrides)
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Phase 2 Reconciliation Report", "", "## Source vs target counts", ""]
    for source_name in PRIMARY_TARGET_MAP:
        lines.append(f"- `{source_name}`: source `{reconciliation['source_counts'][source_name]}`, target `{reconciliation['target_counts'][source_name]}`")
    lines.extend(["", "## Effective source vs target counts", ""])
    for source_name in PRIMARY_TARGET_MAP:
        lines.append(
            f"- `{source_name}`: effective source `{reconciliation['effective_source_counts'][source_name]}`, "
            f"target `{reconciliation['target_counts'][source_name]}`, "
            f"excluded `{reconciliation['excluded_rows'].get(source_name, 0)}`"
        )
    lines.extend(["", "## Derived target counts", ""])
    for key, value in reconciliation["derived_counts"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Mismatches", ""])
    if reconciliation["mismatches"]:
        for key, value in reconciliation["mismatches"].items():
            lines.append(f"- `{key}`: source `{value['source_count']}`, target `{value['target_count']}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Effective mismatches after confirmed exclusions", ""])
    if reconciliation["effective_mismatches"]:
        for key, value in reconciliation["effective_mismatches"].items():
            lines.append(
                f"- `{key}`: effective source `{value['effective_source_count']}`, "
                f"target `{value['target_count']}`, excluded `{value['excluded_count']}`"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Skipped rows", ""])
    if reconciliation["skipped_rows"]:
        for key, value in reconciliation["skipped_rows"].items():
            lines.append(f"- `{key}`: skipped `{value}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Confirmed excluded blanked rows", ""])
    if reconciliation["excluded_rows"]:
        for key, value in reconciliation["excluded_rows"].items():
            lines.append(f"- `{key}`: excluded `{value}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Overrides", "", f"- applied overrides: `{reconciliation['applied_override_count']}`"])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return Phase2Result(str(session.get_bind().url), reconciliation, report_path)
