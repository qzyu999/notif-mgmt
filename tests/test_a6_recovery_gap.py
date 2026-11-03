"""A6-5 expired-cursor recovery atomicity.

A recovered batch, its cursor advancement, its sync-gap row, and the
recovery timestamp must commit together. A failure while recording the
gap cannot leave a recovered cursor behind without the gap marker, and
recovery replay cannot duplicate historical derived state.
"""
import sqlite3

import pytest

from notif_mgmt.gmail import GmailApiError, GmailConnector
from notif_mgmt.storage import (
    connect,
    get_sync_state,
    list_followups,
    list_signals,
    update_followup,
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
        raise AssertionError("history pages are not used by these recovery tests")

    def get_message(self, message_id):
        self._maybe_raise("get_message")
        return self.messages[message_id]


def _connector(db, transport):
    return GmailConnector(db, transport, account_id=ACCOUNT,
                          sleeper=lambda seconds: None)


def _gaps(db):
    return db.execute(
        "SELECT * FROM sync_gaps WHERE source='gmail' AND account_id=? ORDER BY id",
        (ACCOUNT,)).fetchall()


def _expired_recovery(db, transport):
    transport.errors["list_history"] = [GmailApiError(404, "historyId expired")]
    return _connector(db, transport).sync_incremental()


def test_gap_write_failure_rolls_back_recovered_batch_and_cursor(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport([
        _msg("m1", "Taylor <taylor@example.invalid>", "Original question"),
    ])
    _connector(db, transport).sync_initial(query="newer_than:30d")
    confirmed = list_followups(db)[0]
    update_followup(db, confirmed.id, kind="reply")
    transport.messages["m2"] = _msg(
        "m2", "Sam <sam@example.invalid>", "Recovered question")
    transport.history_id = "200"
    db.execute("""
        CREATE TRIGGER reject_sync_gap
        BEFORE INSERT ON sync_gaps
        BEGIN
          SELECT RAISE(ABORT, 'simulated gap write failure');
        END;
    """)

    with pytest.raises(sqlite3.Error):
        _expired_recovery(db, transport)

    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "100"
    assert get_sync_state(db, "gmail", ACCOUNT)["last_recovery_at"] is None
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 1
    assert [s.dedupe_key for s in list_signals(db)] == [f"gmail:{ACCOUNT}:m1"]
    followups = list_followups(db)
    assert len(followups) == 1
    assert followups[0].id == confirmed.id and followups[0].kind == "reply"
    assert followups[0].status == "open"
    assert _gaps(db) == []

    db.execute("DROP TRIGGER reject_sync_gap")
    result = _expired_recovery(db, transport)
    assert result.recovered and result.inserted == 1
    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "200"
    assert get_sync_state(db, "gmail", ACCOUNT)["last_recovery_at"] is not None
    gaps = _gaps(db)
    assert len(gaps) == 1
    assert gaps[0]["old_cursor"] == "100" and gaps[0]["new_cursor"] == "200"
    assert len(list_signals(db)) == 2 and len(list_followups(db)) == 2
    preserved = next(f for f in list_followups(db) if f.id == confirmed.id)
    assert preserved.kind == "reply" and preserved.status == "open"


def test_repeated_expired_recovery_replays_events_without_duplicate_state(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport([
        _msg("m1", "Taylor <taylor@example.invalid>", "Original question"),
    ])
    _connector(db, transport).sync_initial(query="newer_than:30d")
    transport.history_id = "200"

    first = _expired_recovery(db, transport)
    second = _expired_recovery(db, transport)

    assert first.recovered and second.recovered
    assert (second.inserted, second.duplicates) == (0, 1)
    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "200"
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 1
    assert len(list_signals(db)) == 1 and len(list_followups(db)) == 1
    gaps = _gaps(db)
    assert [(gap["old_cursor"], gap["new_cursor"]) for gap in gaps] == [
        ("100", "200"), ("200", "200")]
