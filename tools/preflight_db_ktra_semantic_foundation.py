"""Read-only compatibility evidence for db.ktra semantic-foundation migration."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text


REQUIRED_DATABASE_NAME = "gxp_legacy_rehearsal"


def require_rehearsal_postgres(database_url: str) -> None:
    parsed = urlsplit(database_url)
    database_name = parsed.path.rsplit("/", 1)[-1]
    if parsed.scheme not in {"postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        raise RuntimeError("preflight requires an explicit PostgreSQL database URL")
    if database_name != REQUIRED_DATABASE_NAME:
        raise RuntimeError(f"preflight refuses database {database_name!r}; expected {REQUIRED_DATABASE_NAME!r}")


def normalize_role_label(value: str | None) -> str:
    value = str(value or "").replace("Đ", "D").replace("đ", "d")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", value).strip().casefold()


def _scalar(connection, statement: str) -> int:
    return int(connection.execute(text(statement)).scalar_one())


def _columns(connection, table_name: str) -> set[str]:
    return set(
        connection.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = :table_name"
            ),
            {"table_name": table_name},
        ).scalars()
    )


def run_preflight(database_url: str) -> dict[str, object]:
    require_rehearsal_postgres(database_url)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            actual_database = connection.execute(text("SELECT current_database()")).scalar_one()
            read_only = str(connection.execute(text("SHOW transaction_read_only")).scalar_one()).strip().lower()
            if actual_database != REQUIRED_DATABASE_NAME or read_only not in {"on", "true", "1"}:
                raise RuntimeError("preflight requires verified read-only gxp_legacy_rehearsal transaction")
            labels = Counter(
                normalize_role_label(row[0])
                for row in connection.execute(text("SELECT role_label FROM inspection_team_member"))
            )
            outcome_columns = _columns(connection, "inspection_outcome")
            plan_columns = _columns(connection, "inspection_plan")
            approval_table_present = connection.execute(
                text("SELECT to_regclass(current_schema() || '.inspection_approval_submission') IS NOT NULL")
            ).scalar_one()
            return {
                "database": actual_database,
                "transaction_read_only": True,
                "alembic_revision": connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none(),
                "inspection_team_member": {
                    "total": _scalar(connection, "SELECT count(*) FROM inspection_team_member"),
                    "sort_order_lte_zero": _scalar(connection, "SELECT count(*) FROM inspection_team_member WHERE sort_order <= 0"),
                    "duplicate_team_sort_order": _scalar(connection, "SELECT count(*) FROM (SELECT team_id, sort_order FROM inspection_team_member GROUP BY team_id, sort_order HAVING count(*) > 1) AS duplicates"),
                    "both_identity_ids": _scalar(connection, "SELECT count(*) FROM inspection_team_member WHERE inspector_profile_id IS NOT NULL AND person_id IS NOT NULL"),
                    "neither_identity_id": _scalar(connection, "SELECT count(*) FROM inspection_team_member WHERE inspector_profile_id IS NULL AND person_id IS NULL"),
                    "role_label_normalized_distribution": dict(sorted(labels.items())),
                    "deterministically_convertible_role_code": _scalar(connection, "SELECT count(*) FROM inspection_team_member WHERE sort_order >= 1"),
                    "not_deterministically_convertible_role_code": _scalar(connection, "SELECT count(*) FROM inspection_team_member WHERE sort_order < 1"),
                },
                "inspection_outcome": {
                    "row_count": _scalar(connection, "SELECT count(*) FROM inspection_outcome"),
                    "new_fields_present": sorted(
                        outcome_columns
                        & {"final_evaluation", "minutes_recorded_on", "minutes_recorded_time", "minutes_legacy_raw", "compliance_due_on"}
                    ),
                },
                "inspection_plan": {
                    "row_count": _scalar(connection, "SELECT count(*) FROM inspection_plan"),
                    "new_fields_present": sorted(plan_columns & {"decision_reference", "decision_date", "decision_legacy_raw"}),
                },
                "inspection_approval_submission": {"table_present": bool(approval_table_present)},
            }
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    print(json.dumps(run_preflight(args.database_url), ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
