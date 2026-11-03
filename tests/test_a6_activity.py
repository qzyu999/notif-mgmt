"""A6-3 routine platform-activity noise reduction.

Policy under test:
1. Routine platform activity stays stored as interaction evidence.
2. Only direct message notifications and direct email create review
   candidates, because only those reasonably indicate interpersonal
   outreach from the notification alone.
3. Existing user-created and user-confirmed follow-ups are never removed
   by the tighter gate, and replay or parser upgrades cannot duplicate
   signals or recreate candidates.
"""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from notif_mgmt import pipeline
from notif_mgmt.api import create_app
from notif_mgmt.gmail import GmailApiError, GmailConnector
from notif_mgmt.models import InboundEvent
from notif_mgmt.pipeline import process_event, process_unprocessed_events
from notif_mgmt.storage import (
    connect,
    insert_signal,
    list_followups,
    list_signals,
    store_event,
    update_followup,
)

CORPUS = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "parser-corpus.json")
    .read_text(encoding="utf-8")
)
ACCOUNT = "me@example.invalid"
OUTREACH_KINDS = {"direct_message_notification", "direct_email"}
ROUTINE_IDS = {
    "li-invitation", "li-search-appearance", "li-promo", "x-like", "x-mention",
    "x-password", "reddit-reply", "reddit-trending", "reddit-anon-reply",
    "ig-follower", "ig-security", "xhs-comment", "xhs-promo",
}


def _case(case_id):
    return next(case for case in CORPUS if case["id"] == case_id)


def test_routine_activity_is_preserved_without_review_candidates(tmp_path):
    db = connect(tmp_path / "app.db")
    for case_id in sorted(ROUTINE_IDS):
        signal = process_event(db, InboundEvent(**_case(case_id)["event"]))
        assert signal is not None
        assert signal.kind == "platform_activity"

    signals = list_signals(db)
    assert len(signals) == len(ROUTINE_IDS)
    assert {s.kind for s in signals} == {"platform_activity"}
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == len(ROUTINE_IDS)
    assert list_followups(db) == []


def test_corpus_outreach_kinds_are_the_only_candidate_sources(tmp_path):
    db = connect(tmp_path / "app.db")
    expected_signal_ids = {}
    for case in CORPUS:
        signal = process_event(db, InboundEvent(**case["event"]))
        assert signal is not None
        if case["expected"]["kind"] in OUTREACH_KINDS:
            expected_signal_ids[signal.id] = case["id"]

    assert len(list_signals(db)) == len(CORPUS)
    followups = list_followups(db)
    assert {f.signal_id for f in followups} == set(expected_signal_ids)
    assert len(followups) == len(expected_signal_ids)
    assert all(f.kind == "review" and f.status == "open" for f in followups)


def test_routine_replay_and_parser_upgrade_create_no_candidates(tmp_path, monkeypatch):
    db = connect(tmp_path / "app.db")
    event = InboundEvent(**_case("x-like")["event"])
    signal = process_event(db, event)
    assert signal is not None and signal.kind == "platform_activity"
    original = pipeline.parse_notification

    def bumped(parsed_event):
        return original(parsed_event).model_copy(update={"parser_version": "99"})

    monkeypatch.setattr(pipeline, "parse_notification", bumped)
    assert process_event(db, event) is None
    assert process_unprocessed_events(db, source="gmail", account_id="default") == 0
    signals = list_signals(db)
    assert len(signals) == 1 and signals[0].parser_version == "1"
    assert list_followups(db) == []


def test_existing_user_followups_on_routine_signals_survive_replay(tmp_path):
    db = connect(tmp_path / "app.db")
    events = [
        InboundEvent(**_case("x-like")["event"]),
        InboundEvent(**_case("reddit-trending")["event"]),
    ]
    legacy_followups = []
    for index, event in enumerate(events):
        store_event(db, event)
        event_id = db.execute(
            "SELECT id FROM inbound_events WHERE source=? AND account_id=? AND external_id=?",
            (event.source, event.account_id, event.external_id)).fetchone()["id"]
        signal = insert_signal(
            db, source_event_id=event_id, identity_id=None, person_id=None,
            platform="x" if index == 0 else "reddit", kind="platform_activity",
            occurred_at=event.received_at, summary=event.preview,
            actor_candidate=None, confidence=0.7, parser_name="legacy",
            parser_version="0",
            dedupe_key=f"gmail:default:{event.external_id}",
            create_followup=True)
        legacy_followups.append(next(
            f for f in list_followups(db) if f.signal_id == signal.id))
    update_followup(db, legacy_followups[0].id, kind="reply")
    with db:
        db.execute("UPDATE followups SET created_by='user' WHERE id=?",
                   (legacy_followups[1].id,))

    for event in events:
        assert process_event(db, event) is None

    followups = {f.id: f for f in list_followups(db)}
    assert followups[legacy_followups[0].id].kind == "reply"
    assert followups[legacy_followups[0].id].status == "open"
    assert followups[legacy_followups[1].id].created_by == "user"
    assert followups[legacy_followups[1].id].status == "open"
    assert len(list_signals(db)) == 2


def _msg(mid, sender, subject):
    return {
        "id": mid, "threadId": f"t-{mid}", "internalDate": "1793400000000",
        "snippet": "synthetic", "labelIds": ["INBOX"],
        "payload": {"headers": [
            {"name": "From", "value": sender},
            {"name": "Subject", "value": subject},
        ]},
    }


class FakeTransport:
    def __init__(self, messages):
        self.messages = {m["id"]: m for m in messages}

    def get_profile(self):
        return {"emailAddress": ACCOUNT, "historyId": "100"}

    def list_message_ids(self, query, page_token=None):
        ids = sorted(self.messages)
        page = int(page_token or 0)
        chunk = ids[page * 2:(page + 1) * 2]
        result = {"messages": [{"id": i} for i in chunk]}
        if (page + 1) * 2 < len(ids):
            result["nextPageToken"] = str(page + 1)
        return result

    def list_history(self, start_history_id, page_token=None):
        raise GmailApiError(404, "not used by initial sync tests")

    def get_message(self, message_id):
        return self.messages[message_id]


def test_fake_gmail_sync_keeps_activity_evidence_without_candidates(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport([
        _msg("m-dm", "LinkedIn <messages-noreply@linkedin.com>",
             "Alex Chen sent you a message on LinkedIn"),
        _msg("m-like", "X <notify@twitter.com>", "Your post was liked"),
        _msg("m-promo", "Xiaohongshu <promotions@xiaohongshu.com>",
             "Trending posts for you this week"),
        _msg("m-email", "Taylor <taylor@example.invalid>", "A direct question"),
    ])
    connector = GmailConnector(
        db, transport, account_id=ACCOUNT, sleeper=lambda seconds: None)
    result = connector.sync_initial(query="newer_than:30d")

    assert (result.fetched, result.inserted, result.duplicates) == (4, 4, 0)
    signals = list_signals(db)
    assert len(signals) == 4
    assert {s.kind for s in signals} == {
        "direct_message_notification", "platform_activity", "direct_email"}
    candidate_signal_ids = {f.signal_id for f in list_followups(db)}
    assert candidate_signal_ids == {
        s.id for s in signals if s.kind in OUTREACH_KINDS}
    assert len(candidate_signal_ids) == 2


def test_api_today_and_followups_exclude_routine_activity(tmp_path):
    path = tmp_path / "app.db"
    db = connect(path)
    for case_id in ("li-dm-named", "x-like", "reddit-trending", "email-direct"):
        process_event(db, InboundEvent(**_case(case_id)["event"]))
    db.close()

    client = TestClient(create_app(str(path)))
    signals = client.get("/api/v1/signals").json()
    assert len(signals) == 4
    assert {s["kind"] for s in signals} == {
        "direct_message_notification", "platform_activity", "direct_email"}
    followups = client.get(
        "/api/v1/followups", params={"status": "open", "kind": "review"}).json()
    assert len(followups) == 2
    assert {f["signal_id"] for f in followups} == {
        s["id"] for s in signals if s["kind"] in OUTREACH_KINDS}
    today = client.get(
        "/api/v1/today", params={"now": "2999-01-01T00:00:00Z"}).json()
    assert [f["id"] for f in today["review_candidates"]] == [
        f["id"] for f in followups]
    assert today["due"] == [] and today["snoozed_ready"] == []
