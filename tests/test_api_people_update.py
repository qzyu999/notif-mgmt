"""A5d person update endpoint (notes editing) behind the localhost guard."""
import pytest
from fastapi.testclient import TestClient

from notif_mgmt.api import create_app
from notif_mgmt.storage import connect, create_person, update_person

LOCAL = {"host": "127.0.0.1"}


@pytest.fixture()
def client(tmp_path):
    path = tmp_path / "app.db"
    db = connect(path)
    create_person(db, "Taylor", notes="old")
    db.close()
    return TestClient(create_app(path))


def test_patch_person_notes(client):
    updated = client.patch("/api/v1/people/1", headers=LOCAL,
                           json={"notes": "Prefers async updates"})
    assert updated.status_code == 200
    assert updated.json()["notes"] == "Prefers async updates"
    assert updated.json()["display_name"] == "Taylor"  # untouched


def test_patch_person_unknown_and_guarded(client):
    assert client.patch("/api/v1/people/999", headers=LOCAL,
                        json={"notes": "x"}).status_code == 404
    assert client.patch("/api/v1/people/1",
                        json={"notes": "x"}).status_code == 403


def test_storage_update_person_validates(tmp_path):
    db = connect(tmp_path / "x.db")
    with pytest.raises(ValueError):
        update_person(db, 999, notes="x")
    person = create_person(db, "Sam")
    with pytest.raises(ValueError):
        update_person(db, person.id, display_name="  ")
