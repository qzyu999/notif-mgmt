"""A2: OAuth token storage — macOS Keychain preferred, 0600 file fallback."""
import os
import stat
from types import SimpleNamespace

from notif_mgmt.token_store import FileTokenStore, KeychainTokenStore


def test_file_token_store_roundtrip_with_0600(tmp_path):
    path = tmp_path / "token.json"
    store = FileTokenStore(path)
    assert store.load("me@example.invalid") is None
    store.save("me@example.invalid", '{"refresh_token": "synthetic"}')
    assert store.load("me@example.invalid") == '{"refresh_token": "synthetic"}'
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    store.delete("me@example.invalid")
    assert store.load("me@example.invalid") is None


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.saved = {}

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[1] == "add-generic-password":
            account = argv[argv.index("-a") + 1]
            self.saved[account] = argv[argv.index("-w") + 1]
            return SimpleNamespace(returncode=0, stdout="")
        if argv[1] == "find-generic-password":
            account = argv[argv.index("-a") + 1]
            if account in self.saved:
                return SimpleNamespace(returncode=0, stdout=self.saved[account] + "\n")
            return SimpleNamespace(returncode=44, stdout="")
        if argv[1] == "delete-generic-password":
            account = argv[argv.index("-a") + 1]
            self.saved.pop(account, None)
            return SimpleNamespace(returncode=0, stdout="")
        raise AssertionError(argv)


def test_keychain_token_store_uses_security_cli():
    runner = FakeRunner()
    store = KeychainTokenStore(runner=runner)
    assert store.load("me@example.invalid") is None  # not found -> None, no raise
    store.save("me@example.invalid", "synthetic-secret")
    assert store.load("me@example.invalid") == "synthetic-secret"
    store.delete("me@example.invalid")
    assert store.load("me@example.invalid") is None
    assert all(call[0] == "security" for call in runner.calls)
