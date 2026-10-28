"""Print repository-only QĐKT audit; no approval, live data or file writer."""
import argparse
import sys

from backend.app.document.inspection_qd_kt_transformation_audit import (
    build_qdkt_transformation_audit, transformation_audit_json, transformation_audit_markdown,
    QdKtTransformationAuditBlocked,
)
from backend.app.document.inspection_qd_kt_provenance_gate import QdKtProvenanceGateBlocked


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        report = build_qdkt_transformation_audit()
    except (QdKtTransformationAuditBlocked, QdKtProvenanceGateBlocked) as exc:
        sys.stdout.write(transformation_audit_json({"audit_blockers": [str(exc)], "ready_to_render": False, "legal_equivalence_verified": False}))
        return 2
    sys.stdout.write(transformation_audit_json(report) if args.format == "json" else transformation_audit_markdown(report))
    return 2  # Evidence is not authorization or renderer readiness.


if __name__ == "__main__":
    raise SystemExit(main())
