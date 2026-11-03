"""A5b mutation API: people, identity linking, signal assignment, follow-ups.

State-transition rules under test:
- open -> snoozed requires snoozed_until; snoozed -> open/done/dismissed
- done/dismissed set resolved_at; reopening clears it
- done/dismissed cannot be snoozed directly; unknown ids are 404
- an identity owned by another person cannot be relinked (409)
Mutations are localhost-only: foreign Host or Origin headers get 403.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from notif_mgmt.api import create_app
from notif_mgmt.models import InboundEvent
from notif_mgmt.pipeline import process_event
from notif_mgmt.storage import connect, list_followups

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "sample-notifications.json")
    .read_text(encoding="utf-8")
)
LOCAL = {"host": "127.0.0.1"}


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


def _followup_id(client):
    return client.get("/api/v1/followups").json()[0]["id"]


def test_create_person_and_validation(client):
    created = client.post("/api/v1/people", headers=LOCAL,
                          json={"display_name": "Alex", "notes": "met at conf"})
    assert created.status_code == 201
    assert created.json()["display_name"] == "Alex"
    assert client.post("/api/v1/people", headers=LOCAL,
                       json={"display_name": ""}).status_code == 422


def test_add_identity_and_conflict(client):
    person = client.post("/api/v1/people", headers=LOCAL,
                         json={"display_name": "Sam"}).json()
    other = client.post("/api/v1/people", headers=LOCAL,
                        json={"display_name": "Other"}).json()
    body = {"platform": "email", "identity_kind": "email", "value": "sam@example.invalid"}
    attached = client.post(f"/api/v1/people/{person['id']}/identities",
                           headers=LOCAL, json=body)
    assert attached.status_code == 201
    assert attached.json()["match_status"] == "verified"
    conflict = client.post(f"/api/v1/people/{other['id']}/identities",
                           headers=LOCAL, json=body)
    assert conflict.status_code == 409
    missing = client.post("/api/v1/people/999/identities", headers=LOCAL, json=body)
    assert missing.status_code == 404


def test_link_identity_backfills_signals(client):
    person = client.post("/api/v1/people", headers=LOCAL,
                         json={"display_name": "Taylor"}).json()
    identity = client.get("/api/v1/identities",
                          params={"match_status": "unmatched"}).json()[0]
    linked = client.post(f"/api/v1/identities/{identity['id']}/link", headers=LOCAL,
                         json={"person_id": person["id"]})
    assert linked.status_code == 200
    assert linked.json()["match_status"] == "verified"
    detail = client.get(f"/api/v1/people/{person['id']}").json()
    assert len(detail["signals"]) == 1  # backfilled by the link

    rival = client.post("/api/v1/people", headers=LOCAL,
                        json={"display_name": "Rival"}).json()
    stolen = client.post(f"/api/v1/identities/{identity['id']}/link", headers=LOCAL,
                         json={"person_id": rival["id"]})
    assert stolen.status_code == 409
    assert client.post("/api/v1/identities/999/link", headers=LOCAL,
                       json={"person_id": person["id"]}).status_code == 404


def test_assign_name_only_signal(client):
    person = client.post("/api/v1/people", headers=LOCAL,
                         json={"display_name": "Alex"}).json()
    linkedin = next(s for s in client.get("/api/v1/signals").json()
                    if s["platform"] == "linkedin")
    assigned = client.post(f"/api/v1/signals/{linkedin['id']}/assign", headers=LOCAL,
                           json={"person_id": person["id"]})
    assert assigned.status_code == 200
    assert assigned.json()["person_id"] == person["id"]


def test_followup_full_lifecycle(client):
    fid = _followup_id(client)
    done = client.patch(f"/api/v1/followups/{fid}", headers=LOCAL,
                        json={"status": "done", "kind": "reply"})
    assert done.status_code == 200
    assert done.json()["status"] == "done"
    assert done.json()["kind"] == "reply"
    assert done.json()["resolved_at"] is not None

    illegal = client.patch(f"/api/v1/followups/{fid}", headers=LOCAL,
                           json={"status": "snoozed",
                                 "snoozed_until": "2026-12-01T00:00:00Z"})
    assert illegal.status_code == 422  # resolved items reopen before snoozing

    reopened = client.patch(f"/api/v1/followups/{fid}", headers=LOCAL,
                            json={"status": "open"})
    assert reopened.json()["resolved_at"] is None

    snoozed = client.patch(f"/api/v1/followups/{fid}", headers=LOCAL,
                           json={"status": "snoozed",
                                 "snoozed_until": "2026-12-01T00:00:00Z"})
    assert snoozed.status_code == 200
    assert snoozed.json()["snoozed_until"] == "2026-12-01T00:00:00Z"

    dismissed = client.patch(f"/api/v1/followups/{fid}", headers=LOCAL,
                             json={"status": "dismissed"})
    assert dismissed.json()["status"] == "dismissed"
    assert dismissed.json()["resolved_at"] is not None
    assert client.patch("/api/v1/followups/999", headers=LOCAL,
                        json={"status": "done"}).status_code == 404


def test_snooze_requires_until_and_due_date_roundtrip(client):
    fid = _followup_id(client)
    assert client.patch(f"/api/v1/followups/{fid}", headers=LOCAL,
                        json={"status": "snoozed"}).status_code == 422
    updated = client.patch(f"/api/v1/followups/{fid}", headers=LOCAL,
                           json={"due_at": "2026-11-05T00:00:00Z"})
    assert updated.json()["due_at"] == "2026-11-05T00:00:00Z"
    cleared = client.patch(f"/api/v1/followups/{fid}", headers=LOCAL,
                           json={"due_at": None})
    assert cleared.json()["due_at"] is None


def test_mutations_reject_foreign_host_and_origin(client):
    body = {"display_name": "Mallory"}
    assert client.post("/api/v1/people", json=body).status_code == 403  # testserver
    assert client.post("/api/v1/people", headers={"host": "evil.example"},
                       json=body).status_code == 403
    assert client.post("/api/v1/people",
                       headers={**LOCAL, "origin": "https://evil.example"},
                       json=body).status_code == 403
    ok = client.post("/api/v1/people",
                     headers={**LOCAL, "origin": "http://127.0.0.1:5173"}, json=body)
    assert ok.status_code == 201
    # Reads are not blocked by the mutation guard.
    assert client.get("/api/v1/people").status_code == 200


def test_storage_rejects_unknown_followup(tmp_path):
    from notif_mgmt.storage import update_followup

    db = connect(tmp_path / "x.db")
    with pytest.raises(ValueError):
        update_followup(db, 999, status="done")
    assert list_followups(db) == []
