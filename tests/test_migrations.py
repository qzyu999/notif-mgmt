"""A1: versioned schema, migration from the v1 scaffold, data preservation."""
import sqlite3

from notif_mgmt.storage import SCHEMA_VERSION, connect


def _tables(db):
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(db, table):
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def test_fresh_db_is_at_current_schema_version(tmp_path):
    db = connect(tmp_path / "fresh.db")
    assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert {"people", "identities", "interaction_signals", "followups", "sync_state"} <= _tables(db)


def test_signal_schema_separates_evidence_from_inference(tmp_path):
    db = connect(tmp_path / "fresh.db")
    cols = _columns(db, "interaction_signals")
    assert {"source_event_id", "identity_id", "person_id", "actor_candidate",
            "parser_name", "parser_version", "dedupe_key", "confidence"} <= cols
    # identities must be storable before resolution
    assert "person_id" in _columns(db, "identities")


def test_v1_database_migrates_without_losing_events(tmp_path):
    path = tmp_path / "v1.db"
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
        CREATE TABLE sync_cursors (source TEXT PRIMARY KEY, cursor TEXT NOT NULL,
          updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')));
        CREATE TABLE followups (id INTEGER PRIMARY KEY, contact_id INTEGER,
          inbound_event_id INTEGER, status TEXT NOT NULL DEFAULT 'needs_review',
          note TEXT NOT NULL, due_at TEXT,
          created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')));
        INSERT INTO inbound_events (source, external_id, sender, subject, preview,
          received_at, category, priority, state, classification_reason,
          classification_confidence)
        VALUES ('gmail', 'm1', 'a@example.invalid', 'Hi', 'x', '2026-11-02T00:00:00Z',
                'other_email', 'low', 'needs_review', 'legacy', 0.4);
        INSERT INTO sync_cursors (source, cursor) VALUES ('gmail', 'history-10');
        INSERT INTO followups (note) VALUES ('legacy followup');
    """)
    legacy.commit()
    legacy.close()

    db = connect(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 1
    # legacy cursor is carried into account-scoped sync state
    row = db.execute(
        "SELECT cursor FROM sync_state WHERE source='gmail' AND account_id='default'"
    ).fetchone()
    assert row[0] == "history-10"
    # pre-existing followups rows are preserved, not dropped
    preserved = db.execute(
        "SELECT count(*) FROM followups_v1 WHERE note='legacy followup'").fetchone()[0]
    assert preserved == 1
    # reconnecting is a no-op (migration is idempotent)
    db2 = connect(path)
    assert db2.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 1
