from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.document.registry import load_curated_registry
from backend.app.document.seed_contract import (
    build_payload_builder_specs,
    build_template_binding_seeds,
    build_template_definition_seeds,
)


REGISTRY_PATH = ROOT / "artifacts/phase5/template_registry.curated.json"
OUTPUT_TEMPLATE_JSON = ROOT / "artifacts/phase5/template_seed.curated.json"
OUTPUT_TEMPLATE_MD = ROOT / "artifacts/phase5/template_seed.curated.md"
OUTPUT_PAYLOAD_JSON = ROOT / "artifacts/phase5/payload_builder_registry.json"
OUTPUT_PAYLOAD_MD = ROOT / "artifacts/phase5/payload_builder_registry.md"


def render_template_seed_markdown(template_seeds: list[dict], binding_seeds: list[dict]) -> str:
    lines = [
        "# Curated Template Seed Baseline",
        "",
        "## Template Definitions",
    ]
    for item in template_seeds:
        lines.append(
            f"- `{item['family_code']}` -> `{item['template_name']}` "
            f"| variant=`{item['variant_type']}` | scope=`{item['storage_scope']}` "
            f"| source_app=`{item['source_application']}`"
        )
    lines.extend(["", "## Template Bindings"])
    for item in binding_seeds:
        lines.append(
            f"- `{item['family_code']}` -> `{item['template_name']}` "
            f"| gxp=`{item['gxp_type'] or '*'}` | legacy_mode=`{item['legacy_mode'] or '*'}` "
            f"| scope=`{item['storage_scope']}`"
        )
    return "\n".join(lines) + "\n"


def render_payload_builder_markdown(payload_specs: list[dict]) -> str:
    lines = [
        "# Payload Builder Registry Baseline",
        "",
        "## Families",
    ]
    for item in payload_specs:
        sensitive_count = sum(1 for field in item["fields"] if field["sensitivity"] == "sensitive")
        lines.append(
            f"- `{item['family_code']}` | procedures=`{', '.join(item['source_procedures'])}` "
            f"| fields={len(item['fields'])} | sensitive={sensitive_count} "
            f"| copy_forward_required={item['copy_forward_required']}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    registry_entries = load_curated_registry(REGISTRY_PATH)
    template_seeds = [asdict(seed) for seed in build_template_definition_seeds(registry_entries)]
    binding_seeds = [asdict(seed) for seed in build_template_binding_seeds(registry_entries)]
    payload_specs = [asdict(spec) for spec in build_payload_builder_specs(registry_entries)]

    OUTPUT_TEMPLATE_JSON.write_text(
        json.dumps(
            {
                "template_definitions": template_seeds,
                "template_bindings": binding_seeds,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    OUTPUT_TEMPLATE_MD.write_text(
        render_template_seed_markdown(template_seeds, binding_seeds),
        encoding="utf-8",
    )
    OUTPUT_PAYLOAD_JSON.write_text(
        json.dumps({"payload_builders": payload_specs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    OUTPUT_PAYLOAD_MD.write_text(
        render_payload_builder_markdown(payload_specs),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
