"""Persisted QĐKT decision-specific roster readback fails closed on drift."""
from __future__ import annotations

import hashlib
import json

import pytest

from backend.app.document.inspection_qd_kt_issued_roster_persistence import (
    QdKtIssuedRosterReadBlocked, require_qdkt_issued_roster_readback_integrity,
)


def members():
    return (
        (1, "source-member-1", "Official Leader", "LEADER", "Inspector"),
        (2, "source-member-2", "Official Secretary", "SECRETARY", "Officer"),
    )


def digest(rows):
    # Independent canonical fixture: position is part of the hash, not just
    # the multiset of names. This is the persisted write-contract algorithm.
    payload = [
        {
            "position": position, "source_member_id": source_id,
            "display_name": name, "role_code": role, "job_title": title,
        }
        for position, source_id, name, role, title in rows
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def test_exact_issued_roster_round_trip_integrity():
    rows = members()
    assert require_qdkt_issued_roster_readback_integrity(
        roster_sha256=digest(rows), members=rows,
    ) is None


@pytest.mark.parametrize("mutate", [
    lambda x: x[:1] + ((2, x[1][1], "Altered", x[1][3], x[1][4]),),
    lambda x: x[:1] + ((2, x[1][1], x[1][2], "MEMBER", x[1][4]),),
    lambda x: x[:1] + ((2, x[1][1], x[1][2], x[1][3], "Changed title"),),
    lambda x: x[:1],
    lambda x: (),
    lambda x: ((2, *x[0][1:]), x[1]),
    lambda x: (x[0], (2, x[0][1], *x[1][2:])),
    lambda x: ((1, None, *x[0][2:]), x[1]),
])
def test_missing_mutated_or_reordered_roster_cannot_be_read_as_confirmed(mutate):
    good = members()
    with pytest.raises(QdKtIssuedRosterReadBlocked):
        require_qdkt_issued_roster_readback_integrity(
            roster_sha256=digest(good), members=mutate(good),
        )


@pytest.mark.parametrize("bad", [
    "0" * 64, "F" * 64, "g" * 64, "", "0" * 63, None,
])
def test_forged_or_malformed_stored_digest_is_rejected(bad):
    with pytest.raises(QdKtIssuedRosterReadBlocked):
        require_qdkt_issued_roster_readback_integrity(
            roster_sha256=bad, members=members(),
        )
