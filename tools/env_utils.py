from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import shlex
import tempfile
from typing import Mapping


def _decode_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        try:
            decoded = ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"Invalid quoted env value: {raw_value!r}") from exc
        if not isinstance(decoded, str):
            raise ValueError(f"Env value must decode to string: {raw_value!r}")
        return decoded
    return value


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError(f"Invalid env line: {raw_line!r}")
        values[key.strip()] = _decode_env_value(value)
    return values


def serialize_systemd_env_value(value: str) -> str:
    return shlex.quote(value)


def parse_systemd_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, raw_value = raw_line.partition("=")
        if not separator:
            raise ValueError(f"Invalid systemd env line: {raw_line!r}")
        decoded = shlex.split(raw_value, posix=True)
        if len(decoded) != 1:
            raise ValueError(f"Systemd env value must decode to a single token: {raw_line!r}")
        values[key.strip()] = decoded[0]
    return values


def serialize_systemd_environment_file_contents(values: Mapping[str, str]) -> str:
    lines: list[str] = []
    for raw_key, raw_value in values.items():
        key = str(raw_key).strip()
        if not key:
            raise ValueError("Systemd env mappings require non-blank keys.")
        value = "" if raw_value is None else str(raw_value)
        lines.append(f"{key}={serialize_systemd_env_value(value)}")
    return "\n".join(lines) + "\n"


def write_systemd_environment_file(path: Path, values: Mapping[str, str]) -> None:
    payload = serialize_systemd_environment_file_contents(values)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise


def build_env_map_from_dotenv(
    path: Path,
    *,
    exclude_keys: tuple[str, ...] = (),
    overrides: Mapping[str, str] | None = None,
    collapse_escaped_backslashes: bool = False,
) -> dict[str, str]:
    values = parse_env_file(path)
    if collapse_escaped_backslashes:
        values = {key: value.replace("\\\\", "\\") for key, value in values.items()}
    for key in exclude_keys:
        values.pop(key, None)
    if overrides:
        for key, value in overrides.items():
            values[str(key)] = str(value)
    return values


def write_yaml_env_file(path: Path, values: Mapping[str, str]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for raw_key, raw_value in values.items():
            key = str(raw_key).strip()
            if not key:
                raise ValueError("YAML env mappings require non-blank keys.")
            value = "" if raw_value is None else str(raw_value)
            fh.write(f"{key}: {json.dumps(value, ensure_ascii=False)}\n")


def dotenv_to_yaml_env_file(
    source_path: Path,
    output_path: Path,
    *,
    exclude_keys: tuple[str, ...] = (),
    overrides: Mapping[str, str] | None = None,
    collapse_escaped_backslashes: bool = False,
) -> dict[str, str]:
    values = build_env_map_from_dotenv(
        source_path,
        exclude_keys=exclude_keys,
        overrides=overrides,
        collapse_escaped_backslashes=collapse_escaped_backslashes,
    )
    write_yaml_env_file(output_path, values)
    return values
