"""Print repository-only QĐKT audit; no approval, live data or file writer."""
import argparse
import sys

from backend.app.document.inspection_qd_kt_transformation_audit import (
    build_qdkt_transformation_audit, transformation_audit_json, transformation_audit_markdown,
    QdKtTransformationAuditBlocked,
)
from backend.app.document.inspection_qd_kt_provenance_gate import QdKtProvenanceGateBlocked
from backend.app.document.inspection_qd_kt_runtime_provenance import QdKtRuntimeEvidenceBlocked


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--verify-local-artifacts", action="store_true", help="Read pinned local ZIP/add-in/templates; optional oletools==0.60.2; no VBA execution")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        report = build_qdkt_transformation_audit()
        if args.verify_local_artifacts:
            from tools.qdkt_runtime_source_verification import verify_local_runtime_sources
            from backend.app.document.inspection_qd_kt_transformation_audit import ROOT
            report["local_artifact_verification"] = verify_local_runtime_sources(ROOT)
    except (QdKtTransformationAuditBlocked, QdKtProvenanceGateBlocked, QdKtRuntimeEvidenceBlocked) as exc:
        sys.stdout.write(transformation_audit_json({"audit_blockers": [str(exc)], "ready_to_render": False, "legal_equivalence_verified": False}))
        return 2
    output = transformation_audit_json(report) if args.format == "json" else transformation_audit_markdown(report)
    if args.verify_local_artifacts and args.format == "markdown":
        output += "\nFresh local verification (not Word UAT):\n\n```json\n" + transformation_audit_json(report["local_artifact_verification"]) + "```\n"
    sys.stdout.write(output)
    return 2  # Evidence is not authorization or renderer readiness.


if __name__ == "__main__":
    raise SystemExit(main())
