from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.document.service_contract import DocumentPayloadField
from backend.app.document.template_contract_runtime import (
    build_scalar_replacement_plan,
    build_scalar_replacement_plan_for_template,
    load_default_template_contract_reconciliation,
)
from tools.audit_phase5_real_templates import normalize_name


def find_template(prefix: str) -> Path:
    templates_root = ROOT / "legacy" / "Templates"
    matches = [
        path
        for path in templates_root.iterdir()
        if path.is_file() and normalize_name(path.name).startswith(prefix)
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one template for prefix={prefix!r}, found {len(matches)}")
    return matches[0]


def main() -> None:
    families = load_default_template_contract_reconciliation()
    dkkd_template_bytes = find_template("z2 giay chung nhan ddkkdd dieu chinh").read_bytes()

    ddkd_plan = build_scalar_replacement_plan_for_template(
        families,
        "DDKD_CERTIFICATE",
        (
            DocumentPayloadField(field_name="Cap_lan", value="Lan 2", source="smoke"),
            DocumentPayloadField(field_name="TenCty", value="Cong ty A", source="smoke"),
            DocumentPayloadField(field_name="DiachiCoso", value="Dia chi A", source="smoke"),
        ),
        template_bytes=dkkd_template_bytes,
    )
    capa_plan = build_scalar_replacement_plan(
        families,
        "INSPECTION_CAPA_LAN_1",
        (
            DocumentPayloadField(field_name="CAPAx", value="Bang CAPA", source="smoke"),
            DocumentPayloadField(field_name="DsTT", value="Bang ton tai", source="smoke"),
        ),
    )
    qdkt_plan = build_scalar_replacement_plan(
        families,
        "INSPECTION_QD_KT",
        (
            DocumentPayloadField(field_name="QDKT", value="12/QD", source="smoke"),
            DocumentPayloadField(field_name="TT2", value="Doan kiem tra", source="smoke"),
        ),
    )

    print(
        json.dumps(
            {
                "ddkd_mode": ddkd_plan.mode,
                "ddkd_replacements": ddkd_plan.bookmark_replacements,
                "capa_mode": capa_plan.mode,
                "capa_replacements": capa_plan.bookmark_replacements,
                "qdkt_mode": qdkt_plan.mode,
                "qdkt_replacements": qdkt_plan.bookmark_replacements,
                "qdkt_passthrough_fields": list(qdkt_plan.passthrough_input_fields),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
