from __future__ import annotations

import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = {
    "service": ROOT / "infra" / "vm" / "gxp-web.service",
    "nginx": ROOT / "infra" / "vm" / "nginx.gxp.conf",
}
MARKER_PATTERN = re.compile(r"{{[A-Z0-9_]+}}")


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _service_replacement_map() -> dict[str, str]:
    app_user = os.environ.get("VM_APP_USER", "").strip() or "gxp"
    app_group = os.environ.get("VM_APP_GROUP", "").strip() or app_user
    current_backend_release_link = _required_env("VM_CURRENT_BACKEND_RELEASE_LINK")
    current_backend_venv_link = _required_env("VM_CURRENT_BACKEND_VENV_LINK")
    service_working_directory = os.environ.get("VM_SERVICE_WORKING_DIRECTORY", "").strip() or current_backend_release_link
    service_executable = os.environ.get("VM_SERVICE_EXECUTABLE", "").strip() or f"{current_backend_venv_link}/bin/uvicorn"
    service_environment_file = os.environ.get("VM_SERVICE_ENVIRONMENT_FILE", "").strip() or _required_env("VM_SYSTEMD_ENV_FILE")
    return {
        "{{VM_APP_USER}}": app_user,
        "{{VM_APP_GROUP}}": app_group,
        "{{VM_SERVICE_WORKING_DIRECTORY}}": service_working_directory,
        "{{VM_SERVICE_EXECUTABLE}}": service_executable,
        "{{VM_SERVICE_ENVIRONMENT_FILE}}": service_environment_file,
        "{{APP_PORT}}": os.environ.get("APP_PORT", "").strip() or "8000",
    }


def _nginx_replacement_map() -> dict[str, str]:
    public_base_url = _required_env("PUBLIC_BASE_URL")
    parsed = urlparse(public_base_url)
    server_name = os.environ.get("NGINX_SERVER_NAME", "").strip() or parsed.hostname or "_"
    return {
        "{{NGINX_SERVER_NAME}}": server_name,
        "{{VM_TLS_CERT_PATH}}": _required_env("VM_TLS_CERT_PATH"),
        "{{VM_TLS_KEY_PATH}}": _required_env("VM_TLS_KEY_PATH"),
        "{{GXP_FRONTEND_DIST_ROOT}}": _required_env("GXP_FRONTEND_DIST_ROOT"),
        "{{APP_PORT}}": os.environ.get("APP_PORT", "").strip() or "8000",
    }


def _replacement_map(kind: str) -> dict[str, str]:
    if kind == "service":
        return _service_replacement_map()
    if kind == "nginx":
        return _nginx_replacement_map()
    raise ValueError(f"Unsupported template kind: {kind}")


def render_template(kind: str, output_path: Path) -> int:
    template_path = TEMPLATES[kind]
    rendered = template_path.read_text(encoding="utf-8")
    for marker, replacement in _replacement_map(kind).items():
        rendered = rendered.replace(marker, replacement)
    unresolved = sorted(set(MARKER_PATTERN.findall(rendered)))
    if unresolved:
        raise RuntimeError(
            f"Template {kind} still contains unresolved markers: {', '.join(unresolved)}"
        )
    output_path.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] not in TEMPLATES:
        print("Usage: python tools/render_vm_runtime_assets.py {service|nginx} /output/path", file=sys.stderr)
        return 2
    return render_template(args[0], Path(args[1]))


if __name__ == "__main__":
    raise SystemExit(main())
