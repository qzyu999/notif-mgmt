"""SQLite stores source events idempotently and maintains auditable triage decisions."""
import os
import sqlite3
from pathlib import Path

from .classify import classify
from .config import excerpt_chars
from .models import FollowUp, InboundEvent, InteractionSignal, Person, PlatformIdentity

SCHEMA_VERSION = 3


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

# v2 (A1): canonical person-centric tables. Evidence stays in inbound_events;
# everything below is inferred/user-confirmed state, kept separate from it.
# The v1 `followups` table (never written by code) is renamed to followups_v1.
V2_SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL DEFAULT 'person',
  display_name TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS identities (
  id INTEGER PRIMARY KEY,
  person_id INTEGER REFERENCES people(id),
  platform TEXT NOT NULL,
  identity_kind TEXT NOT NULL,
  value_normalized TEXT NOT NULL,
  value_display TEXT NOT NULL,
  match_status TEXT NOT NULL DEFAULT 'unmatched',
  match_method TEXT,
  confidence REAL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  UNIQUE(platform, identity_kind, value_normalized)
);
CREATE TABLE IF NOT EXISTS interaction_signals (
  id INTEGER PRIMARY KEY,
  source_event_id INTEGER NOT NULL REFERENCES inbound_events(id),
  identity_id INTEGER REFERENCES identities(id),
  person_id INTEGER REFERENCES people(id),
  platform TEXT NOT NULL,
  kind TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  actor_candidate TEXT,
  confidence REAL NOT NULL,
  parser_name TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  dedupe_key TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS followups (
  id INTEGER PRIMARY KEY,
  person_id INTEGER REFERENCES people(id),
  signal_id INTEGER REFERENCES interaction_signals(id),
  kind TEXT NOT NULL DEFAULT 'review',
  status TEXT NOT NULL DEFAULT 'open',
  title TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  due_at TEXT,
  snoozed_until TEXT,
  created_by TEXT NOT NULL DEFAULT 'rule',
  confidence REAL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS sync_state (
  source TEXT NOT NULL,
  account_id TEXT NOT NULL DEFAULT 'default',
  cursor TEXT,
  last_sync_completed_at TEXT,
  last_error_code TEXT,
  last_error_message TEXT,
  last_recovery_at TEXT,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  PRIMARY KEY (source, account_id)
);
"""


def _table_columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def _migrate(db: sqlite3.Connection) -> None:
    """Versioned migrations via PRAGMA user_version. Idempotent; preserves data."""
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    if version < 1:
        db.executescript(SCHEMA)  # v1 baseline (also creates the legacy tables)
        db.execute("PRAGMA user_version = 1")
    if version < 2:
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "followups" in tables and "signal_id" not in _table_columns(db, "followups"):
            db.execute("ALTER TABLE followups RENAME TO followups_v1")
        db.executescript(V2_SCHEMA)
        db.execute(
            """INSERT OR IGNORE INTO sync_state (source, account_id, cursor, updated_at)
               SELECT source, 'default', cursor, updated_at FROM sync_cursors""")
        db.execute("PRAGMA user_version = 2")
    if version < 3:
        # v3 (A2): account-scoped source events + explicit sync-gap records.
        db.execute("PRAGMA foreign_keys = OFF")
        if "account_id" not in _table_columns(db, "inbound_events"):
            db.executescript("""
                CREATE TABLE inbound_events_v3 (
                  id INTEGER PRIMARY KEY,
                  source TEXT NOT NULL,
                  external_id TEXT NOT NULL,
                  account_id TEXT NOT NULL DEFAULT 'default',
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
                  UNIQUE(source, account_id, external_id)
                );
                INSERT INTO inbound_events_v3
                  (id, source, external_id, sender, subject, preview, received_at,
                   platform, thread_id, conversation_url, category, priority, state,
                   classification_reason, classification_confidence, inserted_at)
                SELECT id, source, external_id, sender, subject, preview, received_at,
                   platform, thread_id, conversation_url, category, priority, state,
                   classification_reason, classification_confidence, inserted_at
                FROM inbound_events;
                DROP TABLE inbound_events;
                ALTER TABLE inbound_events_v3 RENAME TO inbound_events;
            """)
        db.executescript("""
            CREATE TABLE IF NOT EXISTS sync_gaps (
              id INTEGER PRIMARY KEY,
              source TEXT NOT NULL,
              account_id TEXT NOT NULL,
              old_cursor TEXT,
              new_cursor TEXT,
              recovery_query TEXT,
              detected_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
        """)
        db.execute("PRAGMA foreign_keys = ON")
        violations = db.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"foreign_key_check failed after v3 migration: {violations}")
        db.execute("PRAGMA user_version = 3")
    db.commit()


def connect(path: str | Path, check_same_thread: bool = True) -> sqlite3.Connection:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(str(path), check_same_thread=check_same_thread)
    if os.name == "posix":
        path.chmod(0o600)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    _migrate(db)
    return db


def store_event(db: sqlite3.Connection, event: InboundEvent) -> bool:
    result = classify(event)
    with db:
        cursor = db.execute(
            """INSERT OR IGNORE INTO inbound_events
            (source, external_id, account_id, sender, subject, preview, received_at, platform,
             thread_id, conversation_url, category, priority, state,
             classification_reason, classification_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.source, event.external_id, event.account_id, event.sender, event.subject,
             event.preview[:excerpt_chars()], event.received_at, event.platform, event.thread_id,
             event.conversation_url, result.category, result.priority, result.state,
             result.reason, result.confidence),
        )
        return cursor.rowcount == 1


def commit_events_and_cursor(
    db: sqlite3.Connection, source: str, events: list[InboundEvent], cursor: str,
    account_id: str = "default",
) -> int:
    """Atomic batch: records and account cursor are committed or rolled back together."""
    inserted = 0
    with db:
        for event in events:
            if event.source != source:
                raise ValueError("Mixed event sources in one cursor commit")
            if event.account_id != account_id:
                raise ValueError("Event account does not match cursor account")
            triage = classify(event)
            row = db.execute(
                """INSERT OR IGNORE INTO inbound_events
                (source, external_id, account_id, sender, subject, preview, received_at, platform,
                 thread_id, conversation_url, category, priority, state,
                 classification_reason, classification_confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event.source, event.external_id, event.account_id, event.sender, event.subject,
                 event.preview[:excerpt_chars()], event.received_at, event.platform,
                 event.thread_id, event.conversation_url, triage.category, triage.priority,
                 triage.state, triage.reason, triage.confidence),
            )
            inserted += int(row.rowcount == 1)
        db.execute(
            """INSERT INTO sync_cursors(source, cursor) VALUES (?, ?)
               ON CONFLICT(source) DO UPDATE SET cursor=excluded.cursor,
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
            (source, cursor),
        )
        db.execute(
            """INSERT INTO sync_state(source, account_id, cursor, last_sync_completed_at)
               VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
               ON CONFLICT(source, account_id) DO UPDATE SET cursor=excluded.cursor,
               last_sync_completed_at=excluded.last_sync_completed_at,
               last_error_code=NULL, last_error_message=NULL,
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
            (source, account_id, cursor),
        )
    return inserted


# --- A2 sync-state helpers -----------------------------------------------------


def get_sync_state(db: sqlite3.Connection, source: str, account_id: str) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM sync_state WHERE source=? AND account_id=?",
        (source, account_id)).fetchone()


def record_sync_error(db: sqlite3.Connection, source: str, account_id: str,
                      code: str, message: str) -> None:
    """Persist sync error metadata (never message bodies) without moving a cursor."""
    with db:
        db.execute(
            """INSERT INTO sync_state (source, account_id, last_error_code, last_error_message)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(source, account_id) DO UPDATE SET
               last_error_code=excluded.last_error_code,
               last_error_message=excluded.last_error_message,
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
            (source, account_id, code, message[:200]))


def record_sync_gap(db: sqlite3.Connection, source: str, account_id: str,
                    old_cursor: str | None, new_cursor: str, recovery_query: str) -> None:
    """Record a potential synchronization gap from bounded cursor recovery."""
    with db:
        db.execute(
            """INSERT INTO sync_gaps (source, account_id, old_cursor, new_cursor, recovery_query)
               VALUES (?, ?, ?, ?, ?)""",
            (source, account_id, old_cursor, new_cursor, recovery_query))
        db.execute(
            """UPDATE sync_state SET last_recovery_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
               WHERE source=? AND account_id=?""",
            (source, account_id))


def withdraw_signals_for_source_event(db: sqlite3.Connection, source: str,
                                      account_id: str, external_id: str) -> int:
    """Mark signals from a deleted source item withdrawn (evidence is kept)."""
    with db:
        cur = db.execute(
            """UPDATE interaction_signals SET status='withdrawn'
               WHERE status='active' AND source_event_id IN
                 (SELECT id FROM inbound_events
                  WHERE source=? AND account_id=? AND external_id=?)""",
            (source, account_id, external_id))
        return cur.rowcount


# --- A1 repositories: people, identities, signals, follow-ups -----------------
# Identity resolution is intentionally minimal: unresolved identities, exact
# (email/handle) matching, and manual linking. No name-only merging, ever.


def create_person(db: sqlite3.Connection, display_name: str, kind: str = "person",
                  notes: str = "") -> Person:
    with db:
        cur = db.execute(
            "INSERT INTO people (kind, display_name, notes) VALUES (?, ?, ?)",
            (kind, display_name, notes))
    return Person(**dict(db.execute(
        "SELECT * FROM people WHERE id=?", (cur.lastrowid,)).fetchone()))


def list_people(db: sqlite3.Connection) -> list[Person]:
    return [Person(**dict(r)) for r in db.execute(
        "SELECT * FROM people ORDER BY display_name, id")]


def _identity_by_value(db, platform, identity_kind, value_normalized):
    return db.execute(
        "SELECT * FROM identities WHERE platform=? AND identity_kind=? AND value_normalized=?",
        (platform, identity_kind, value_normalized)).fetchone()


def add_identity(db: sqlite3.Connection, person_id: int, *, platform: str,
                 identity_kind: str, value: str) -> PlatformIdentity:
    """Manually attach an exact identity (email/handle) to a person (verified)."""
    normalized = value.strip().lstrip("@").lower()
    existing = _identity_by_value(db, platform, identity_kind, normalized)
    if existing is not None:
        if existing["person_id"] not in (None, person_id):
            raise ValueError("Identity already linked to a different person")
        return PlatformIdentity(**dict(existing))
    if db.execute("SELECT 1 FROM people WHERE id=?", (person_id,)).fetchone() is None:
        raise ValueError(f"Unknown person id {person_id}")
    with db:
        cur = db.execute(
            """INSERT INTO identities (person_id, platform, identity_kind, value_normalized,
               value_display, match_status, match_method, confidence)
               VALUES (?, ?, ?, ?, ?, 'verified', 'manual', 1.0)""",
            (person_id, platform, identity_kind, normalized, value.strip()))
    return PlatformIdentity(**dict(db.execute(
        "SELECT * FROM identities WHERE id=?", (cur.lastrowid,)).fetchone()))


def get_or_create_identity(db: sqlite3.Connection, *, platform: str, identity_kind: str,
                           value_display: str, value_normalized: str,
                           confidence: float | None = None) -> PlatformIdentity:
    """Store an observed exact identity, unresolved unless already known."""
    with db:
        db.execute(
            """INSERT OR IGNORE INTO identities
               (platform, identity_kind, value_normalized, value_display,
                match_status, match_method, confidence)
               VALUES (?, ?, ?, ?, 'unmatched', 'parser', ?)""",
            (platform, identity_kind, value_normalized, value_display, confidence))
    return PlatformIdentity(**dict(_identity_by_value(
        db, platform, identity_kind, value_normalized)))


def link_identity(db: sqlite3.Connection, identity_id: int, person_id: int) -> None:
    """Manual link: verify an identity against a person and backfill its signals."""
    identity = db.execute("SELECT * FROM identities WHERE id=?", (identity_id,)).fetchone()
    person = db.execute("SELECT * FROM people WHERE id=?", (person_id,)).fetchone()
    if identity is None or person is None:
        raise ValueError("Unknown identity or person id")
    with db:
        db.execute(
            """UPDATE identities SET person_id=?, match_status='verified',
               match_method='manual', confidence=1.0,
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id=?""",
            (person_id, identity_id))
        db.execute("UPDATE interaction_signals SET person_id=? WHERE identity_id=?",
                   (person_id, identity_id))
        db.execute(
            """UPDATE followups SET person_id=? WHERE signal_id IN
               (SELECT id FROM interaction_signals WHERE identity_id=?)""",
            (person_id, identity_id))


def assign_signal_person(db: sqlite3.Connection, signal_id: int, person_id: int) -> None:
    """Manual association for signals whose actor is only a name candidate."""
    signal = db.execute("SELECT 1 FROM interaction_signals WHERE id=?",
                        (signal_id,)).fetchone()
    person = db.execute("SELECT 1 FROM people WHERE id=?", (person_id,)).fetchone()
    if signal is None or person is None:
        raise ValueError("Unknown signal or person id")
    with db:
        db.execute("UPDATE interaction_signals SET person_id=? WHERE id=?",
                   (person_id, signal_id))
        db.execute("UPDATE followups SET person_id=? WHERE signal_id=?",
                   (person_id, signal_id))


def insert_signal(db: sqlite3.Connection, *, source_event_id: int,
                  identity_id: int | None, person_id: int | None, platform: str,
                  kind: str, occurred_at: str, summary: str,
                  actor_candidate: str | None, confidence: float, parser_name: str,
                  parser_version: str, dedupe_key: str,
                  create_followup: bool = True) -> InteractionSignal | None:
    """Insert a signal plus (optionally) its review candidate; None if duplicate."""
    with db:
        cur = db.execute(
            """INSERT OR IGNORE INTO interaction_signals
               (source_event_id, identity_id, person_id, platform, kind, occurred_at,
                summary, actor_candidate, confidence, parser_name, parser_version, dedupe_key)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (source_event_id, identity_id, person_id, platform, kind, occurred_at,
             summary, actor_candidate, confidence, parser_name, parser_version, dedupe_key))
        if cur.rowcount != 1:
            return None
        signal_id = cur.lastrowid
        if create_followup:
            actor = actor_candidate or platform
            db.execute(
                """INSERT INTO followups (person_id, signal_id, kind, status, title,
                   created_by, confidence)
                   VALUES (?, ?, 'review', 'open', ?, 'rule', ?)""",
                (person_id, signal_id, f"Review {kind.replace('_', ' ')} from {actor}",
                 confidence))
    return InteractionSignal(**dict(db.execute(
        "SELECT * FROM interaction_signals WHERE id=?", (signal_id,)).fetchone()))


def list_signals(db: sqlite3.Connection, person_id: int | None = None,
                 status: str | None = None) -> list[InteractionSignal]:
    query = "SELECT * FROM interaction_signals"
    clauses, args = [], []
    if person_id is not None:
        clauses.append("person_id=?")
        args.append(person_id)
    if status is not None:
        clauses.append("status=?")
        args.append(status)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY occurred_at, id"
    return [InteractionSignal(**dict(r)) for r in db.execute(query, tuple(args))]


def list_followups(db: sqlite3.Connection, person_id: int | None = None,
                   status: str | None = None, kind: str | None = None) -> list[FollowUp]:
    clauses, args = [], []
    if person_id is not None:
        clauses.append("person_id=?")
        args.append(person_id)
    if status is not None:
        clauses.append("status=?")
        args.append(status)
    if kind is not None:
        clauses.append("kind=?")
        args.append(kind)
    query = "SELECT * FROM followups"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at, id"
    return [FollowUp(**dict(r)) for r in db.execute(query, tuple(args))]


# --- A5a read queries ---------------------------------------------------------


def get_person(db: sqlite3.Connection, person_id: int) -> Person | None:
    row = db.execute("SELECT * FROM people WHERE id=?", (person_id,)).fetchone()
    return Person(**dict(row)) if row else None


def get_identity(db: sqlite3.Connection, identity_id: int) -> PlatformIdentity | None:
    row = db.execute("SELECT * FROM identities WHERE id=?", (identity_id,)).fetchone()
    return PlatformIdentity(**dict(row)) if row else None


_FOLLOWUP_STATUSES = {"open", "snoozed", "done", "dismissed"}
_FOLLOWUP_KINDS = {"review", "reply", "waiting", "follow_up"}
_FOLLOWUP_TRANSITIONS = {
    "open": {"snoozed", "done", "dismissed"},
    "snoozed": {"open", "done", "dismissed"},
    "done": {"open"},
    "dismissed": {"open"},
}
_UNSET = object()


def update_followup(db: sqlite3.Connection, followup_id: int, *,
                    status: str | None = None, kind: str | None = None,
                    note: str | None = None, due_at=_UNSET,
                    snoozed_until=_UNSET) -> FollowUp:
    """Apply a follow-up state transition with timestamp bookkeeping.

    done/dismissed stamp resolved_at; reopening clears it. Snoozing requires
    an effective snoozed_until; leaving snoozed clears it unless a new one is
    given. due_at/snoozed_until use a sentinel so callers can explicitly
    clear them with None. Raises ValueError on unknown id, bad values, or an
    illegal transition (resolved items must reopen before snoozing).
    """
    row = db.execute("SELECT * FROM followups WHERE id=?", (followup_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown followup id {followup_id}")
    current = FollowUp(**dict(row))
    new_status = status if status is not None else current.status
    if new_status not in _FOLLOWUP_STATUSES:
        raise ValueError(f"Invalid follow-up status {new_status}")
    if (status is not None and status != current.status
            and status not in _FOLLOWUP_TRANSITIONS[current.status]):
        raise ValueError(
            f"Invalid follow-up transition {current.status} -> {status}")
    new_kind = kind if kind is not None else current.kind
    if new_kind not in _FOLLOWUP_KINDS:
        raise ValueError(f"Invalid follow-up kind {new_kind}")

    new_snoozed = (current.snoozed_until if snoozed_until is _UNSET
                   else snoozed_until)
    if status is not None and new_status != "snoozed" and snoozed_until is _UNSET:
        new_snoozed = None if current.status == "snoozed" else new_snoozed
    if new_status == "snoozed" and not new_snoozed:
        raise ValueError("Snoozing requires snoozed_until")
    new_due = current.due_at if due_at is _UNSET else due_at

    sets = ["status=?", "kind=?", "due_at=?", "snoozed_until=?",
            "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"]
    args: list = [new_status, new_kind, new_due, new_snoozed]
    if note is not None:
        sets.append("note=?")
        args.append(note)
    if new_status in ("done", "dismissed") and current.status != new_status:
        sets.append("resolved_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")
    elif new_status == "open" and current.status in ("done", "dismissed"):
        sets.append("resolved_at=NULL")
    with db:
        db.execute(f"UPDATE followups SET {', '.join(sets)} WHERE id=?",
                   (*args, followup_id))
    return FollowUp(**dict(db.execute(
        "SELECT * FROM followups WHERE id=?", (followup_id,)).fetchone()))


def list_identities(db: sqlite3.Connection, match_status: str | None = None,
                    person_id: int | None = None) -> list[PlatformIdentity]:
    clauses, args = [], []
    if match_status is not None:
        clauses.append("match_status=?")
        args.append(match_status)
    if person_id is not None:
        clauses.append("person_id=?")
        args.append(person_id)
    query = "SELECT * FROM identities"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY platform, value_normalized, id"
    return [PlatformIdentity(**dict(r)) for r in db.execute(query, tuple(args))]


def list_people_with_stats(db: sqlite3.Connection) -> list[dict]:
    """People plus identity/platform/activity aggregates for list views."""
    people = []
    for person in list_people(db):
        identities = list_identities(db, person_id=person.id)
        signals = list_signals(db, person_id=person.id)
        platforms = sorted({i.platform for i in identities}
                           | {s.platform for s in signals})
        people.append({
            **person.model_dump(),
            "identity_count": len(identities),
            "platforms": platforms,
            "last_interaction_at": max((s.occurred_at for s in signals), default=None),
            "open_followup_count": len(list_followups(db, person_id=person.id,
                                                      status="open")),
        })
    return people


def today_followups(db: sqlite3.Connection, now: str) -> dict[str, list[FollowUp]]:
    """Group follow-ups needing attention at `now` (ISO 8601 UTC string).

    Confirmed obligations and expired snoozes come first; notification-derived
    review candidates are reported separately and never presented as replies
    owed. ISO strings compare lexicographically, matching storage format.
    """
    followups = list_followups(db)
    due = [f for f in followups
           if f.status == "open" and f.due_at is not None and f.due_at <= now]
    due_ids = {f.id for f in due}
    snoozed_ready = [f for f in followups
                     if f.status == "snoozed" and f.snoozed_until is not None
                     and f.snoozed_until <= now]
    review_candidates = [f for f in followups
                         if f.status == "open" and f.kind == "review"
                         and f.id not in due_ids]
    return {"due": due, "snoozed_ready": snoozed_ready,
            "review_candidates": review_candidates}


def list_sources(db: sqlite3.Connection) -> list[dict]:
    """Per-account sync metadata for the Sources view. Never includes secrets."""
    sources = []
    for row in db.execute("SELECT * FROM sync_state ORDER BY source, account_id"):
        gaps = db.execute(
            "SELECT count(*) FROM sync_gaps WHERE source=? AND account_id=?",
            (row["source"], row["account_id"])).fetchone()[0]
        sources.append({
            "source": row["source"],
            "account_id": row["account_id"],
            "has_cursor": row["cursor"] is not None,
            "last_sync_completed_at": row["last_sync_completed_at"],
            "last_error_code": row["last_error_code"],
            "last_error_message": row["last_error_message"],
            "last_recovery_at": row["last_recovery_at"],
            "gap_count": gaps,
        })
    return sources
