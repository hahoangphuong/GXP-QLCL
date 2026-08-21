from __future__ import annotations

from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend.app.db.models import Base


def render_postgresql_schema() -> str:
    statements = []
    for table in Base.metadata.sorted_tables:
        statements.append(f"{CreateTable(table).compile(dialect=postgresql.dialect())};")
    return "\n\n".join(statements) + "\n"


def write_schema_sql(output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_postgresql_schema(), encoding="utf-8")
    return path
