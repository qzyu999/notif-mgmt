"""Local CLI: offline demo plus person/signal/follow-up views (A1).

Gmail and the Meta API are intentionally not connected yet (A2/A4).
"""
import argparse
import json
from pathlib import Path

from .models import InboundEvent
from .pipeline import process_event
from .storage import (
    assign_signal_person,
    connect,
    create_person,
    link_identity,
    list_followups,
    list_people,
    list_signals,
)


def _person_label(db, person_id: int | None) -> str:
    if person_id is None:
        return "unresolved"
    row = db.execute("SELECT display_name FROM people WHERE id=?", (person_id,)).fetchone()
    return row[0] if row else "unresolved"


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-first notification CRM")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("demo", "list", "people", "signals", "followups", "today"):
        sub.add_parser(name).add_argument("--db", default="./dev.db")
    add_person = sub.add_parser("add-person")
    add_person.add_argument("--db", default="./dev.db")
    add_person.add_argument("--name", required=True)
    add_person.add_argument("--notes", default="")
    link = sub.add_parser("link-identity")
    link.add_argument("--db", default="./dev.db")
    link.add_argument("--identity", type=int, required=True)
    link.add_argument("--person", type=int, required=True)
    assign = sub.add_parser("assign-signal")
    assign.add_argument("--db", default="./dev.db")
    assign.add_argument("--signal", type=int, required=True)
    assign.add_argument("--person", type=int, required=True)
    args = parser.parse_args()
    db = connect(args.db)

    if args.command == "demo":
        fixture = Path(__file__).parents[2] / "fixtures" / "sample-notifications.json"
        if not fixture.exists():
            print("Fixture unavailable; run from the extracted repository root")
            return
        events = json.loads(fixture.read_text(encoding="utf-8"))
        created = sum(process_event(db, InboundEvent(**e)) is not None for e in events)
        print(f"Inserted {created} new interaction signals from synthetic notifications")
        print(f"Open review candidates: {len(list_followups(db, status='open'))}")
    elif args.command == "list":
        for event in db.execute(
            "SELECT source, sender, subject, category, state FROM inbound_events ORDER BY id"
        ):
            print(f"{event['source']}: {event['sender']} | {event['subject']} | "
                  f"{event['category']} | {event['state']}")
    elif args.command == "people":
        people = list_people(db)
        if not people:
            print("No people yet. Import events, then link identities or assign signals.")
        for person in people:
            print(f"{person.id}: {person.display_name} ({person.kind})")
    elif args.command == "signals":
        signals = list_signals(db)
        if not signals:
            print("No interaction signals yet.")
        for s in signals:
            who = s.actor_candidate or _person_label(db, s.person_id)
            print(f"{s.id}: [{s.platform}] {s.kind} from {who} at {s.occurred_at} "
                  f"-> {_person_label(db, s.person_id)}")
    elif args.command in ("followups", "today"):
        followups = list_followups(db, status="open")
        if not followups:
            print("No open follow-ups.")
        for f in followups:
            print(f"{f.id}: [{f.kind}/{f.status}] {f.title} "
                  f"-> {_person_label(db, f.person_id)}")
    elif args.command == "add-person":
        person = create_person(db, args.name, notes=args.notes)
        print(f"Created person {person.id}: {person.display_name}")
    elif args.command == "link-identity":
        link_identity(db, args.identity, args.person)
        print(f"Linked identity {args.identity} to person {args.person}")
    elif args.command == "assign-signal":
        assign_signal_person(db, args.signal, args.person)
        print(f"Assigned signal {args.signal} to person {args.person}")


if __name__ == "__main__":
    main()
