"""CI must exercise the exact integrated rehearsal source rather than an overlay.

These assertions guard the workflow contract. They do not grant deploy approval.
"""
from pathlib import Path


def _workflow() -> str:
    return (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )


def test_rehearsal_integrated_branch_is_required_cross_head_and_b6_scope():
    ci = _workflow()
    branch = "refs/heads/integration/rehearsal-source-20261017"
    # Exact branch in BOTH the B6 and the cross-head job conditions, as well
    # as an explicit cross-head case; unrelated branches stay unapproved.
    b6 = ci.split("  b6-postgres-integration:", 1)[1].split(
        "  cross-head-integration:", 1
    )[0]
    cross = ci.split("  cross-head-integration:", 1)[1]
    assert branch in b6
    assert branch in cross.split("    runs-on:", 1)[0]
    assert f"{branch})" in cross


def test_integrated_branch_verifies_two_approved_sources_without_runner_overlay():
    ci = _workflow()
    cross = ci.split("  cross-head-integration:", 1)[1]
    source_branch = "refs/heads/integration/rehearsal-source-20261017)"
    candidate_section = cross.split(source_branch, 1)[1].split("              ;;", 1)[0]
    assert "FRONTEND=\"23864ac0ff3cf3fb920bf70d46fdf9a06ada5dd6\"" in candidate_section
    assert "refs/remotes/origin/audit/certificate-case-source-integrity-20261011" in candidate_section
    assert 'git show-ref --verify --quiet "${REVIEWED_BACKEND_REF}"' in candidate_section
    assert 'tools.verify_rehearsal_release_sources' in candidate_section
    assert '--approved-backend-sha "${REVIEWED_BACKEND_SHA}"' in candidate_section
    assert '--approved-frontend-sha "${FRONTEND}"' in candidate_section
    assert '--target-sha "${GXP_BACKEND_CHECKOUT_SHA}"' in candidate_section
    assert "cp -a" not in candidate_section
    assert "rm -rf frontend" not in candidate_section


def test_integrated_candidate_is_reverified_after_ci_execution():
    cross = _workflow().split("  cross-head-integration:", 1)[1]
    post = cross.split(
        "      - name: Verify frontend source identity after runner-only integration", 1
    )[1]
    assert "integration/rehearsal-source-20261017" in post
    assert "tools.verify_rehearsal_release_sources" in post
    assert '--approved-backend-sha "${REVIEWED_BACKEND_SHA}"' in post
    assert 'git diff --exit-code -- frontend' in post
    assert "no deploy" not in post  # no magic skip token; actual checks required
