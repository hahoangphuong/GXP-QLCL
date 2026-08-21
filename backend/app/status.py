from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def _load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_application_status() -> dict[str, Any]:
    phase3 = _load_json_if_exists(ROOT / "artifacts" / "phase3r" / "phase3_final_closeout.json")
    phase4 = _load_json_if_exists(ROOT / "artifacts" / "phase4" / "phase4_final_closeout.json")
    phase5 = _load_json_if_exists(ROOT / "artifacts" / "phase5" / "phase5_final_closeout.json")
    phase6 = _load_json_if_exists(ROOT / "artifacts" / "phase6" / "phase6_final_closeout.json")
    phase7 = _load_json_if_exists(ROOT / "artifacts" / "phase7" / "phase7_final_closeout.json")
    phase3s = _load_json_if_exists(
        ROOT / "artifacts" / "phase3s" / "current_projection_conflict_decisions.summary.json"
    )

    return {
        "phase3_status": None if phase3 is None else phase3.get("phase3_status"),
        "phase4_status": None if phase4 is None else phase4.get("phase4_status"),
        "phase5_status": None if phase5 is None else phase5.get("phase5_status"),
        "phase6_status": None if phase6 is None else phase6.get("phase6_status"),
        "phase7_status": None if phase7 is None else phase7.get("phase7_status"),
        "current_projection_conflicts_status": None if phase3s is None else phase3s.get("overall_status"),
        "current_projection_conflicts_unresolved_count": None
        if phase3s is None
        else phase3s.get("unresolved_count"),
    }
