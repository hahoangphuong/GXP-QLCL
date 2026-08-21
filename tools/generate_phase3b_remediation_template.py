from __future__ import annotations

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "phase2" / "reconciliation.json"
OUT_DIR = ROOT / "artifacts" / "phase3b"
TEMPLATE_PATH = OUT_DIR / "remediation_overrides.template.json"
DETAILS_PATH = OUT_DIR / "remediation_candidates.json"
UNKEYED_PATH = OUT_DIR / "remediation_unkeyed_anomalies.json"


REMEDIATION_KEY_BY_REASON = {
    "missing_company_fk": "company_legacy_id",
    "missing_site_fk": "site_legacy_id",
    "missing_case_fk": "case_legacy_id",
    "missing_change_request_fk": "change_request_legacy_id",
}


def main() -> int:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    anomalies = data.get("anomaly_rows", [])
    overrides: dict[str, dict[str, dict[str, None]]] = {}
    candidates: dict[str, list[dict[str, str | None]]] = {}
    unkeyed: dict[str, list[dict[str, str | None]]] = {}

    for row in anomalies:
        if row.get("status") != "open":
            continue
        sheet = row["source_sheet"]
        row_key = row.get("source_row_key") or row.get("legacy_row_id")
        reason = row["reason"]
        remediation_key = REMEDIATION_KEY_BY_REASON.get(reason)
        if not remediation_key:
            continue
        if not row_key:
            unkeyed.setdefault(sheet, []).append(row)
            continue
        overrides.setdefault(sheet, {})[row_key] = {remediation_key: None}
        candidates.setdefault(sheet, []).append(row)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATE_PATH.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
    DETAILS_PATH.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    UNKEYED_PATH.write_text(json.dumps(unkeyed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {TEMPLATE_PATH}")
    print(f"Wrote {DETAILS_PATH}")
    print(f"Wrote {UNKEYED_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
