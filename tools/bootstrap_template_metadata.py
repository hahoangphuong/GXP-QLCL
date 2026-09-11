from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.session import build_session_factory
from backend.app.document.template_metadata_bootstrap import (
    TemplateMetadataReadinessError,
    bootstrap_default_template_metadata,
)
from backend.app.document.seed_runtime import TemplateSeedError


class TemplateMetadataBootstrapError(RuntimeError):
    pass


def bootstrap_template_metadata(*, database_url: str, dry_run: bool = False) -> tuple[object, object]:
    if not database_url.strip():
        raise TemplateMetadataBootstrapError("--database-url must not be blank.")
    factory = build_session_factory(database_url)
    bind = factory.kw.get("bind")
    session = factory()
    try:
        result = bootstrap_default_template_metadata(session)
        if dry_run:
            session.rollback()
        else:
            session.commit()
        return result
    except (TemplateSeedError, TemplateMetadataReadinessError) as exc:
        session.rollback()
        raise TemplateMetadataBootstrapError(str(exc)) from exc
    except Exception as exc:
        session.rollback()
        raise TemplateMetadataBootstrapError("Template metadata bootstrap failed.") from exc
    finally:
        session.close()
        if bind is not None:
            bind.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap canonical Phase 5 template metadata into an explicit database.")
    parser.add_argument("--database-url", required=True, help="Explicit target database URL.")
    parser.add_argument("--dry-run", action="store_true", help="Validate the bootstrap candidate without committing it.")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        seed, readiness = bootstrap_template_metadata(database_url=args.database_url, dry_run=args.dry_run)
    except (TemplateMetadataBootstrapError, SystemExit) as exc:
        if isinstance(exc, SystemExit):
            raise
        print(f"ERROR: {exc}", file=sys.stderr)
        print("TEMPLATE_METADATA_BOOTSTRAP=FAIL", file=sys.stderr)
        return 1
    print("TEMPLATE_METADATA_BOOTSTRAP=PASS")
    print(f"definitions_created={seed.template_definitions_created}")
    print(f"definitions_updated={seed.template_definitions_updated}")
    print(f"bindings_created={seed.template_bindings_created}")
    print(f"bindings_updated={seed.template_bindings_updated}")
    print(f"canonical_template_definitions={readiness.canonical_template_definitions}")
    print(f"canonical_template_bindings={readiness.canonical_template_bindings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
