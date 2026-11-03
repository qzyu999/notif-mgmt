"""A6-1 identity attribution integrity.

Precedence under test (highest first):
1. Explicit user decisions (manual signal assignment, manual identity link)
2. Exact identity match against an already-linked identity
3. Parser inference (unmatched identities, actor name candidates)

A manual assignment must never be silently overwritten by a later identity
link, attaching an existing unresolved identity must actually link it, and a
conflicting link must be rejected rather than overwriting attribution.
"""
import json
from pathlib import Path

import pytest

from notif_mgmt.models import InboundEvent
from notif_mgmt.pipeline import process_event
from notif_mgmt.storage import (
    add_identity,
    assign_signal_person,
    connect,
    create_person,
    get_identity,
    link_identity,
    list_followups,
    list_signals,
)

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "sample-notifications.json")
    .read_text(encoding="utf-8")
)


def _seed_two_taylor_emails(db):
    process_event(db, InboundEvent(**FIXTURE[2]))
    process_event(db, InboundEvent(
        source="gmail", external_id="taylor-2", sender="Taylor <taylor@example.invalid>",
        subject="Follow up", preview="One more thought on the privacy model.",
        received_at="2026-11-02T18:00:00Z"))
    return list_signals(db)


def _taylor_identity_id(db):
    return db.execute(
        "SELECT id FROM identities WHERE value_normalized='taylor@example.invalid'"
    ).fetchone()["id"]


def test_add_identity_links_existing_unresolved_identity(tmp_path):
    db = connect(tmp_path / "app.db")
    process_event(db, InboundEvent(**FIXTURE[2]))
    identity_id = _taylor_identity_id(db)
    before = get_identity(db, identity_id)
    assert before.person_id is None and before.match_status == "unmatched"
    assert before.match_method == "parser"

    taylor = create_person(db, "Taylor")
    attached = add_identity(db, taylor.id, platform="email", identity_kind="email",
                            value="taylor@example.invalid")
    assert attached.person_id == taylor.id
    assert attached.match_status == "verified"
    assert attached.match_method == "manual"
    signal = list_signals(db)[0]
    assert signal.person_id == taylor.id
    assert list_followups(db, person_id=taylor.id)


def test_link_identity_rejects_conflicting_person(tmp_path):
    db = connect(tmp_path / "app.db")
    process_event(db, InboundEvent(**FIXTURE[2]))
    identity_id = _taylor_identity_id(db)
    first = create_person(db, "First")
    second = create_person(db, "Second")
    link_identity(db, identity_id, first.id)
    with pytest.raises(ValueError):
        link_identity(db, identity_id, second.id)
    assert get_identity(db, identity_id).person_id == first.id


def test_manual_signal_assignment_survives_identity_link(tmp_path):
    db = connect(tmp_path / "app.db")
    first_signal, second_signal = _seed_two_taylor_emails(db)
    identity_id = _taylor_identity_id(db)
    manual_owner = create_person(db, "Manual Owner")
    identity_owner = create_person(db, "Identity Owner")

    assign_signal_person(db, first_signal.id, manual_owner.id)
    link_identity(db, identity_id, identity_owner.id)

    signals = {s.id: s for s in list_signals(db)}
    # The explicit manual assignment wins for that signal and its follow-up.
    assert signals[first_signal.id].person_id == manual_owner.id
    # The unassigned signal follows the identity link.
    assert signals[second_signal.id].person_id == identity_owner.id
    followups = {f.signal_id: f for f in list_followups(db)}
    assert followups[first_signal.id].person_id == manual_owner.id
    assert followups[second_signal.id].person_id == identity_owner.id


def test_identity_link_backfills_only_unassigned(tmp_path):
    db = connect(tmp_path / "app.db")
    _seed_two_taylor_emails(db)
    identity_id = _taylor_identity_id(db)
    taylor = create_person(db, "Taylor")
    link_identity(db, identity_id, taylor.id)
    assert all(s.person_id == taylor.id for s in list_signals(db))
    assert len(list_followups(db, person_id=taylor.id)) == 2
