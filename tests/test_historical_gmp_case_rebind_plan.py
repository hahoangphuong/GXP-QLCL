"""Source witness + target state must match before proposing one GMP Case FK."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from pathlib import Path
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    Case, Certificate, CertificateScope, CertificateVersion, Company, Site,
)
from backend.app.domain.historical_gmp_case_rebind_plan import (
    HistoricalGmpRebindBlocked, plan_historical_gmp_case_rebind_readonly,
)
from backend.app.domain.legacy_certificate_case_source_audit import (
    audit_certificate_case_source_links,
)
from tools.audit_certificate_case_site_owners_rehearsal_readonly import (
    compare_source_to_rehearsal, EXPECTED_SNAPSHOT_SHA256,
)


def _test_context(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gmp-rebind-review.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company_original = Company(legacy_company_id=57, legal_name="Unrelated source owner")
        company_issued = Company(legacy_company_id=58, legal_name="Issued GMP site owner")
        session.add_all((company_original, company_issued))
        session.flush()
        old_site = Site(legacy_site_id=72, company_id=company_original.id, site_name="Original import Case site")
        correct_site = Site(legacy_site_id=73, company_id=company_issued.id, site_name="Certified GMP site")
        session.add_all((old_site, correct_site))
        session.flush()
        wrong = Case(legacy_inspection_id=378, site_id=old_site.id, gxp_type="GMP", state=CaseState.CERTIFIED)
        right = Case(legacy_inspection_id=380, site_id=correct_site.id, gxp_type="GMP", state=CaseState.CERTIFIED)
        session.add_all((wrong, right))
        session.flush()
        cert = Certificate(
            legacy_certificate_id=376, site_id=correct_site.id,
            case_id=wrong.id, certificate_type="GMP",
            issuance_basis="inspection_case",
        )
        session.add(cert)
        session.flush()
        version = CertificateVersion(
            certificate_id=cert.id, version_no=1,
            issue_date=date(2018, 3, 12), certificate_number="C376",
            is_latest_version=True,
        )
        session.add(version)
        session.flush()
        session.add(CertificateScope(
            certificate_version_id=version.id, scope_text="A historic bound scope",
            language_code="vi", sort_order=0,
        ))
        session.commit()

    snapshot = {
        "db.cty": [{"ID": "57"}, {"ID": "58"}],
        "db.cso": [{"ID": "72", "ID Cty": "57"}, {"ID": "73", "ID Cty": "58"}],
        "db.ktra": [
            {"ID": "378", "ID CƠ SỞ": "72", "LOẠI KT": "GMP", "Ngày K.tra": "01/03/2008"},
            {"ID": "380", "ID CƠ SỞ": "73", "LOẠI KT": "GMP",
             "ID CC GPs": "376", "Mã số CC": "C376",
             "PHẠM VI KIỂM TRA": "A historic bound scope"},
        ],
        "db.cc": [{
            "ID": "376", "ID CƠ SỞ": "73", "ID ĐỢT KTRA": "378", "LOẠI CC": "GMP",
            "Mã số CC": "C376", "Ngày cấp CC": "12/03/2018",
            "PHẠM VI CHỨNG NHẬN": "A historic bound scope",
        }],
    }
    source = audit_certificate_case_source_links(snapshot)
    with Session(engine) as session:
        witness = compare_source_to_rehearsal(
            session, source, expected_certificate_ids={376},
        )
    witness["snapshot_sha256"] = EXPECTED_SNAPSHOT_SHA256
    witness["database_transaction_read_only"] = True
    decision = json.loads(Path(
        "docs/decisions/GMP_376_CASE_380_OWNER_CONFIRMED_SOURCE_20261018.json"
    ).read_text(encoding="utf-8"))
    return engine, witness, decision


def _plan(engine, witness, decision):
    with Session(engine) as session:
        return plan_historical_gmp_case_rebind_readonly(
            session, witness=witness, decision=decision,
        )


def test_verified_owner_case_source_generates_one_private_non_executable_inverse(tmp_path):
    engine, witness, decision = _test_context(tmp_path)
    before_witness = deepcopy(witness)
    before_decision = deepcopy(decision)
    with Session(engine) as session:
        before_cases = [(c.legacy_certificate_id, c.case_id, c.site_id) for c in session.scalars(select(Certificate))]
    plan = _plan(engine, witness, decision)
    assert plan["status"] == "OWNER_CONFIRMED_SOURCE_ORIGIN_TARGET_VERIFIED_WRITE_NOT_AUTHORIZED"
    assert plan["target_database"] == "gxp_legacy_rehearsal"
    assert plan["expected_business_rows_to_change"] == 1
    assert len(plan["plan_sha256"]) == 64
    assert plan["database_writes"] == 0
    assert plan["database_write_authorized"] is False
    assert plan["document_binary_verified"] is False
    assert plan["deployment_authorized"] is False
    assert plan["backup_performed"] is False
    change = plan["proposed_change"]
    assert change["legacy_certificate_id"] == 376
    assert change["expected_before_case_legacy_id"] == 378
    assert change["proposed_after_case_legacy_id"] == 380
    assert change["expected_before_case_id"] != change["proposed_after_case_id"]
    assert change["inverse_rollback_case_id"] == change["expected_before_case_id"]
    with Session(engine) as session:
        after_cases = [(c.legacy_certificate_id, c.case_id, c.site_id) for c in session.scalars(select(Certificate))]
    assert after_cases == before_cases
    assert witness == before_witness and decision == before_decision
    engine.dispose()


@pytest.mark.parametrize(("mutation", "expected"), [
    ("wrong_certificate", "SOURCE_CERTIFICATE_NOT_UNIQUE"),
    ("wrong_old_case", "SOURCE_IDENTITIES_MISSING_OR_EQUAL"),
    ("fake_decision_approval", "OWNER_OR_SOURCE_DECISION_INCOMPLETE"),
    ("other_snapshot", "OWNER_OR_SOURCE_DECISION_INCOMPLETE"),
    ("no_read_only", "UNTRUSTED_SOURCE_OR_NON_READ_ONLY_WITNESS"),
    ("no_private_witness", "WITNESS_DETAILS_ABSENT"),
    ("wrong_reverse_case", "ORIGINATING_CASE_REVERSE_EVIDENCE_NOT_UNIQUE"),
    ("bad_scope_match", "ORIGINATING_CASE_REVERSE_EVIDENCE_NOT_UNIQUE"),
    ("wrong_version_provenance", "HISTORICAL_CERTIFICATE_VERSION_NOT_EXACT"),
    ("source_coverage_claimed_approved", "UNTRUSTED_SOURCE_OR_NON_READ_ONLY_WITNESS"),
])
def test_wrong_or_partial_source_decision_is_fail_closed(tmp_path, mutation, expected):
    engine, witness, decision = _test_context(tmp_path)
    if mutation == "wrong_certificate":
        decision["certificate_legacy_id"] = 999
    elif mutation == "wrong_old_case":
        decision["incorrect_imported_case_legacy_id"] = decision["confirmed_issuing_case_legacy_id"]
    elif mutation == "fake_decision_approval":
        decision["database_write_authorized"] = True
    elif mutation == "other_snapshot":
        decision["source_snapshot_sha256"] = "f" * 64
    elif mutation == "no_read_only":
        witness["database_transaction_read_only"] = False
    elif mutation == "no_private_witness":
        witness.pop("details_private")
    elif mutation == "wrong_reverse_case":
        witness["details_private"][0]["reverse_case_review_candidates"][0]["legacy_case_id"] = 999
    elif mutation == "bad_scope_match":
        witness["details_private"][0]["reverse_case_review_candidates"][0]["source_full_scope_lexical_correspondence"] = False
    elif mutation == "wrong_version_provenance":
        witness["details_private"][0]["certificate_versions"][0]["original_import_value_fidelity_verified"] = False
    elif mutation == "source_coverage_claimed_approved":
        witness["site_specific_scope_coverage_approved"] = True
    with pytest.raises(HistoricalGmpRebindBlocked, match=expected):
        _plan(engine, witness, decision)
    engine.dispose()


@pytest.mark.parametrize("mutation", [
    "fk_changed", "certificate_site_changed", "certificate_administrative",
    "original_case_site_changed", "target_case_site_changed",
    "target_case_gxp_changed", "target_case_occupied",
])
def test_canonical_drift_or_occupied_target_case_fails_closed(tmp_path, mutation):
    engine, witness, decision = _test_context(tmp_path)
    with Session(engine) as session:
        cert = session.scalar(select(Certificate).where(Certificate.legacy_certificate_id == 376))
        orig = session.scalar(select(Case).where(Case.legacy_inspection_id == 378))
        target = session.scalar(select(Case).where(Case.legacy_inspection_id == 380))
        if mutation == "fk_changed":
            cert.case_id = target.id
        elif mutation == "certificate_site_changed":
            cert.site_id = orig.site_id
        elif mutation == "certificate_administrative":
            cert.issuance_basis = "administrative_no_inspection"
            cert.case_id = None
        elif mutation == "original_case_site_changed":
            orig.site_id = target.site_id
        elif mutation == "target_case_site_changed":
            target.site_id = orig.site_id
        elif mutation == "target_case_gxp_changed":
            target.gxp_type = "GLP"
        elif mutation == "target_case_occupied":
            session.add(Certificate(
                site_id=target.site_id, case_id=target.id,
                certificate_type="GMP", issuance_basis="inspection_case",
            ))
        session.commit()
    with pytest.raises(HistoricalGmpRebindBlocked):
        _plan(engine, witness, decision)
    engine.dispose()
