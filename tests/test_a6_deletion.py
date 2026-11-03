"""A6-2 deletion consistency.

Policy under test:
1. Permanent deletion withdraws a signal but preserves source evidence.
2. Only open, system-generated (rule-created) review candidates attached to
   a newly withdrawn signal are auto-dismissed, with resolved_at stamped.
3. User-confirmed obligations (reply / waiting / follow_up), user-created
   reviews, snoozed reviews, and already-resolved follow-ups are untouched.
4. Repeated deletion and event replay are idempotent and never resurrect
   a dismissed candidate.
5. The dismissal lands atomically with the Gmail cursor commit, so an
   interrupted sync either changes nothing or leaves a consistent state.
"""
import pytest
from fastapi.testclient import TestClient

from notif_mgmt import gmail as gmail_module
from notif_mgmt.api import create_app
from notif_mgmt.gmail import GmailApiError, GmailConnector, GmailSyncError
from notif_mgmt.models import InboundEvent
from notif_mgmt.pipeline import process_event, process_unprocessed_events
from notif_mgmt.storage import (
    add_identity,
    connect,
    create_person,
    get_sync_state,
    list_followups,
    list_signals,
    update_followup,
    withdraw_signals_for_source_event,
)

ACCOUNT = "me@example.invalid"


def _event(external_id, sender="Taylor <taylor@example.invalid>"):
    return InboundEvent(
        source="gmail", external_id=external_id, sender=sender,
        subject="Hello", preview="A short synthetic preview.",
        received_at="2026-11-02T18:00:00Z", account_id="default")


def _seed(db, external_id, sender="Taylor <taylor@example.invalid>"):
    signal = process_event(db, _event(external_id, sender))
    followup = next(f for f in list_followups(db) if f.signal_id == signal.id)
    return signal, followup


def _followup(db, followup_id):
    return next(f for f in list_followups(db) if f.id == followup_id)


def test_withdrawal_dismisses_open_rule_review_and_keeps_evidence(tmp_path):
    db = connect(tmp_path / "app.db")
    signal, followup = _seed(db, "m1")
    assert followup.status == "open" and followup.kind == "review"
    assert followup.created_by == "rule"

    assert withdraw_signals_for_source_event(db, "gmail", "default", "m1") == 1

    kept = list_signals(db)
    assert len(kept) == 1 and kept[0].id == signal.id
    assert kept[0].status == "withdrawn"
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 1
    dismissed = _followup(db, followup.id)
    assert dismissed.status == "dismissed"
    assert dismissed.resolved_at is not None


def test_withdrawal_preserves_confirmed_and_user_created_followups(tmp_path):
    db = connect(tmp_path / "app.db")
    cases = {}
    for name in ("review", "reply", "waiting", "follow_up", "user_review", "snoozed"):
        signal, followup = _seed(db, f"m-{name}",
                                 sender=f"{name} <{name}@example.invalid>")
        cases[name] = (signal, followup)
    update_followup(db, cases["reply"][1].id, kind="reply")
    update_followup(db, cases["waiting"][1].id, kind="waiting")
    update_followup(db, cases["follow_up"][1].id, kind="follow_up")
    with db:
        db.execute("UPDATE followups SET created_by='user' WHERE id=?",
                   (cases["user_review"][1].id,))
    update_followup(db, cases["snoozed"][1].id, status="snoozed",
                    snoozed_until="2999-01-01T00:00:00Z")

    for name, (signal, _followup_row) in cases.items():
        withdraw_signals_for_source_event(db, "gmail", "default", f"m-{name}")

    assert _followup(db, cases["review"][1].id).status == "dismissed"
    assert _followup(db, cases["reply"][1].id).status == "open"
    assert _followup(db, cases["waiting"][1].id).status == "open"
    assert _followup(db, cases["follow_up"][1].id).status == "open"
    assert _followup(db, cases["user_review"][1].id).status == "open"
    snoozed = _followup(db, cases["snoozed"][1].id)
    assert snoozed.status == "snoozed" and snoozed.resolved_at is None
    assert all(s.status == "withdrawn" for s in list_signals(db))


def test_withdrawal_preserves_resolved_followups_and_timestamps(tmp_path):
    db = connect(tmp_path / "app.db")
    _, done = _seed(db, "m-done")
    _, dismissed = _seed(db, "m-dismissed", sender="Other <other@example.invalid>")
    update_followup(db, done.id, status="done")
    update_followup(db, dismissed.id, status="dismissed")
    before_done = _followup(db, done.id)
    before_dismissed = _followup(db, dismissed.id)
    assert before_done.resolved_at is not None
    assert before_dismissed.resolved_at is not None

    withdraw_signals_for_source_event(db, "gmail", "default", "m-done")
    withdraw_signals_for_source_event(db, "gmail", "default", "m-dismissed")

    after_done = _followup(db, done.id)
    after_dismissed = _followup(db, dismissed.id)
    assert after_done.status == "done"
    assert after_done.resolved_at == before_done.resolved_at
    assert after_done.updated_at == before_done.updated_at
    assert after_dismissed.status == "dismissed"
    assert after_dismissed.resolved_at == before_dismissed.resolved_at
    assert after_dismissed.updated_at == before_dismissed.updated_at


def test_repeated_deletion_is_idempotent(tmp_path):
    db = connect(tmp_path / "app.db")
    _seed(db, "m1")
    assert withdraw_signals_for_source_event(db, "gmail", "default", "m1") == 1
    followup = list_followups(db)[0]
    assert followup.status == "dismissed" and followup.resolved_at is not None

    assert withdraw_signals_for_source_event(db, "gmail", "default", "m1") == 0
    again = list_followups(db)[0]
    assert again.status == "dismissed"
    assert again.resolved_at == followup.resolved_at
    assert again.updated_at == followup.updated_at
    assert withdraw_signals_for_source_event(db, "gmail", "default", "missing") == 0

    # A user may deliberately reopen the candidate afterwards; a replayed
    # deletion for the already-withdrawn signal must not override that.
    update_followup(db, followup.id, status="open")
    assert withdraw_signals_for_source_event(db, "gmail", "default", "m1") == 0
    reopened = list_followups(db)[0]
    assert reopened.status == "open" and reopened.resolved_at is None


def test_replay_never_recreates_dismissed_candidate(tmp_path):
    db = connect(tmp_path / "app.db")
    _signal, followup = _seed(db, "m1")
    withdraw_signals_for_source_event(db, "gmail", "default", "m1")

    assert process_event(db, _event("m1")) is None
    assert process_unprocessed_events(db, source="gmail", account_id="default") == 0
    signals = list_signals(db)
    assert len(signals) == 1 and signals[0].status == "withdrawn"
    followups = list_followups(db)
    assert len(followups) == 1 and followups[0].id == followup.id
    assert followups[0].status == "dismissed"


# --- Gmail connector level (fake transport, synthetic data only) -------------


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


def _connector(db, transport):
    return GmailConnector(db, transport, account_id=ACCOUNT,
                          sleeper=lambda seconds: None)


def _synced_pair(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport([
        _msg("m1", "Taylor <taylor@example.invalid>", "One"),
        _msg("m2", "Sam <sam@example.invalid>", "Two"),
    ])
    conn = _connector(db, transport)
    conn.sync_initial(query="newer_than:30d")
    return db, transport, conn


def test_incremental_deletion_dismisses_review_and_advances_cursor(tmp_path):
    db, transport, conn = _synced_pair(tmp_path)
    transport.history_pages = [
        ([{"messagesDeleted": [{"message": {"id": "m2"}}]}], "105"),
    ]
    result = conn.sync_incremental()
    assert result.deleted == 1
    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "105"
    signals = {s.dedupe_key: s for s in list_signals(db)}
    assert signals["gmail:me@example.invalid:m2"].status == "withdrawn"
    assert signals["gmail:me@example.invalid:m1"].status == "active"
    followups = {f.signal_id: f for f in list_followups(db)}
    assert followups[signals["gmail:me@example.invalid:m2"].id].status == "dismissed"
    assert followups[signals["gmail:me@example.invalid:m1"].id].status == "open"
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 2


def test_failed_incremental_changes_nothing_then_retry_applies_deletion(tmp_path):
    db, transport, conn = _synced_pair(tmp_path)
    changes = ([{"messagesAdded": [{"message": {"id": "m3"}}],
                 "messagesDeleted": [{"message": {"id": "m2"}}]}], "105")
    transport.messages["m3"] = _msg("m3", "New <new@example.invalid>", "Three")
    transport.history_pages = [changes]
    transport.errors["get_message"] = [GmailApiError(500)] * 10
    with pytest.raises(GmailSyncError):
        _connector(db, transport).sync_incremental()
    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "100"
    assert all(s.status == "active" for s in list_signals(db))
    assert all(f.status == "open" for f in list_followups(db))
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 2

    transport.errors.clear()
    transport.history_pages = [changes]
    result = conn.sync_incremental()
    assert (result.inserted, result.deleted) == (1, 1)
    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "105"
    withdrawn = [s for s in list_signals(db) if s.status == "withdrawn"]
    assert len(withdrawn) == 1
    followup = next(f for f in list_followups(db) if f.signal_id == withdrawn[0].id)
    assert followup.status == "dismissed"


def test_crash_after_commit_leaves_consistent_dismissed_state(tmp_path, monkeypatch):
    db, transport, conn = _synced_pair(tmp_path)
    transport.history_pages = [
        ([{"messagesDeleted": [{"message": {"id": "m2"}}]}], "105"),
    ]

    calls = {"count": 0}

    def crash(db_, *, source, account_id):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("simulated crash after commit")
        return 0

    monkeypatch.setattr(gmail_module, "process_unprocessed_events", crash)
    with pytest.raises(RuntimeError):
        conn.sync_incremental()
    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "105"
    withdrawn = [s for s in list_signals(db) if s.status == "withdrawn"]
    assert len(withdrawn) == 1
    followup = next(f for f in list_followups(db) if f.signal_id == withdrawn[0].id)
    assert followup.status == "dismissed"

    monkeypatch.undo()
    assert process_unprocessed_events(db, source="gmail", account_id=ACCOUNT) == 0
    assert len(list_followups(db)) == 2
    assert _followup(db, followup.id).status == "dismissed"


def test_api_reads_reflect_withdrawal_consistently(tmp_path):
    path = tmp_path / "app.db"
    db = connect(path)
    signal, followup = _seed(db, "m1")
    taylor = create_person(db, "Taylor")
    add_identity(db, taylor.id, platform="email", identity_kind="email",
                 value="taylor@example.invalid")
    withdraw_signals_for_source_event(db, "gmail", "default", "m1")
    db.close()

    client = TestClient(create_app(str(path)))
    today = client.get("/api/v1/today", params={"now": "2026-11-02T00:00:00Z"})
    assert today.status_code == 200
    body = today.json()
    assert all(f["id"] != followup.id
               for group in body.values() for f in group)
    open_rows = client.get("/api/v1/followups", params={"status": "open"}).json()
    assert all(f["id"] != followup.id for f in open_rows)
    dismissed = client.get("/api/v1/followups",
                           params={"status": "dismissed"}).json()
    assert [f["id"] for f in dismissed] == [followup.id]
    detail = client.get(f"/api/v1/people/{taylor.id}").json()
    assert detail["signals"][0]["id"] == signal.id
    assert detail["signals"][0]["status"] == "withdrawn"
    assert detail["followups"][0]["status"] == "dismissed"
    withdrawn = client.get("/api/v1/signals", params={"status": "withdrawn"}).json()
    assert [s["id"] for s in withdrawn] == [signal.id]
