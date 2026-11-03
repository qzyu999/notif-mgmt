"""A6-4 cross-layer crash consistency and self-healing.

Guarantees under test:
1. A failed fetch or a failed batch commit leaves no partial derived state.
2. Events and cursors commit atomically even when derivation has not run.
3. The next sync derives missing signals exactly once, including signals
   for events deleted while they were still underived.
4. Manual assignments, confirmed obligations, and withdrawn history are
   preserved across crashes, replays, connection recovery, and API reads.
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from notif_mgmt import gmail as gmail_module
from notif_mgmt.api import create_app
from notif_mgmt.gmail import GmailApiError, GmailConnector, GmailSyncError
from notif_mgmt.models import InboundEvent
from notif_mgmt.pipeline import process_event
from notif_mgmt.storage import (
    add_identity,
    assign_signal_person,
    commit_events_and_cursor,
    commit_sync_batch,
    connect,
    create_person,
    get_sync_state,
    list_followups,
    list_signals,
    update_followup,
    withdraw_signals_for_source_event,
)

ACCOUNT = "me@example.invalid"


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
    def __init__(self, messages, history_id="100"):
        self.messages = {m["id"]: m for m in messages}
        self.history_id = history_id
        self.history_pages = []
        self.errors = {}

    def _maybe_raise(self, method):
        queue = self.errors.get(method) or []
        if queue:
            raise queue.pop(0)

    def get_profile(self):
        self._maybe_raise("get_profile")
        return {"emailAddress": ACCOUNT, "historyId": self.history_id}

    def list_message_ids(self, query, page_token=None):
        self._maybe_raise("list_message_ids")
        ids = sorted(self.messages)
        page = int(page_token or 0)
        chunk = ids[page * 2:(page + 1) * 2]
        result = {"messages": [{"id": i} for i in chunk]}
        if (page + 1) * 2 < len(ids):
            result["nextPageToken"] = str(page + 1)
        return result

    def list_history(self, start_history_id, page_token=None):
        self._maybe_raise("list_history")
        page = int(page_token or 0)
        changes, history_id = self.history_pages[page]
        result = {"history": changes, "historyId": history_id}
        if page + 1 < len(self.history_pages):
            result["nextPageToken"] = str(page + 1)
        return result

    def get_message(self, message_id):
        self._maybe_raise("get_message")
        if message_id not in self.messages:
            raise GmailApiError(404, "message deleted before fetch")
        return self.messages[message_id]


def _connector(db, transport, **kwargs):
    return GmailConnector(db, transport, account_id=ACCOUNT,
                          sleeper=lambda seconds: None, **kwargs)


def _two_messages():
    return [
        _msg("m1", "Taylor <taylor@example.invalid>", "A direct question"),
        _msg("m2", "Sam <sam@example.invalid>", "Another direct question"),
    ]


def _crash_initial_sync(db, transport, monkeypatch):
    def crash(db_, *, source, account_id):
        raise RuntimeError("simulated crash after event and cursor commit")

    monkeypatch.setattr(gmail_module, "process_unprocessed_events", crash)
    with pytest.raises(RuntimeError):
        _connector(db, transport).sync_initial(query="newer_than:30d")
    monkeypatch.undo()


def test_crash_before_commit_leaves_nothing_and_retry_succeeds(tmp_path):
    path = tmp_path / "app.db"
    db = connect(path)
    transport = FakeTransport(_two_messages())
    transport.errors["get_message"] = [GmailApiError(503)] * 10
    with pytest.raises(GmailSyncError):
        _connector(db, transport, max_retries=1).sync_initial(
            query="newer_than:30d")
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 0
    assert list_signals(db) == [] and list_followups(db) == []
    state = get_sync_state(db, "gmail", ACCOUNT)
    assert state is None or state["cursor"] is None
    db.close()

    db = connect(path)
    transport.errors.clear()
    result = _connector(db, transport).sync_initial(query="newer_than:30d")
    assert result.inserted == 2
    assert len(list_signals(db)) == 2 and len(list_followups(db)) == 2
    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "100"


def test_batch_failure_rolls_back_insert_withdrawal_dismissal_and_cursor(tmp_path):
    db = connect(tmp_path / "app.db")
    signal = process_event(db, InboundEvent(
        source="gmail", external_id="m1",
        sender="Taylor <taylor@example.invalid>", subject="Hello",
        preview="Synthetic", received_at="2026-11-02T18:00:00Z"))
    followup = list_followups(db)[0]
    commit_events_and_cursor(db, "gmail", [], "100", account_id="default")
    db.executescript("""
        CREATE TRIGGER reject_bad_cursor
        BEFORE UPDATE ON sync_state
        WHEN NEW.cursor = 'bad'
        BEGIN
          SELECT RAISE(ABORT, 'simulated cursor write failure');
        END;
    """)

    with pytest.raises(sqlite3.Error):
        commit_sync_batch(
            db, "gmail",
            [InboundEvent(
                source="gmail", external_id="m2",
                sender="Sam <sam@example.invalid>", subject="New",
                preview="Synthetic", received_at="2026-11-02T19:00:00Z")],
            "bad", account_id="default", deleted_external_ids=["m1"])

    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 1
    kept = list_signals(db)
    assert kept[0].id == signal.id and kept[0].status == "active"
    kept_followup = list_followups(db)[0]
    assert kept_followup.id == followup.id and kept_followup.status == "open"
    assert get_sync_state(db, "gmail", "default")["cursor"] == "100"


def test_crash_after_initial_commit_repairs_after_reconnect_and_manual_link(
        tmp_path, monkeypatch):
    path = tmp_path / "app.db"
    db = connect(path)
    transport = FakeTransport(_two_messages())
    _crash_initial_sync(db, transport, monkeypatch)
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 2
    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "100"
    assert list_signals(db) == [] and list_followups(db) == []
    db.close()

    db = connect(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 3
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    taylor = create_person(db, "Taylor")
    add_identity(db, taylor.id, platform="email", identity_kind="email",
                 value="taylor@example.invalid")
    transport.history_pages = [([], "101")]
    result = _connector(db, transport).sync_incremental()

    assert (result.inserted, result.deleted) == (0, 0)
    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "101"
    signals = list_signals(db)
    assert len(signals) == 2 and len(list_followups(db)) == 2
    taylor_signal = next(s for s in signals if s.actor_candidate == "Taylor")
    assert taylor_signal.person_id == taylor.id
    assert list_followups(db, person_id=taylor.id)[0].signal_id == taylor_signal.id

    transport.history_pages = [([], "101")]
    _connector(db, transport).sync_incremental()
    assert len(list_signals(db)) == 2 and len(list_followups(db)) == 2


def test_deleted_underived_event_is_withdrawn_not_resurrected(tmp_path, monkeypatch):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport(_two_messages()[:1])
    _crash_initial_sync(db, transport, monkeypatch)
    assert list_signals(db) == []

    transport.history_pages = [
        ([{"messagesDeleted": [{"message": {"id": "m1"}}]}], "101"),
    ]
    result = _connector(db, transport).sync_incremental()

    assert result.deleted == 1
    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "101"
    signals = list_signals(db)
    assert len(signals) == 1 and signals[0].status == "withdrawn"
    followups = list_followups(db)
    assert len(followups) == 1 and followups[0].status == "dismissed"
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 1


def test_crash_after_incremental_commit_preserves_manual_state(tmp_path, monkeypatch):
    path = tmp_path / "app.db"
    db = connect(path)
    transport = FakeTransport(_two_messages())
    _connector(db, transport).sync_initial(query="newer_than:30d")
    signals = {s.dedupe_key: s for s in list_signals(db)}
    taylor_signal = signals[f"gmail:{ACCOUNT}:m1"]
    manual_signal = signals[f"gmail:{ACCOUNT}:m2"]
    manual_owner = create_person(db, "Manual Owner")
    assign_signal_person(db, manual_signal.id, manual_owner.id)
    manual_followup = next(
        f for f in list_followups(db) if f.signal_id == manual_signal.id)
    update_followup(db, manual_followup.id, kind="reply")
    withdraw_signals_for_source_event(db, "gmail", ACCOUNT, "m1")
    withdrawn_followup = next(
        f for f in list_followups(db) if f.signal_id == taylor_signal.id)
    assert withdrawn_followup.status == "dismissed"

    transport.messages["m3"] = _msg(
        "m3", "New Person <new@example.invalid>", "One more question")
    transport.history_pages = [
        ([{"messagesAdded": [{"message": {"id": "m3"}}]}], "105"),
    ]
    calls = {"count": 0}

    def crash_on_post_commit_derivation(db_, *, source, account_id):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("simulated crash after incremental commit")
        return 0

    monkeypatch.setattr(
        gmail_module, "process_unprocessed_events", crash_on_post_commit_derivation)
    with pytest.raises(RuntimeError):
        _connector(db, transport).sync_incremental()
    monkeypatch.undo()
    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "105"
    assert len(list_signals(db)) == 2
    db.close()

    db = connect(path)
    transport.history_pages = [([], "106")]
    _connector(db, transport).sync_incremental()
    signals = {s.dedupe_key: s for s in list_signals(db)}
    assert len(signals) == 3 and len(list_followups(db)) == 3
    assert signals[f"gmail:{ACCOUNT}:m1"].status == "withdrawn"
    assert signals[f"gmail:{ACCOUNT}:m2"].person_id == manual_owner.id
    followups = {f.signal_id: f for f in list_followups(db)}
    assert followups[taylor_signal.id].status == "dismissed"
    assert followups[manual_signal.id].kind == "reply"
    assert followups[manual_signal.id].status == "open"
    assert followups[signals[f"gmail:{ACCOUNT}:m3"].id].status == "open"

    transport.history_pages = [
        ([{"messagesAdded": [{"message": {"id": "m3"}}]}], "107"),
    ]
    replay = _connector(db, transport).sync_incremental()
    assert (replay.inserted, replay.duplicates) == (0, 1)
    assert len(list_signals(db)) == 3 and len(list_followups(db)) == 3
    assert {s.dedupe_key: s for s in list_signals(db)}[
        f"gmail:{ACCOUNT}:m1"].status == "withdrawn"


def test_api_views_are_consistent_after_connection_recovery(tmp_path, monkeypatch):
    path = tmp_path / "app.db"
    db = connect(path)
    transport = FakeTransport([
        _msg("m1", "Taylor <taylor@example.invalid>", "A direct question"),
        _msg("m2", "LinkedIn <messages-noreply@linkedin.com>",
             "Alex Chen sent you a message on LinkedIn"),
        _msg("m3", "X <notify@twitter.com>", "Your post was liked"),
    ])
    _crash_initial_sync(db, transport, monkeypatch)
    db.close()

    db = connect(path)
    taylor = create_person(db, "Taylor")
    add_identity(db, taylor.id, platform="email", identity_kind="email",
                 value="taylor@example.invalid")
    transport.history_pages = [([], "101")]
    _connector(db, transport).sync_incremental()
    db.close()

    client = TestClient(create_app(str(path)))
    signals = client.get("/api/v1/signals").json()
    assert len(signals) == 3
    assert {s["kind"] for s in signals} == {
        "direct_email", "direct_message_notification", "platform_activity"}
    followups = client.get(
        "/api/v1/followups", params={"status": "open", "kind": "review"}).json()
    assert len(followups) == 2
    today = client.get(
        "/api/v1/today", params={"now": "2026-11-02T00:00:00Z"}).json()
    assert [f["id"] for f in today["review_candidates"]] == [
        f["id"] for f in followups]
    people = client.get("/api/v1/people").json()
    assert len(people) == 1 and people[0]["id"] == taylor.id
    assert people[0]["open_followup_count"] == 1
    detail = client.get(f"/api/v1/people/{taylor.id}").json()
    assert len(detail["signals"]) == 1 and len(detail["followups"]) == 1
    assert detail["signals"][0]["person_id"] == taylor.id
    sources = client.get("/api/v1/sources").json()
    assert len(sources) == 1
    assert sources[0]["account_id"] == ACCOUNT and sources[0]["has_cursor"] is True
    assert sources[0]["gap_count"] == 0 and sources[0]["last_error_code"] is None
