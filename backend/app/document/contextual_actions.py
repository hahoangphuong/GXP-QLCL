from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.app.db.models.phase1 import CapaCycle


WorkflowStep = Literal["Hồ sơ", "Kiểm tra", "Khắc phục", "Xử lý", "Chứng nhận GxP", "Chứng nhận ĐĐK"]
ContextClassification = Literal["PROVEN", "AMBIGUOUS", "UNMAPPED", "NOT_APPLICABLE_TO_CASE"]
TypedCreateReadiness = Literal[
    "READY_CREATE_OPEN_HISTORY",
    "READY_OPEN_HISTORY",
    "READY_READ_ONLY",
    "TEMPLATE_READY_BUT_BACKEND_ACTION_MISSING",
    "STORAGE_WRITE_CONTRACT_MISSING",
    "BUSINESS_INPUT_CONTRACT_MISSING",
    "LEGACY_ONLY_UNRESOLVED",
    "OTHER_BLOCKED",
]
ParentScope = Literal["case", "capa_cycle", "change_request"]


@dataclass(frozen=True)
class CaseDocumentContextSpec:
    family_code: str
    label: str
    workflow_step: WorkflowStep | None
    parent_scope: ParentScope
    classification: ContextClassification
    create_readiness: TypedCreateReadiness
    legacy_host_procedure: str
    legacy_case_numbers: tuple[int, ...]
    round_no: int | None = None


_CASE_DOCUMENT_CONTEXT_SPECS: tuple[CaseDocumentContextSpec, ...] = (
    CaseDocumentContextSpec(
        family_code="INSPECTION_BBTD_HOSO_DK",
        label="Biên bản thẩm định",
        workflow_step="Hồ sơ",
        parent_scope="case",
        classification="PROVEN",
        create_readiness="BUSINESS_INPUT_CONTRACT_MISSING",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_numbers=(1,),
    ),
    CaseDocumentContextSpec(
        family_code="INSPECTION_QD_KT",
        label="Quyết định kiểm tra",
        workflow_step="Kiểm tra",
        parent_scope="case",
        classification="PROVEN",
        create_readiness="BUSINESS_INPUT_CONTRACT_MISSING",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_numbers=(2,),
    ),
    CaseDocumentContextSpec(
        family_code="INSPECTION_KE_HOACH_KT",
        label="Kế hoạch kiểm tra",
        workflow_step="Kiểm tra",
        parent_scope="case",
        classification="PROVEN",
        create_readiness="BUSINESS_INPUT_CONTRACT_MISSING",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_numbers=(3,),
    ),
    CaseDocumentContextSpec(
        family_code="INSPECTION_BB_KT",
        label="Biên bản kiểm tra",
        workflow_step="Kiểm tra",
        parent_scope="case",
        classification="PROVEN",
        create_readiness="BUSINESS_INPUT_CONTRACT_MISSING",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_numbers=(4,),
    ),
    CaseDocumentContextSpec(
        family_code="INSPECTION_CAPA_LAN_1",
        label="Đánh giá CAPA 1",
        workflow_step="Khắc phục",
        parent_scope="capa_cycle",
        classification="PROVEN",
        create_readiness="BUSINESS_INPUT_CONTRACT_MISSING",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_numbers=(5,),
        round_no=1,
    ),
    CaseDocumentContextSpec(
        family_code="INSPECTION_CAPA_LAN_2",
        label="Đánh giá CAPA 2",
        workflow_step="Khắc phục",
        parent_scope="capa_cycle",
        classification="PROVEN",
        create_readiness="BUSINESS_INPUT_CONTRACT_MISSING",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_numbers=(6,),
        round_no=2,
    ),
    CaseDocumentContextSpec(
        family_code="INSPECTION_PT_PCT",
        label="Phiếu trình PCT",
        workflow_step="Xử lý",
        parent_scope="case",
        classification="PROVEN",
        create_readiness="BUSINESS_INPUT_CONTRACT_MISSING",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_numbers=(7,),
    ),
    CaseDocumentContextSpec(
        family_code="INSPECTION_PT_CT",
        label="Phiếu trình CT",
        workflow_step="Xử lý",
        parent_scope="case",
        classification="PROVEN",
        create_readiness="BUSINESS_INPUT_CONTRACT_MISSING",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_numbers=(8,),
    ),
    CaseDocumentContextSpec(
        family_code="CERTIFICATE_DECISION",
        label="Quyết định cấp CC",
        workflow_step="Xử lý",
        parent_scope="case",
        classification="PROVEN",
        create_readiness="BUSINESS_INPUT_CONTRACT_MISSING",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_numbers=(9,),
    ),
    CaseDocumentContextSpec(
        family_code="CERTIFICATE_ISSUANCE_WORD",
        label="Chứng chỉ GPs",
        workflow_step="Chứng nhận GxP",
        parent_scope="case",
        classification="PROVEN",
        create_readiness="BUSINESS_INPUT_CONTRACT_MISSING",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_numbers=(10,),
    ),
    CaseDocumentContextSpec(
        family_code="RISK_MANAGEMENT_WORKSHEET",
        label="Bảng công cụ quản lý rủi ro",
        workflow_step="Xử lý",
        parent_scope="case",
        classification="PROVEN",
        create_readiness="BUSINESS_INPUT_CONTRACT_MISSING",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_numbers=(11,),
    ),
    CaseDocumentContextSpec(
        family_code="STATUS_CONFIRMATION_LETTER",
        label="Xác nhận tình trạng",
        workflow_step="Xử lý",
        parent_scope="case",
        classification="PROVEN",
        create_readiness="BUSINESS_INPUT_CONTRACT_MISSING",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_numbers=(12,),
    ),
    CaseDocumentContextSpec(
        family_code="ASSESSMENT_MINUTES",
        label="Biên bản đánh giá",
        workflow_step=None,
        parent_scope="case",
        classification="AMBIGUOUS",
        create_readiness="LEGACY_ONLY_UNRESOLVED",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_numbers=(15,),
    ),
)


def list_case_document_context_specs() -> tuple[CaseDocumentContextSpec, ...]:
    return _CASE_DOCUMENT_CONTEXT_SPECS


def list_case_document_labels() -> dict[str, str]:
    return {spec.family_code: spec.label for spec in _CASE_DOCUMENT_CONTEXT_SPECS}


def get_case_document_context_spec(family_code: str) -> CaseDocumentContextSpec | None:
    for spec in _CASE_DOCUMENT_CONTEXT_SPECS:
        if spec.family_code == family_code:
            return spec
    return None


def build_case_contextual_document_specs(capa_cycles: list[CapaCycle]) -> tuple[tuple[CaseDocumentContextSpec, str], ...]:
    items: list[tuple[CaseDocumentContextSpec, str]] = []
    cycle_by_round = {cycle.round_no: cycle.id for cycle in capa_cycles}
    for spec in _CASE_DOCUMENT_CONTEXT_SPECS:
        if spec.classification != "PROVEN" or spec.workflow_step is None:
            continue
        if spec.parent_scope == "case":
            items.append((spec, ""))
            continue
        if spec.parent_scope == "capa_cycle" and spec.round_no is not None:
            cycle_id = cycle_by_round.get(spec.round_no)
            if cycle_id is not None:
                items.append((spec, cycle_id))
    return tuple(items)


def build_document_action_states(
    *,
    open_available: bool,
    history_available: bool,
    create_readiness: TypedCreateReadiness,
    permissions: frozenset[str],
    family_code: str,
    parent_scope: ParentScope,
    parent_id: str,
    document_type_code: str | None,
) -> list[dict[str, object]]:
    def available_or_reason(
        *,
        action_key: str,
        label: str,
        required_permissions: tuple[str, ...],
        supported: bool,
        unavailable_reason: str,
    ) -> dict[str, object]:
        missing = [permission for permission in required_permissions if permission not in permissions]
        if missing:
            return {
                "action_key": action_key,
                "label": label,
                "available": False,
                "disabled_reason": (
                    "Tài khoản hiện tại không có quyền đọc tài liệu."
                    if action_key in {"open", "history"}
                    else "Tài khoản hiện tại không có quyền tạo tài liệu."
                ),
                "required_permissions": list(required_permissions),
            }
        if supported:
            return {
                "action_key": action_key,
                "label": label,
                "available": True,
                "disabled_reason": None,
                "required_permissions": list(required_permissions),
            }
        return {
            "action_key": action_key,
            "label": label,
            "available": False,
            "disabled_reason": unavailable_reason,
            "required_permissions": list(required_permissions),
        }

    create_reason_by_readiness = {
        "TEMPLATE_READY_BUT_BACKEND_ACTION_MISSING": (
            "Template đã được xác định nhưng chưa có typed backend action để tạo tài liệu này."
        ),
        "STORAGE_WRITE_CONTRACT_MISSING": (
            "Chưa có contract ghi storage an toàn, xác định đích và chống ghi đè cho loại tài liệu này."
        ),
        "BUSINESS_INPUT_CONTRACT_MISSING": (
            "Thiếu contract input nghiệp vụ typed theo ngữ cảnh; không hiển thị thao tác tạo generic."
        ),
        "LEGACY_ONLY_UNRESOLVED": (
            "Family legacy chưa có owner mapping/workflow đủ chắc chắn để tạo tài liệu."
        ),
        "OTHER_BLOCKED": "Tạo tài liệu đang bị chặn bởi contract backend chưa hoàn tất.",
        "READY_OPEN_HISTORY": "Loại tài liệu này hiện chỉ hỗ trợ mở và xem lịch sử tài liệu đã có.",
        "READY_READ_ONLY": "Loại tài liệu này chỉ hỗ trợ theo dõi hiện trạng trong slice hiện tại.",
    }
    create_reason = create_reason_by_readiness.get(
        create_readiness,
        "Chưa có typed backend create contract owner-safe cho loại tài liệu này.",
    )
    create_permission_missing = "document.write" not in permissions
    create_metadata = {
        "reason_code": (
            "permission_denied"
            if create_permission_missing
            else None if create_readiness == "READY_CREATE_OPEN_HISTORY" else create_readiness.lower()
        ),
        "create_readiness": create_readiness,
        "family_code": family_code,
        "parent_scope": parent_scope,
        "parent_id": parent_id,
        "document_type_code": document_type_code,
    }

    return [
        available_or_reason(
            action_key="open",
            label="Mở",
            required_permissions=("document.read",),
            supported=open_available,
            unavailable_reason="Chưa có tệp hiện hành để mở.",
        ),
        available_or_reason(
            action_key="create",
            label="Tạo",
            required_permissions=("document.write",),
            supported=create_readiness == "READY_CREATE_OPEN_HISTORY",
            unavailable_reason=create_reason,
        ) | create_metadata,
        available_or_reason(
            action_key="history",
            label="Lịch sử",
            required_permissions=("document.read",),
            supported=history_available,
            unavailable_reason="Chưa có lịch sử tài liệu để xem.",
        ),
    ]
