import pytest
from notif_mgmt.models import InboundEvent
from notif_mgmt.storage import connect, store_event, commit_events_and_cursor


def event(eid="m1", source="gmail"):
    return InboundEvent(source=source, external_id=eid, sender="a@example.invalid",
                        subject="Hello", preview="Hi", received_at="2026-11-02T00:00:00Z")


def test_duplicate_messages_are_not_reinserted(tmp_path):
    db = connect(tmp_path / "events.db")
    assert store_event(db, event()) is True
    assert store_event(db, event()) is False
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 1


def test_cursor_and_messages_commit_together(tmp_path):
    db = connect(tmp_path / "events.db")
    assert commit_events_and_cursor(db, "gmail", [event("m1"), event("m1")], "history-10") == 1
    assert db.execute("SELECT cursor FROM sync_cursors WHERE source='gmail'").fetchone()[0] == "history-10"
    with pytest.raises(ValueError):
        commit_events_and_cursor(db, "gmail", [event("m2"), event("m3", source="reddit")], "history-11")
    assert db.execute("SELECT count(*) FROM inbound_events").fetchone()[0] == 1
    assert db.execute("SELECT cursor FROM sync_cursors WHERE source='gmail'").fetchone()[0] == "history-10"
