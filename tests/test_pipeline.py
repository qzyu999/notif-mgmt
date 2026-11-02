"""A1 vertical slice: fixture Gmail notifications -> signals -> people -> review candidates.

Identity resolution is deliberately minimal: unresolved identities, exact
(email/handle) matching, and manual linking. No name-only merging.
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
    link_identity,
    list_followups,
    list_people,
    list_signals,
)

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "sample-notifications.json")
    .read_text(encoding="utf-8")
)


def load(db):
    return [process_event(db, InboundEvent(**raw)) for raw in FIXTURE]


def test_fixture_notifications_become_signals_with_review_candidates(tmp_path):
    db = connect(tmp_path / "app.db")
    results = load(db)
    assert len([r for r in results if r is not None]) == 3

    signals = list_signals(db)
    assert len(signals) == 3
    by_platform = {s.platform: s for s in signals}
    linkedin = by_platform["linkedin"]
    assert linkedin.kind == "direct_message_notification"
    assert linkedin.actor_candidate == "Alex"
    assert linkedin.parser_name and linkedin.parser_version
    # A notification alone never asserts a reply is owed.
    followups = list_followups(db)
    assert followups and all(f.kind == "review" and f.status == "open" for f in followups)


def test_replay_is_idempotent(tmp_path):
    db = connect(tmp_path / "app.db")
    load(db)
    again = load(db)
    assert all(r is None for r in again)
    assert len(list_signals(db)) == 3
    assert len(list_followups(db)) == 3


def test_actor_name_alone_creates_no_identity_and_no_person(tmp_path):
    db = connect(tmp_path / "app.db")
    load(db)
    linkedin = next(s for s in list_signals(db) if s.platform == "linkedin")
    assert linkedin.identity_id is None  # 'Alex' is a candidate, not an identity
    assert linkedin.person_id is None
    assert list_people(db) == []


def test_direct_email_creates_unresolved_email_identity(tmp_path):
    db = connect(tmp_path / "app.db")
    load(db)
    email_signal = next(s for s in list_signals(db) if s.platform == "email")
    assert email_signal.identity_id is not None
    assert email_signal.person_id is None
    row = db.execute(
        "SELECT value_normalized, match_status FROM identities WHERE id=?",
        (email_signal.identity_id,),
    ).fetchone()
    assert row["value_normalized"] == "taylor@example.invalid"
    assert row["match_status"] == "unmatched"


def test_exact_email_match_associates_signal_with_person(tmp_path):
    db = connect(tmp_path / "app.db")
    taylor = create_person(db, "Taylor")
    add_identity(db, taylor.id, platform="email", identity_kind="email",
                 value="taylor@example.invalid")
    load(db)
    email_signal = next(s for s in list_signals(db) if s.platform == "email")
    assert email_signal.person_id == taylor.id
    assert list_followups(db, person_id=taylor.id)


def test_manual_link_identity_backfills_signals_and_followups(tmp_path):
    db = connect(tmp_path / "app.db")
    load(db)
    email_signal = next(s for s in list_signals(db) if s.platform == "email")
    taylor = create_person(db, "Taylor")
    link_identity(db, email_signal.identity_id, taylor.id)
    signal = next(s for s in list_signals(db) if s.id == email_signal.id)
    assert signal.person_id == taylor.id
    assert list_followups(db, person_id=taylor.id)


def test_manual_assign_signal_person_for_name_only_actor(tmp_path):
    db = connect(tmp_path / "app.db")
    load(db)
    linkedin = next(s for s in list_signals(db) if s.platform == "linkedin")
    alex = create_person(db, "Alex")
    assign_signal_person(db, linkedin.id, alex.id)
    signal = next(s for s in list_signals(db) if s.id == linkedin.id)
    assert signal.person_id == alex.id
    people = list_people(db)
    assert [p.display_name for p in people] == ["Alex"]


def test_link_identity_rejects_unknown_ids(tmp_path):
    db = connect(tmp_path / "app.db")
    with pytest.raises(ValueError):
        link_identity(db, 999, 999)
