"""A1 CLI: the fixture slice is visible in the application (CLI views)."""
import sys

from notif_mgmt import cli


def run(monkeypatch, capsys, *argv):
    monkeypatch.setattr(sys, "argv", ["notif-mgmt", *argv])
    cli.main()
    return capsys.readouterr().out


def test_demo_signals_followups_and_manual_assignment(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / "cli.db")
    out = run(monkeypatch, capsys, "demo", "--db", db)
    assert "Inserted 3 new interaction signals" in out

    out = run(monkeypatch, capsys, "demo", "--db", db)  # replay: no duplicates
    assert "Inserted 0 new interaction signals" in out

    out = run(monkeypatch, capsys, "signals", "--db", db)
    assert "linkedin" in out and "Alex" in out

    out = run(monkeypatch, capsys, "followups", "--db", db)
    assert "review" in out

    run(monkeypatch, capsys, "add-person", "--db", db, "--name", "Alex")
    out = run(monkeypatch, capsys, "assign-signal", "--db", db,
              "--signal", "1", "--person", "1")
    assert "Assigned signal 1 to person 1" in out
    out = run(monkeypatch, capsys, "people", "--db", db)
    assert "Alex" in out
