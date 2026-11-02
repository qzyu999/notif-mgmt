"""A2 CLI: auth/sync/status wiring (no real Gmail in tests)."""
import sys

from notif_mgmt import cli


def run(monkeypatch, capsys, *argv):
    monkeypatch.setattr(sys, "argv", ["notif-mgmt", *argv])
    cli.main()
    return capsys.readouterr().out


def test_status_with_no_sync_state(tmp_path, monkeypatch, capsys):
    out = run(monkeypatch, capsys, "status", "--db", str(tmp_path / "x.db"))
    assert "No sync state" in out


def test_sync_without_credentials_gives_guidance(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NOTIF_MGMT_TOKEN_STORE", "file")
    monkeypatch.setenv("NOTIF_MGMT_TOKEN_FILE", str(tmp_path / "tokens.json"))
    out = run(monkeypatch, capsys, "sync", "--db", str(tmp_path / "x.db"),
              "--account", "me@example.invalid")
    assert "No stored credentials" in out
    assert "auth" in out


def test_auth_without_google_libraries_gives_guidance(tmp_path, monkeypatch, capsys):
    out = run(monkeypatch, capsys, "auth", "--credentials", str(tmp_path / "creds.json"))
    assert "pip install" in out and "[gmail]" in out
