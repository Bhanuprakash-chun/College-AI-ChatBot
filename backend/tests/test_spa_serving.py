"""Tests for single-server SPA static serving and routing."""

import importlib
from fastapi.testclient import TestClient

from app.main import app, _FRONTEND_DIR


def test_api_root():
    client = TestClient(app)
    response = client.get("/api")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "health" in data


def test_api_unknown_route_returns_404_json():
    client = TestClient(app)
    response = client.get("/api/nonexistent-endpoint-12345")
    assert response.status_code == 404
    assert response.headers.get("content-type", "").startswith("application/json")


def test_spa_root_and_routes_when_frontend_present():
    client = TestClient(app)
    response = client.get("/")
    if _FRONTEND_DIR is not None:
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        # SPA client-side route
        chat_resp = client.get("/chat")
        assert chat_resp.status_code == 200
        assert "text/html" in chat_resp.headers.get("content-type", "")
    else:
        assert response.status_code in (200, 307)


def test_spa_serving_with_mock_static(tmp_path, monkeypatch):
    """Verify single-server SPA serving and asset handling in isolated environment."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<!doctype html><html><body>SPA Root</body></html>", encoding="utf-8")
    (static_dir / "test.txt").write_text("Hello Static", encoding="utf-8")
    assets_dir = static_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "bundle.js").write_text("console.log('bundle');", encoding="utf-8")

    monkeypatch.setenv("FRONTEND_DIST", str(static_dir))
    import app.main as m
    importlib.reload(m)

    client = TestClient(m.app)

    # Root route serves index.html
    r_root = client.get("/")
    assert r_root.status_code == 200
    assert "SPA Root" in r_root.text

    # Client-side SPA routes fallback to index.html
    r_client = client.get("/chat/session-42")
    assert r_client.status_code == 200
    assert "SPA Root" in r_client.text

    # Static assets under /assets/ are mounted
    r_asset = client.get("/assets/bundle.js")
    assert r_asset.status_code == 200
    assert "console.log" in r_asset.text

    # Root-level files (e.g. favicon, manifest) served directly
    r_file = client.get("/test.txt")
    assert r_file.status_code == 200
    assert "Hello Static" in r_file.text

    # Unmatched /api/... routes return JSON 404, not HTML
    r_api = client.get("/api/nonexistent")
    assert r_api.status_code == 404
    assert r_api.headers.get("content-type", "").startswith("application/json")

    # Cleanup environment and reload module to default state
    monkeypatch.delenv("FRONTEND_DIST", raising=False)
    importlib.reload(m)
