"""The release-candidate CI result must not treat a skipped job as PASS.

Disposable tests only: no GitHub API, VM, database, credentials or deployment.
"""
from pathlib import Path

import pytest

from tools.check_rehearsal_ci_results import (
    RehearsalRequiredCiError,
    evaluate_rehearsal_ci_results,
)


REQUIRED = {
    "backend": "success",
    "frontend": "success",
    "hygiene": "success",
    "cross-head-integration": "success",
    "b6-postgres-integration": "success",
}


def test_all_five_required_jobs_must_report_success():
    report = evaluate_rehearsal_ci_results(REQUIRED)
    assert report["status"] == "REHEARSAL_REQUIRED_CI_PASS"
    assert report["required_jobs"] == REQUIRED


@pytest.mark.parametrize("job", tuple(REQUIRED))
@pytest.mark.parametrize("not_success", ["skipped", "failure", "cancelled", "timed_out", "neutral", ""])
def test_any_required_job_without_success_fails_closed(job: str, not_success: str):
    results = dict(REQUIRED, **{job: not_success})
    with pytest.raises(RehearsalRequiredCiError, match=job):
        evaluate_rehearsal_ci_results(results)


@pytest.mark.parametrize("job", tuple(REQUIRED))
def test_missing_required_job_status_never_passes(job: str):
    values = dict(REQUIRED)
    del values[job]
    with pytest.raises(RehearsalRequiredCiError, match=job):
        evaluate_rehearsal_ci_results(values)


def test_empty_or_unknown_job_set_is_not_an_implicit_pass():
    with pytest.raises(RehearsalRequiredCiError):
        evaluate_rehearsal_ci_results({})
    with pytest.raises(RehearsalRequiredCiError):
        evaluate_rehearsal_ci_results({"backend": "success"})


def test_workflow_has_exact_integration_push_fan_in_for_all_required_ci():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    job = workflow.split("\n  rehearsal-candidate-required-ci:\n", 1)[1]
    assert "needs: [backend, frontend, hygiene, cross-head-integration, b6-postgres-integration]" in job
    assert "always()" in job
    assert "github.event_name == 'push'" in job
    assert "github.ref == 'refs/heads/integration/rehearsal-source-20261017'" in job
    assert "tools.check_rehearsal_ci_results" in job
    for field in (
        "CI_BACKEND_RESULT",
        "CI_FRONTEND_RESULT",
        "CI_HYGIENE_RESULT",
        "CI_CROSS_HEAD_RESULT",
        "CI_B6_RESULT",
    ):
        assert field in job
    assert "needs['cross-head-integration'].result" in job
    assert "needs['b6-postgres-integration'].result" in job
    assert "persist-credentials: false" in job
