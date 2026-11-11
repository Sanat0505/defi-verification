from pathlib import Path

from fastapi.testclient import TestClient

from source.api.app import app


def test_frontend_assets_are_served_from_the_source_folder(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    # No lifespan context: this checks file serving without connecting to Neo4j.
    client = TestClient(app)
    page = client.get("/")
    javascript = client.get("/static/app.js")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert javascript.status_code == 200
    assert javascript.text == (Path(__file__).resolve().parents[1] / "static/app.js").read_bytes().decode("utf-8")


def test_non_executable_approval_is_not_rendered_as_an_error():
    javascript = (Path(__file__).resolve().parents[1] / "static/app.js").read_text(encoding="utf-8")
    assert 'data.executable ? "Ready to execute on Sepolia testnet"' in javascript
    assert 'class="info-msg"' in javascript
    assert "Relationship verification succeeded, but blockchain execution" not in javascript


def test_slippage_display_uses_verified_execution_parameters():
    javascript = (Path(__file__).resolve().parents[1] / "static/app.js").read_text(encoding="utf-8")
    assert "data.execution_parameters" in javascript
    assert "Maximum slippage" in javascript
    assert "configured default" in javascript
    assert "your limit" in javascript
