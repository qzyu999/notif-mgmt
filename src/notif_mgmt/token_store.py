"""OAuth token storage. macOS Keychain preferred; 0600 file fallback.

Secrets are never logged and never committed. The Keychain backend shells out
to the macOS `security` CLI through an injectable runner (tests use a fake;
no real Keychain access in tests).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SERVICE = "notif-mgmt-gmail"


class FileTokenStore:
    """Fallback store: one JSON file, written with 0600 permissions."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def load(self, account: str) -> str | None:
        return self._read().get(account)

    def save(self, account: str, secret: str) -> None:
        data = self._read()
        data[account] = secret
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)
        os.chmod(self.path, 0o600)

    def delete(self, account: str) -> None:
        data = self._read()
        data.pop(account, None)
        if data:
            self.path.write_text(json.dumps(data), encoding="utf-8")
            os.chmod(self.path, 0o600)
        elif self.path.exists():
            self.path.unlink()


class KeychainTokenStore:
    """macOS Keychain via the `security` CLI. Runner is injectable for tests."""

    def __init__(self, service: str = SERVICE, runner=subprocess.run):
        self.service = service
        self.runner = runner

    def _run(self, argv):
        return self.runner(argv, capture_output=True, text=True, check=False)

    def load(self, account: str) -> str | None:
        result = self._run(["security", "find-generic-password", "-a", account,
                            "-s", self.service, "-w"])
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def save(self, account: str, secret: str) -> None:
        self._run(["security", "add-generic-password", "-a", account,
                   "-s", self.service, "-w", secret, "-U"])

    def delete(self, account: str) -> None:
        self._run(["security", "delete-generic-password", "-a", account,
                   "-s", self.service])


def default_token_store():
    """Keychain on macOS unless NOTIF_MGMT_TOKEN_STORE=file selects fallback."""
    choice = os.environ.get("NOTIF_MGMT_TOKEN_STORE", "").lower()
    if choice == "file" or sys.platform != "darwin":
        path = os.environ.get(
            "NOTIF_MGMT_TOKEN_FILE", "~/.local/share/notif-mgmt/tokens.json")
        return FileTokenStore(path)
    return KeychainTokenStore()
