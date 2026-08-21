from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "artifacts" / "phase6"
JSON_OUT = OUT_DIR / "environment_probe.json"
MD_OUT = OUT_DIR / "environment_probe.md"

WORD_PATHS = [
    Path(r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE"),
    Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE"),
    Path(r"C:\Program Files\Microsoft Office\Office16\WINWORD.EXE"),
    Path(r"C:\Program Files (x86)\Microsoft Office\Office16\WINWORD.EXE"),
]


def _run_powershell(command: str) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _json_powershell(command: str) -> Any:
    raw = _run_powershell(command)
    if not raw:
        return None
    return json.loads(raw)


def probe_environment() -> dict[str, Any]:
    winword_paths = [str(path) for path in WORD_PATHS if path.exists()]
    word_com = _run_powershell(
        "try { $w = New-Object -ComObject Word.Application; "
        "$v = $w.Version; $w.Quit(); "
        "@{ available = $true; version = $v } | ConvertTo-Json -Compress } "
        "catch { @{ available = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress }"
    )
    word_com_payload = json.loads(word_com) if word_com else {"available": False, "error": "unknown"}
    explorer_path = shutil.which("explorer.exe")
    tailscale_path = shutil.which("tailscale")
    smb_mappings = _json_powershell(
        "Get-SmbMapping | Select-Object LocalPath,RemotePath,Status | ConvertTo-Json -Compress"
    )
    if isinstance(smb_mappings, dict):
        smb_mappings = [smb_mappings]
    if smb_mappings is None:
        smb_mappings = []
    disconnected_mappings = [item for item in smb_mappings if str(item.get("Status", "")).lower() != "ok"]
    active_mappings = [item for item in smb_mappings if str(item.get("Status", "")).lower() == "ok"]
    return {
        "generated_on": "2026-08-14",
        "word_executable_paths": winword_paths,
        "word_com": word_com_payload,
        "explorer_executable": explorer_path,
        "tailscale_executable": tailscale_path,
        "smb_mappings": smb_mappings,
        "active_smb_mappings": active_mappings,
        "disconnected_smb_mappings": disconnected_mappings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 6 Environment Probe",
        "",
        f"- Generated on: `{report['generated_on']}`",
        f"- Word executable found: `{bool(report['word_executable_paths'])}`",
        f"- Word COM available: `{report['word_com'].get('available')}`",
        f"- Explorer executable found: `{bool(report['explorer_executable'])}`",
        f"- Tailscale executable found: `{bool(report['tailscale_executable'])}`",
        f"- SMB mappings observed: `{len(report['smb_mappings'])}`",
        f"- Active SMB mappings: `{len(report['active_smb_mappings'])}`",
        f"- Disconnected SMB mappings: `{len(report['disconnected_smb_mappings'])}`",
        "",
        "## SMB Mappings",
        "",
    ]
    if not report["smb_mappings"]:
        lines.append("- none")
    for item in report["smb_mappings"]:
        lines.append(
            f"- local=`{item.get('LocalPath')}` remote=`{item.get('RemotePath')}` status=`{item.get('Status')}`"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = probe_environment()
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
