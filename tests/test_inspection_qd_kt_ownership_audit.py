from contextlib import nullcontext
from types import SimpleNamespace
import pytest

from backend.app.document.inspection_qd_kt_ownership_audit import inspect_case_qdkt_ownership


class Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class Session:
    no_autoflush = nullcontext()

    def __init__(self, *, exists=True, plans=(), teams=(), decisions=(), documents=(), versions=0):
        self.exists = exists
        self.groups = [list(plans), list(teams)]
        if plans:
            self.groups.append(list(decisions))
        self.groups.append(list(documents))
        self.versions = versions
        self.get_calls = []

    def get(self, model, key):
        self.get_calls.append(key)
        return SimpleNamespace(id=key) if self.exists else None

    def scalars(self, query):
        return Scalars(self.groups.pop(0))

    def scalar(self, query):
        return self.versions


def row(id):
    return SimpleNamespace(id=id)


def test_multiple_decisions_and_documents_never_imply_historical_link():
    session = Session(
        plans=[row("plan")], teams=[row("team")],
        decisions=[row("original"), row("replacement")],
        documents=[row("doc-a"), row("doc-b")], versions=4,
    )
    result = inspect_case_qdkt_ownership(session, case_id="case")
    assert result.decision_ids == ("original", "replacement")
    assert result.current_case_team_id == "team"
    assert result.case_qdkt_document_version_count == 4
    assert result.decision_team_links_proven is False
    assert result.draft_snapshot_links_proven is False
    assert "DOCUMENT_VERSION_DECISION_LINK_NOT_MODELED" in result.blockers


def test_no_plan_team_or_doc_does_not_invent_a_roster():
    result = inspect_case_qdkt_ownership(Session(), case_id="case")
    assert result.decision_ids == ()
    assert result.current_case_team_id is None
    assert result.case_qdkt_document_version_count == 0
    assert result.blockers


def test_plan_with_no_decisions_is_valid_audit_input():
    result = inspect_case_qdkt_ownership(Session(plans=[row("plan")]), case_id="case")
    assert result.inspection_plan_id == "plan"
    assert result.decision_ids == ()


@pytest.mark.parametrize("case_id", ["", " case", "case ", None])
def test_invalid_case_id_is_rejected(case_id):
    with pytest.raises(ValueError, match="CASE_ID_INVALID"):
        inspect_case_qdkt_ownership(Session(), case_id=case_id)


def test_unknown_case_and_ambiguous_owners_fail_closed():
    with pytest.raises(ValueError, match="CASE_NOT_FOUND"):
        inspect_case_qdkt_ownership(Session(exists=False), case_id="case")
    with pytest.raises(ValueError, match="CASE_OWNER_NOT_UNIQUE"):
        inspect_case_qdkt_ownership(Session(plans=[row("p1"), row("p2")]), case_id="case")
    with pytest.raises(ValueError, match="CASE_OWNER_NOT_UNIQUE"):
        inspect_case_qdkt_ownership(Session(teams=[row("t1"), row("t2")]), case_id="case")
