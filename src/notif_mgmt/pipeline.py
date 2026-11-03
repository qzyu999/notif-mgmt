"""Fixture/manual pipeline: source event -> signal -> review candidate.

This is the earliest end-to-end vertical slice. Gmail (A2) will feed the same
process_event() entry point; nothing here talks to a network.
"""
import sqlite3

from .models import InboundEvent, InteractionSignal
from .parsing import parse_notification
from .storage import get_or_create_identity, insert_signal, store_event


def process_event(db: sqlite3.Connection, event: InboundEvent) -> InteractionSignal | None:
    """Store evidence, derive one deduplicated signal and a review candidate.

    Returns the new signal, or None when this event was already processed.
    The source event is never mutated by parsing; the signal is separate,
    versioned inferred state. A notification alone creates a *review*
    follow-up, never an asserted reply obligation.
    """
    store_event(db, event)
    row = db.execute(
        "SELECT id FROM inbound_events WHERE source=? AND account_id=? AND external_id=?",
        (event.source, event.account_id, event.external_id)).fetchone()
    parsed = parse_notification(event)
    identity_id = person_id = None
    if parsed.identity is not None:
        identity = get_or_create_identity(
            db, platform=parsed.identity.platform,
            identity_kind=parsed.identity.identity_kind,
            value_display=parsed.identity.value_display,
            value_normalized=parsed.identity.value_normalized,
            confidence=parsed.confidence)
        identity_id = identity.id
        person_id = identity.person_id  # set only on an exact/manual prior link
    # Dedupe is scoped to the source event, not the parser: a parser upgrade
    # replayed over old events must never mint duplicate signals/follow-ups.
    # Historical signals keep their original parser name/version.
    dedupe_key = f"{event.source}:{event.account_id}:{event.external_id}"
    # Only interaction-shaped kinds ask for human review; automated and
    # unclassified mail is kept as evidence without a follow-up candidate.
    create_followup = parsed.kind in {
        "direct_message_notification", "platform_activity", "direct_email"}
    return insert_signal(
        db, source_event_id=row["id"], identity_id=identity_id, person_id=person_id,
        platform=parsed.platform, kind=parsed.kind, occurred_at=event.received_at,
        summary=parsed.summary, actor_candidate=parsed.actor_candidate,
        confidence=parsed.confidence, parser_name=parsed.parser_name,
        parser_version=parsed.parser_version, dedupe_key=dedupe_key,
        create_followup=create_followup)


def process_unprocessed_events(db: sqlite3.Connection, *, source: str,
                               account_id: str) -> int:
    """Derive signals for stored events that have none yet (crash self-healing).

    Signal derivation is idempotent, so a crash between the atomic
    event+cursor commit and signal creation is repaired by the next sync.
    """
    rows = db.execute(
        """SELECT e.* FROM inbound_events e
           WHERE e.source=? AND e.account_id=? AND NOT EXISTS
             (SELECT 1 FROM interaction_signals s WHERE s.source_event_id = e.id)
           ORDER BY e.id""",
        (source, account_id)).fetchall()
    created = 0
    for row in rows:
        event = InboundEvent(
            source=row["source"], external_id=row["external_id"],
            sender=row["sender"], subject=row["subject"], preview=row["preview"],
            received_at=row["received_at"], platform=row["platform"],
            thread_id=row["thread_id"], conversation_url=row["conversation_url"],
            account_id=row["account_id"])
        created += int(process_event(db, event) is not None)
    return created
