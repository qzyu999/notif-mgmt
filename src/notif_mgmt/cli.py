"""Minimal offline demo CLI. Gmail and the Meta API are intentionally not connected yet."""
import argparse
import json
from pathlib import Path

from .models import InboundEvent
from .storage import connect, store_event


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-first notification CRM")
    parser.add_argument("command", choices=["demo", "list"])
    parser.add_argument("--db", default="./dev.db")
    args = parser.parse_args()
    db = connect(args.db)
    if args.command == "demo":
        fixture = Path(__file__).parents[2] / "fixtures" / "sample-notifications.json"
        if not fixture.exists():
            print("Fixture unavailable; run from the extracted repository root")
            return
        events = json.loads(fixture.read_text(encoding="utf-8"))
        inserted = sum(store_event(db, InboundEvent(**event)) for event in events)
        print(f"Inserted {inserted} synthetic notifications")
    else:
        for event in db.execute(
            "SELECT source, sender, subject, category, state FROM inbound_events ORDER BY id"
        ):
            print(f"{event['source']}: {event['sender']} | {event['subject']} | "
                  f"{event['category']} | {event['state']}")


if __name__ == "__main__":
    main()
