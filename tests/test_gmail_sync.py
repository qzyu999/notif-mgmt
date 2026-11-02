"""A2: Gmail sync against a fake transport — no network, deterministic.

Covers: initial bounded sync, incremental add/delete, pagination, duplicate
replay, transactional cursor advancement, expired-cursor (404) bounded
recovery with a recorded gap, 429 retry, 401 auth failure, mid-sync crash.
"""
import pytest

from notif_mgmt.gmail import (
    GmailApiError,
    GmailAuthError,
    GmailConnector,
    GmailSyncError,
)
from notif_mgmt.storage import connect, get_sync_state, list_signals

ACCOUNT = "me@example.invalid"


def msg(mid, sender, subject, snippet, ts_ms="1793400000000", thread=None, labels=None):
    return {
        "id": mid, "threadId": thread or f"t-{mid}", "internalDate": ts_ms,
        "snippet": snippet, "labelIds": labels or ["INBOX"],
        "payload": {"headers": [
            {"name": "From", "value": sender},
            {"name": "Subject", "value": subject},
        ]},
    }


class FakeTransport:
    """Gmail-shaped fake. `errors[method]` is a queue of exceptions to raise."""

    def __init__(self, messages, history_id="100", ghost_ids=()):
        self.messages = {m["id"]: m for m in messages}
        self.ghost_ids = list(ghost_ids)
        self.history_id = history_id
        self.history_pages = []   # list of (changes, history_id)
        self.errors = {}
        self.calls = []

    def _maybe_raise(self, method):
        queue = self.errors.get(method) or []
        if queue:
            raise queue.pop(0)

    def get_profile(self):
        self.calls.append("get_profile")
        self._maybe_raise("get_profile")
        return {"emailAddress": ACCOUNT, "historyId": self.history_id}

    def list_message_ids(self, query, page_token=None):
        self.calls.append(("list_message_ids", query, page_token))
        self._maybe_raise("list_message_ids")
        ids = sorted(self.messages) + self.ghost_ids
        page = int(page_token or 0)
        chunk = ids[page * 2:(page + 1) * 2]  # page size 2 to force pagination
        result = {"messages": [{"id": i} for i in chunk]}
        if (page + 1) * 2 < len(ids):
            result["nextPageToken"] = str(page + 1)
        return result

    def list_history(self, start_history_id, page_token=None):
        self.calls.append(("list_history", start_history_id, page_token))
        self._maybe_raise("list_history")
        page = int(page_token or 0)
        changes, history_id = self.history_pages[page]
        result = {"history": changes, "historyId": history_id}
        if page + 1 < len(self.history_pages):
            result["nextPageToken"] = str(page + 1)
        return result

    def get_message(self, message_id):
        self.calls.append(("get_message", message_id))
        self._maybe_raise("get_message")
        if message_id not in self.messages:
            raise GmailApiError(404, "message deleted before fetch")
        return self.messages[message_id]


def connector(db, transport, **kwargs):
    kwargs.setdefault("sleeper", lambda seconds: None)
    return GmailConnector(db, transport, account_id=ACCOUNT, **kwargs)


def three_messages():
    return [
        msg("m1", "LinkedIn <messages-noreply@example.invalid>",
            "Alex sent you a message on LinkedIn", "Alex: hello"),
        msg("m2", "Taylor <taylor@example.invalid>", "Feedback", "Thoughts on privacy"),
        msg("m3", "Reddit <notifications@example.invalid>", "Activity on Reddit", "A reply"),
    ]


def test_initial_sync_paginates_stores_signals_and_cursor(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport(three_messages())
    result = connector(db, transport).sync_initial(query="newer_than:30d")
    assert (result.fetched, result.inserted, result.duplicates) == (3, 3, 0)
    assert not result.recovered
    state = get_sync_state(db, "gmail", ACCOUNT)
    assert state["cursor"] == "100"
    assert len(list_signals(db)) == 3  # signals derived from gmail evidence


def test_incremental_sync_adds_deletes_and_advances_cursor(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport(three_messages())
    conn = connector(db, transport)
    conn.sync_initial(query="newer_than:30d")
    transport.messages["m4"] = msg("m4", "Sam <sam@example.invalid>", "Intro", "Hello")
    transport.history_pages = [
        ([{"messagesAdded": [{"message": {"id": "m4"}}],
           "messagesDeleted": [{"message": {"id": "m2"}}]}], "105"),
    ]
    result = conn.sync_incremental()
    assert (result.fetched, result.inserted, result.deleted) == (1, 1, 1)
    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "105"
    withdrawn = [s for s in list_signals(db) if s.status == "withdrawn"]
    assert len(withdrawn) == 1  # m2's signal is withdrawn, not erased


def test_incremental_replay_is_duplicate_free(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport(three_messages())
    conn = connector(db, transport)
    conn.sync_initial(query="newer_than:30d")
    transport.history_pages = [
        ([{"messagesAdded": [{"message": {"id": "m1"}}]}], "101"),
    ]
    result = conn.sync_incremental()
    assert (result.inserted, result.duplicates) == (0, 1)
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 3


def test_expired_cursor_recovers_bounded_and_records_gap(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport(three_messages())
    conn = connector(db, transport, recovery_days=7)
    conn.sync_initial(query="newer_than:30d")
    transport.errors["list_history"] = [GmailApiError(404, "historyId expired")]
    result = conn.sync_incremental()
    assert result.recovered
    gap = db.execute(
        "SELECT * FROM sync_gaps WHERE source='gmail' AND account_id=?", (ACCOUNT,)
    ).fetchone()
    assert gap is not None
    assert gap["old_cursor"] == "100"
    assert "7d" in gap["recovery_query"]
    assert get_sync_state(db, "gmail", ACCOUNT)["last_recovery_at"] is not None


def test_rate_limit_retries_then_succeeds(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport(three_messages())
    transport.errors["list_message_ids"] = [GmailApiError(429), GmailApiError(429)]
    result = connector(db, transport).sync_initial(query="newer_than:30d")
    assert result.inserted == 3


def test_rate_limit_exhaustion_leaves_cursor_untouched(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport(three_messages())
    transport.errors["get_message"] = [GmailApiError(500)] * 10
    with pytest.raises(GmailSyncError):
        connector(db, transport, max_retries=2).sync_initial(query="newer_than:30d")
    state = get_sync_state(db, "gmail", ACCOUNT)
    assert state is None or state["cursor"] is None  # error may be recorded; no cursor
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 0


def test_auth_failure_is_explicit_and_moves_nothing(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport(three_messages())
    transport.errors["get_profile"] = [GmailApiError(401)]
    with pytest.raises(GmailAuthError):
        connector(db, transport).sync_initial(query="newer_than:30d")
    assert get_sync_state(db, "gmail", ACCOUNT)["last_error_code"] == "401"


def test_crash_mid_initial_sync_commits_nothing(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport(three_messages())
    transport.errors["get_message"] = [GmailApiError(503)] * 10
    with pytest.raises(GmailSyncError):
        connector(db, transport, max_retries=1).sync_initial(query="newer_than:30d")
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 0
    state = get_sync_state(db, "gmail", ACCOUNT)
    assert state is None or state["cursor"] is None
    # retry with a healthy transport succeeds cleanly
    transport.errors.clear()
    result = connector(db, transport).sync_initial(query="newer_than:30d")
    assert result.inserted == 3


def test_incremental_without_initial_sync_fails(tmp_path):
    db = connect(tmp_path / "app.db")
    with pytest.raises(GmailSyncError):
        connector(db, FakeTransport([])).sync_incremental()


def test_message_deleted_between_list_and_fetch_is_skipped(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport(three_messages(), ghost_ids=["ghost-1"])
    result = connector(db, transport).sync_initial(query="newer_than:30d")
    assert result.inserted == 3
    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "100"


def test_incremental_added_message_already_deleted_does_not_poison_cursor(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport(three_messages())
    conn = connector(db, transport)
    conn.sync_initial(query="newer_than:30d")
    transport.history_pages = [
        ([{"messagesAdded": [{"message": {"id": "ghost-9"}}]}], "106"),
    ]
    result = conn.sync_incremental()
    assert result.inserted == 0
    assert get_sync_state(db, "gmail", ACCOUNT)["cursor"] == "106"


def test_quota_403_is_retried_instead_of_demanding_reauth(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport(three_messages())
    transport.errors["list_message_ids"] = [
        GmailApiError(403, "quota", reason="rateLimitExceeded")]
    result = connector(db, transport).sync_initial(query="newer_than:30d")
    assert result.inserted == 3


def test_permission_403_is_an_auth_error(tmp_path):
    db = connect(tmp_path / "app.db")
    transport = FakeTransport(three_messages())
    transport.errors["list_message_ids"] = [
        GmailApiError(403, "forbidden", reason="insufficientPermissions")]
    with pytest.raises(GmailAuthError):
        connector(db, transport).sync_initial(query="newer_than:30d")


def test_sent_and_draft_messages_are_not_ingested(tmp_path):
    db = connect(tmp_path / "app.db")
    messages = three_messages() + [
        msg("m8", "Me <me@example.invalid>", "Sent note", "outgoing", labels=["SENT"]),
        msg("m9", "Me <me@example.invalid>", "Draft note", "unsent", labels=["DRAFT"]),
    ]
    result = connector(db, FakeTransport(messages)).sync_initial(query="newer_than:30d")
    assert result.inserted == 3
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 3
