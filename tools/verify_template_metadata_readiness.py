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
    verify_default_template_metadata,
)


class TemplateMetadataReadinessCliError(RuntimeError):
    pass


def verify_template_metadata_readiness(*, database_url: str):
    if not database_url.strip():
        raise TemplateMetadataReadinessCliError("--database-url must not be blank.")
    factory = build_session_factory(database_url)
    bind = factory.kw.get("bind")
    session = factory()
    try:
        return verify_default_template_metadata(session)
    except TemplateMetadataReadinessError as exc:
        raise TemplateMetadataReadinessCliError(str(exc)) from exc
    except Exception as exc:
        raise TemplateMetadataReadinessCliError("Template metadata readiness verification failed.") from exc
    finally:
        session.rollback()
        session.close()
        if bind is not None:
            bind.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify canonical Phase 5 template metadata in an explicit database.")
    parser.add_argument("--database-url", required=True, help="Explicit target database URL.")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        summary = verify_template_metadata_readiness(database_url=args.database_url)
    except (TemplateMetadataReadinessCliError, SystemExit) as exc:
        if isinstance(exc, SystemExit):
            raise
        print(f"ERROR: {exc}", file=sys.stderr)
        print("TEMPLATE_METADATA_READINESS=FAIL", file=sys.stderr)
        return 1
    print("TEMPLATE_METADATA_READINESS=PASS")
    print(f"canonical_template_definitions={summary.canonical_template_definitions}")
    print(f"canonical_template_bindings={summary.canonical_template_bindings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
