from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.env_utils import parse_env_file


POSTGRES_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


@dataclass(frozen=True)
class PrivatePostgresAccess:
    client_cidr: str
    db_name: str
    runtime_user: str
    migrator_user: str

    def render_hba_rules(self) -> tuple[str, ...]:
        rules = (
            f"hostssl {self.db_name} {self.runtime_user} {self.client_cidr} scram-sha-256",
            f"hostssl {self.db_name} {self.migrator_user} {self.client_cidr} scram-sha-256",
        )
        return tuple(dict.fromkeys(rules))


@dataclass(frozen=True)
class VmPostgresConfig:
    listen_addresses: tuple[str, ...]
    private_access: PrivatePostgresAccess | None

    @property
    def listen_addresses_csv(self) -> str:
        return ",".join(self.listen_addresses)

    @property
    def private_hba_rules(self) -> tuple[str, ...]:
        if self.private_access is None:
            return ()
        return self.private_access.render_hba_rules()


def _csv_values(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _normalize_listen_address(raw: str, errors: list[str]) -> str | None:
    if raw == "localhost":
        raw = "127.0.0.1"
    if raw == "*":
        errors.append("PG_LISTEN_ADDRESSES must not include wildcard *.")
        return None
    if raw == "0.0.0.0":
        errors.append("PG_LISTEN_ADDRESSES must not include 0.0.0.0.")
        return None
    try:
        parsed = ipaddress.ip_address(raw)
    except ValueError:
        errors.append(f"PG_LISTEN_ADDRESSES contains an invalid IP address: {raw!r}.")
        return None
    if parsed.version != 4:
        errors.append(f"PG_LISTEN_ADDRESSES only supports IPv4 addresses for the VM baseline, got {raw!r}.")
        return None
    if parsed.is_loopback:
        return "127.0.0.1"
    if not parsed.is_private:
        errors.append(f"PG_LISTEN_ADDRESSES must stay on loopback or RFC1918 private IPv4 addresses, got {raw!r}.")
        return None
    return raw


def _normalize_listen_addresses(source: dict[str, str], errors: list[str]) -> tuple[str, ...]:
    raw = (source.get("PG_LISTEN_ADDRESSES", "") or "").strip() or "127.0.0.1"
    values = _csv_values(raw)
    if not values:
        errors.append("PG_LISTEN_ADDRESSES must not be blank.")
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _normalize_listen_address(value, errors)
        if item is None or item in seen:
            continue
        normalized.append(item)
        seen.add(item)
    if "127.0.0.1" not in seen:
        errors.append("PG_LISTEN_ADDRESSES must include 127.0.0.1 so the GXP localhost connection path remains intact.")
    return tuple(normalized)


def _require_private_value(source: dict[str, str], key: str, errors: list[str]) -> str:
    value = (source.get(key, "") or "").strip()
    if not value:
        errors.append(f"{key} is required when configuring private PostgreSQL client access.")
    return value


def _validate_identifier(kind: str, value: str, errors: list[str], key: str) -> str:
    if value.lower() == "all":
        errors.append(f"{key} must not be all.")
        return value
    if not POSTGRES_IDENTIFIER_PATTERN.fullmatch(value):
        errors.append(f"{key} must be a simple PostgreSQL {kind} identifier.")
    return value


def _parse_private_access(source: dict[str, str], errors: list[str]) -> PrivatePostgresAccess | None:
    keys = (
        "PG_PRIVATE_CLIENT_CIDR",
        "PG_PRIVATE_DB_NAME",
        "PG_PRIVATE_RUNTIME_USER",
        "PG_PRIVATE_MIGRATOR_USER",
    )
    if not any((source.get(key, "") or "").strip() for key in keys):
        return None

    client_cidr = _require_private_value(source, "PG_PRIVATE_CLIENT_CIDR", errors)
    db_name = _validate_identifier("database", _require_private_value(source, "PG_PRIVATE_DB_NAME", errors), errors, "PG_PRIVATE_DB_NAME")
    runtime_user = _validate_identifier("role", _require_private_value(source, "PG_PRIVATE_RUNTIME_USER", errors), errors, "PG_PRIVATE_RUNTIME_USER")
    migrator_user = _validate_identifier("role", _require_private_value(source, "PG_PRIVATE_MIGRATOR_USER", errors), errors, "PG_PRIVATE_MIGRATOR_USER")

    try:
        network = ipaddress.ip_network(client_cidr, strict=False)
    except ValueError:
        errors.append(f"PG_PRIVATE_CLIENT_CIDR must be a valid CIDR, got {client_cidr!r}.")
        return None
    if network.version != 4:
        errors.append("PG_PRIVATE_CLIENT_CIDR must be an IPv4 CIDR for the VM baseline.")
    elif not network.is_private:
        errors.append("PG_PRIVATE_CLIENT_CIDR must stay within an RFC1918 private IPv4 range.")
    if network.prefixlen == 0:
        errors.append("PG_PRIVATE_CLIENT_CIDR must not be an open network like 0.0.0.0/0.")

    if errors:
        return None
    return PrivatePostgresAccess(
        client_cidr=str(network),
        db_name=db_name,
        runtime_user=runtime_user,
        migrator_user=migrator_user,
    )


def validate_vm_postgres_config(source: dict[str, str] | None = None) -> tuple[VmPostgresConfig | None, list[str]]:
    values = os.environ if source is None else source
    errors: list[str] = []
    listen_addresses = _normalize_listen_addresses(values, errors)
    private_access = _parse_private_access(values, errors)
    if errors:
        return None, errors
    return VmPostgresConfig(listen_addresses=listen_addresses, private_access=private_access), []


def render_json(source: dict[str, str] | None = None) -> str:
    config, errors = validate_vm_postgres_config(source)
    if errors or config is None:
        raise ValueError("\n".join(errors))
    return json.dumps(
        {
            "listen_addresses": list(config.listen_addresses),
            "listen_addresses_csv": config.listen_addresses_csv,
            "private_hba_rules": list(config.private_hba_rules),
        },
        ensure_ascii=False,
    )


def _load_source_from_args(args: list[str]) -> dict[str, str]:
    if not args:
        return dict(os.environ)
    if len(args) != 1:
        raise ValueError("render-json accepts at most one runtime env path.")
    return dict(parse_env_file(Path(args[0])))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "render-json":
        print("Usage: python tools/vm_postgres_config.py render-json [/path/to/runtime.env]", file=sys.stderr)
        return 2
    try:
        print(render_json(_load_source_from_args(args[1:])))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
