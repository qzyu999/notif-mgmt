"""A5e: FastAPI serves the production React build as a single local process.

API routes must keep precedence over the static mount, and the app must work
unchanged when no build exists (tests, API-only use).
"""
from fastapi.testclient import TestClient

from notif_mgmt.api import create_app


def test_static_build_served_with_api_precedence(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>notif-mgmt app</body></html>",
                                     encoding="utf-8")
    client = TestClient(create_app(tmp_path / "app.db", static_dir=dist))
    root = client.get("/")
    assert root.status_code == 200
    assert "notif-mgmt app" in root.text
    # API still wins over the static mount.
    assert client.get("/api/v1/people").json() == []


def test_no_static_dir_is_fine(tmp_path):
    client = TestClient(create_app(tmp_path / "app.db",
                                   static_dir=tmp_path / "missing"))
    assert client.get("/api/v1/people").json() == []
    assert client.get("/").status_code == 404
