"""A5a read-only API contracts over an isolated synthetic database.

The API reuses the Pydantic domain models and storage layer; it must never
create people from actor candidates, never expose tokens, and must keep
review candidates distinct from confirmed obligations.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from notif_mgmt.api import create_app
from notif_mgmt.models import InboundEvent
from notif_mgmt.pipeline import process_event
from notif_mgmt.storage import (
    connect,
    create_person,
    link_identity,
    list_followups,
    record_sync_error,
    record_sync_gap,
)

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "sample-notifications.json")
    .read_text(encoding="utf-8")
)


@pytest.fixture()
def seeded(tmp_path):
    path = tmp_path / "app.db"
    db = connect(path)
    for raw in FIXTURE:
        process_event(db, InboundEvent(**raw))
    db.close()
    return path


@pytest.fixture()
def client(seeded):
    return TestClient(create_app(seeded))


def test_people_empty(tmp_path):
    empty = TestClient(create_app(tmp_path / "empty.db"))
    assert empty.get("/api/v1/people").json() == []


def test_people_summaries_and_detail(client, seeded):
    db = connect(seeded)
    taylor = create_person(db, "Taylor")
    row = db.execute(
        "SELECT id FROM identities WHERE value_normalized='taylor@example.invalid'"
    ).fetchone()
    link_identity(db, row["id"], taylor.id)
    db.close()

    people = client.get("/api/v1/people").json()
    assert len(people) == 1
    summary = people[0]
    assert summary["display_name"] == "Taylor"
    assert summary["identity_count"] == 1
    assert summary["platforms"] == ["email"]
    assert summary["last_interaction_at"] is not None
    assert summary["open_followup_count"] == 1

    detail = client.get(f"/api/v1/people/{taylor.id}").json()
    assert detail["person"]["id"] == taylor.id
    assert [i["value_normalized"] for i in detail["identities"]] == [
        "taylor@example.invalid"]
    assert len(detail["signals"]) == 1
    assert detail["signals"][0]["platform"] == "email"
    assert len(detail["followups"]) == 1


def test_person_detail_unknown_id_is_404(client):
    assert client.get("/api/v1/people/999").status_code == 404


def test_actor_candidate_never_becomes_a_person(client):
    # The LinkedIn fixture actor "Alex" is a name candidate only.
    assert client.get("/api/v1/people").json() == []
    signals = client.get("/api/v1/signals").json()
    linkedin = next(s for s in signals if s["platform"] == "linkedin")
    assert linkedin["actor_candidate"] == "Alex"
    assert linkedin["person_id"] is None
    assert linkedin["parser_name"] == "linkedin-notifications"
    assert linkedin["parser_version"] == "1"


def test_identities_filter_by_match_status(client):
    unmatched = client.get("/api/v1/identities",
                           params={"match_status": "unmatched"}).json()
    assert [i["value_normalized"] for i in unmatched] == ["taylor@example.invalid"]
    assert client.get("/api/v1/identities",
                      params={"match_status": "verified"}).json() == []


def test_followups_filters(client):
    open_reviews = client.get(
        "/api/v1/followups", params={"status": "open", "kind": "review"}).json()
    # The LinkedIn DM and the direct email are review candidates; the
    # routine Reddit activity fixture is evidence only.
    assert len(open_reviews) == 2
    assert all(f["status"] == "open" and f["kind"] == "review" for f in open_reviews)
    assert client.get("/api/v1/followups", params={"status": "done"}).json() == []


def test_today_groups_due_snoozed_and_candidates(client, seeded):
    db = connect(seeded)
    # The fixtures yield two candidates under the A6-3 gate; add one more
    # direct outreach so all three Today groups can be exercised at once.
    process_event(db, InboundEvent(
        source="gmail", external_id="today-extra",
        sender="Sam <sam@example.invalid>", subject="One more question",
        preview="Could you take a look?", received_at="2026-11-02T19:00:00Z"))
    followups = list_followups(db)
    due, snoozed, candidate = followups[0], followups[1], followups[2]
    with db:
        db.execute("UPDATE followups SET due_at='2026-11-01T00:00:00Z' WHERE id=?",
                   (due.id,))
        db.execute(
            "UPDATE followups SET status='snoozed', snoozed_until='2026-11-01T00:00:00Z'"
            " WHERE id=?", (snoozed.id,))
    db.close()

    today = client.get("/api/v1/today", params={"now": "2026-11-02T00:00:00Z"}).json()
    assert [f["id"] for f in today["due"]] == [due.id]
    assert [f["id"] for f in today["snoozed_ready"]] == [snoozed.id]
    assert [f["id"] for f in today["review_candidates"]] == [candidate.id]


def test_sources_reports_state_and_gaps_without_secrets(client, seeded):
    db = connect(seeded)
    record_sync_error(db, "gmail", "test@example.invalid", 401, "auth failed")
    record_sync_gap(db, "gmail", "test@example.invalid", "100", "200",
                    "newer_than:30d")
    db.close()

    sources = client.get("/api/v1/sources").json()
    assert len(sources) == 1
    source = sources[0]
    assert source["source"] == "gmail"
    assert source["account_id"] == "test@example.invalid"
    assert source["has_cursor"] is False
    assert source["last_error_code"] == "401"
    assert source["gap_count"] == 1
    assert source["last_recovery_at"] is not None
    # Sync metadata only; never credentials or message content.
    assert "token" not in json.dumps(source).lower()
