from tools.phase3d_manual_evidence import _rank_cc_candidate


def test_rank_cc_candidate_prefers_matching_site_scope_and_gxp():
    row = {
        "site_legacy_id_ref": "132",
        "certificate_type": "GMP",
        "scope_code": "A",
    }
    site_uuid_by_legacy = {"132": "site-uuid-132"}
    candidate = {
        "legacy_inspection_id": 575,
        "site_id": "site-uuid-132",
        "gxp_type": "GMP",
        "scope_code": "A",
    }
    assert _rank_cc_candidate(row, candidate, site_uuid_by_legacy) == 10


def test_rank_cc_candidate_ignores_non_matching_fields():
    row = {
        "site_legacy_id_ref": "132",
        "certificate_type": "GMP",
        "scope_code": "A",
    }
    site_uuid_by_legacy = {"132": "site-uuid-132"}
    candidate = {
        "legacy_inspection_id": 999,
        "site_id": "different-site",
        "gxp_type": "GLP",
        "scope_code": "B",
    }
    assert _rank_cc_candidate(row, candidate, site_uuid_by_legacy) == 0
