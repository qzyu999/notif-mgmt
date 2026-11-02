"""A2 foundation: migration v3 (account-scoped events, sync_gaps), excerpt cap."""
import sqlite3

from notif_mgmt.models import InboundEvent
from notif_mgmt.storage import SCHEMA_VERSION, commit_events_and_cursor, connect, store_event


def event(eid="m1", account="default", preview="Hi"):
    return InboundEvent(source="gmail", external_id=eid, sender="a@example.invalid",
                        subject="Hello", preview=preview,
                        received_at="2026-11-02T00:00:00Z", account_id=account)


def test_fresh_db_is_v3_with_sync_gaps(tmp_path):
    db = connect(tmp_path / "fresh.db")
    assert SCHEMA_VERSION == 3
    assert db.execute("PRAGMA user_version").fetchone()[0] == 3
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "sync_gaps" in tables


def test_v2_database_migrates_to_v3_preserving_events(tmp_path):
    path = tmp_path / "v2.db"
    legacy = sqlite3.connect(path)
    legacy.executescript("""
        CREATE TABLE inbound_events (
          id INTEGER PRIMARY KEY, source TEXT NOT NULL, external_id TEXT NOT NULL,
          sender TEXT NOT NULL, subject TEXT NOT NULL, preview TEXT NOT NULL,
          received_at TEXT NOT NULL, platform TEXT, thread_id TEXT,
          conversation_url TEXT, category TEXT NOT NULL, priority TEXT NOT NULL,
          state TEXT NOT NULL, classification_reason TEXT NOT NULL,
          classification_confidence REAL NOT NULL,
          inserted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
          UNIQUE(source, external_id));
        INSERT INTO inbound_events (source, external_id, sender, subject, preview,
          received_at, category, priority, state, classification_reason,
          classification_confidence)
        VALUES ('gmail', 'm1', 'a@example.invalid', 'Hi', 'x', '2026-11-02T00:00:00Z',
                'other_email', 'low', 'needs_review', 'legacy', 0.4);
        PRAGMA user_version = 2;
    """)
    legacy.commit()
    legacy.close()

    db = connect(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 3
    row = db.execute("SELECT external_id, account_id FROM inbound_events").fetchone()
    assert (row["external_id"], row["account_id"]) == ("m1", "default")


def test_same_message_id_in_two_accounts_is_not_a_duplicate(tmp_path):
    db = connect(tmp_path / "app.db")
    assert store_event(db, event(account="a@example.invalid")) is True
    assert store_event(db, event(account="b@example.invalid")) is True
    assert store_event(db, event(account="a@example.invalid")) is False
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 2


def test_cursor_commit_is_account_scoped(tmp_path):
    db = connect(tmp_path / "app.db")
    commit_events_and_cursor(db, "gmail", [event(account="a@example.invalid")],
                             "h-1", account_id="a@example.invalid")
    row = db.execute(
        "SELECT cursor FROM sync_state WHERE source='gmail' AND account_id='a@example.invalid'"
    ).fetchone()
    assert row[0] == "h-1"
    assert db.execute(
        "SELECT count(*) FROM sync_state WHERE account_id='default'").fetchone()[0] == 0


def test_stored_excerpt_capped_at_200_by_default(tmp_path):
    db = connect(tmp_path / "app.db")
    store_event(db, event(preview="x" * 500))
    stored = db.execute("SELECT preview FROM inbound_events").fetchone()[0]
    assert len(stored) == 200


def test_excerpt_cap_is_configurable(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTIF_MGMT_EXCERPT_CHARS", "10")
    db = connect(tmp_path / "app.db")
    store_event(db, event(preview="x" * 500))
    stored = db.execute("SELECT preview FROM inbound_events").fetchone()[0]
    assert len(stored) == 10
