"""SQLite stores source events idempotently and maintains auditable triage decisions."""
import os
import sqlite3
from pathlib import Path

from .classify import classify
from .models import InboundEvent


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS inbound_events (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  sender TEXT NOT NULL,
  subject TEXT NOT NULL,
  preview TEXT NOT NULL,
  received_at TEXT NOT NULL,
  platform TEXT,
  thread_id TEXT,
  conversation_url TEXT,
  category TEXT NOT NULL,
  priority TEXT NOT NULL,
  state TEXT NOT NULL,
  classification_reason TEXT NOT NULL,
  classification_confidence REAL NOT NULL,
  inserted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  UNIQUE(source, external_id)
);
CREATE TABLE IF NOT EXISTS sync_cursors (
  source TEXT PRIMARY KEY,
  cursor TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS contacts (
  id INTEGER PRIMARY KEY,
  display_name TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS contact_identities (
  id INTEGER PRIMARY KEY,
  contact_id INTEGER NOT NULL REFERENCES contacts(id),
  platform TEXT NOT NULL,
  external_identity TEXT NOT NULL,
  verification TEXT NOT NULL DEFAULT 'manual',
  UNIQUE(platform, external_identity)
);
CREATE TABLE IF NOT EXISTS followups (
  id INTEGER PRIMARY KEY,
  contact_id INTEGER REFERENCES contacts(id),
  inbound_event_id INTEGER REFERENCES inbound_events(id),
  status TEXT NOT NULL DEFAULT 'needs_review',
  note TEXT NOT NULL,
  due_at TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(str(path))
    if os.name == "posix":
        path.chmod(0o600)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def store_event(db: sqlite3.Connection, event: InboundEvent) -> bool:
    result = classify(event)
    with db:
        cursor = db.execute(
            """INSERT OR IGNORE INTO inbound_events
            (source, external_id, sender, subject, preview, received_at, platform,
             thread_id, conversation_url, category, priority, state,
             classification_reason, classification_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.source, event.external_id, event.sender, event.subject,
             event.preview, event.received_at, event.platform, event.thread_id,
             event.conversation_url, result.category, result.priority, result.state,
             result.reason, result.confidence),
        )
        return cursor.rowcount == 1


def commit_events_and_cursor(
    db: sqlite3.Connection, source: str, events: list[InboundEvent], cursor: str
) -> int:
    """Atomic batch: records and source cursor are committed or rolled back together."""
    inserted = 0
    with db:
        for event in events:
            if event.source != source:
                raise ValueError("Mixed event sources in one cursor commit")
            triage = classify(event)
            row = db.execute(
                """INSERT OR IGNORE INTO inbound_events
                (source, external_id, sender, subject, preview, received_at, platform,
                 thread_id, conversation_url, category, priority, state,
                 classification_reason, classification_confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event.source, event.external_id, event.sender, event.subject,
                 event.preview, event.received_at, event.platform, event.thread_id,
                 event.conversation_url, triage.category, triage.priority,
                 triage.state, triage.reason, triage.confidence),
            )
            inserted += int(row.rowcount == 1)
        db.execute(
            """INSERT INTO sync_cursors(source, cursor) VALUES (?, ?)
               ON CONFLICT(source) DO UPDATE SET cursor=excluded.cursor,
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
            (source, cursor),
        )
    return inserted
