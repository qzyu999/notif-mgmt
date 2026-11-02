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
        "SELECT id FROM inbound_events WHERE source=? AND external_id=?",
        (event.source, event.external_id)).fetchone()
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
    dedupe_key = f"{event.source}:{event.external_id}:{parsed.parser_name}@{parsed.parser_version}"
    return insert_signal(
        db, source_event_id=row["id"], identity_id=identity_id, person_id=person_id,
        platform=parsed.platform, kind=parsed.kind, occurred_at=event.received_at,
        summary=parsed.summary, actor_candidate=parsed.actor_candidate,
        confidence=parsed.confidence, parser_name=parsed.parser_name,
        parser_version=parsed.parser_version, dedupe_key=dedupe_key)
