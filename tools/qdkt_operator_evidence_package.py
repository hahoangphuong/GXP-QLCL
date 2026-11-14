"""Read-only deterministic operator manifest. No Excel/COM or binary acquisition."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from backend.app.document.inspection_qd_kt_provenance_gate import parse_provenance_json_bytes, semantic_sha256
from backend.app.document.inspection_qd_kt_runtime_identity import runtime_acceptance_matrix, load_runtime_identity_evidence
from backend.app.document.inspection_qd_kt_runtime_provenance import load_runtime_source_evidence
from tools._qdkt_evidence_io import read_evidence, EvidenceBlocked, JSON_LIMIT

PACKAGE_FILES = (
    "tools/Observe-QdktExcelRuntime.ps1",
    "tools/qdkt_operator_evidence_package.py",
    "tools/qdkt_runtime_observation.py",
    "backend/app/document/inspection_qd_kt_provenance_gate.py",
    "backend/app/document/inspection_qd_kt_runtime_identity.py",
    "backend/app/document/inspection_qd_kt_runtime_provenance.py",
    "docs/QDKT_RUNTIME_OBSERVATION_PROTOCOL.md",
    "tests/fixtures/inspection_qd_kt_runtime_source_evidence.json",
    "tests/fixtures/inspection_qd_kt_runtime_identity_evidence.json",
)


def build_operator_package(root: Path) -> dict:
    """Manifest of this reviewed checkout, not a portable executable bundle.

    No clock, machine paths, user identity, private bytes or live session input.
    File hashes are exact checkout bytes (including checkout line endings).
    Authenticating this manifest needs an independently trusted commit/custodian.
    """
    root = Path(root)
    if not root.is_absolute():
        raise ValueError("QDKT_OPERATOR_PACKAGE_ROOT_INVALID")
    files = {}
    for name in PACKAGE_FILES:
        raw = read_evidence(root, name, JSON_LIMIT)
        files[name] = {"size_bytes": len(raw), "sha256": sha256(raw).hexdigest()}
    capture = load_runtime_source_evidence()
    return {
        "schema_version": "qdkt-operator-package/v1", "collector_version": "qdkt-excel-observation/v1",
        "scope": "REVIEWED_CHECKOUT_MANIFEST_NOT_SIGNED_RUNTIME_ATTESTATION",
        "manifest_coverage": "EXPLICIT_FILE_LIST_NOT_TRANSITIVE_DEPENDENCIES_USE_REVIEWED_CHECKOUT",
        "files": files, "expected_private_artifacts": capture["artifact_inputs"],
        "reviewed_addin_size_bytes": load_runtime_identity_evidence()["primary_addin_size_bytes"],
        "source_export_hashes": capture["zip_source_members"],
        "acceptance_matrix": runtime_acceptance_matrix(),
        "collector_authenticated": False, "runtime_identity_verified": False,
        "blocker": "UNVERIFIED_VERSION_BINDING", "ready_to_render": False,
    }


def verify_operator_package(root: Path, manifest: dict) -> dict:
    # Python equality equates False with 0; compare exact JSON semantics instead.
    if type(manifest) is not dict or semantic_sha256(manifest) != semantic_sha256(build_operator_package(root)):
        raise ValueError("QDKT_OPERATOR_PACKAGE_DRIFT")
    return {"package_files_match": True, "manifest_authenticated": False,
            "runtime_identity_verified": False, "ready_to_render": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Print checkout manifest only, never attach to Excel")
    mode.add_argument("--check-manifest", metavar="RELATIVE_JSON", help="Check bounded manifest inside the explicit root; not signature/custody validation")
    args = parser.parse_args(argv)
    try:
        result = (verify_operator_package(args.root, parse_provenance_json_bytes(read_evidence(args.root, args.check_manifest, JSON_LIMIT)))
                  if args.check_manifest else build_operator_package(args.root))
    except (ValueError, EvidenceBlocked) as exc:
        result = {"diagnostic": str(exc), "package_files_match": False,
                  "runtime_identity_verified": False, "ready_to_render": False}
    print(json.dumps(result, sort_keys=True, ensure_ascii=True, indent=2, allow_nan=False))
    return 2  # Neither a manifest nor integrity comparison closes readiness.


if __name__ == "__main__":
    raise SystemExit(main())
