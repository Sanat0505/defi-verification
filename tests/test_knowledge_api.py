import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable
import pytest

from api import knowledge as api
from knowledge.database import entries


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


def test_knowledge_api_does_not_issue_execution_authority(client, monkeypatch):
    monkeypatch.setattr(api, "entries", lambda *args, **kwargs: [{"item": {"action": "stake", "prototype_support": "knowledge_only"}, "sources": []}])
    response = client.get("/api/knowledge/operations?module=aave-umbrella&name=stake")
    assert response.status_code == 200
    payload = response.json()
    assert payload["wallet_eligibility"] == "not_evaluated"
    assert "verification_id" not in str(payload)
    assert "APPROVED" not in str(payload)
    assert client.post("/api/knowledge/operations", json={"action": "stake"}).status_code == 405


def test_invalid_knowledge_query_is_rejected_before_database(client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid input must not reach the database")
    monkeypatch.setattr(api, "entries", forbidden)
    assert client.get("/api/knowledge/functions?limit=1000").status_code == 422
    assert client.get("/api/knowledge/functions?module=unknown").status_code == 422
    assert client.get("/api/knowledge/functions?offset=-1").status_code == 422


def test_missing_knowledge_database_is_a_clear_503_without_secrets(client, monkeypatch):
    def unavailable():
        raise ServiceUnavailable("private provider credentials")
    monkeypatch.setattr(api, "summary", unavailable)
    response = client.get("/api/knowledge/summary")
    assert response.status_code == 503
    assert "python -m knowledge sync" in response.json()["detail"]
    assert "private provider" not in response.text


@pytest.mark.skipif(os.getenv("KNOWLEDGE_INTEGRATION") != "1", reason="Explicit opt-in to the local expanded knowledge database")
def test_live_catalog_filters_paginates_and_renders(client):
    for kind in ("Operation", "Function", "Contract", "CoverageGap"):
        rows = entries(kind, limit=2)
        assert len(rows) == 2
        next_rows = entries(kind, limit=2, offset=2)
        assert not {r["item"]["logical_key"] for r in rows} & {r["item"]["logical_key"] for r in next_rows}
    assert entries("Operation", module="uniswap-v3", name="borrow") == []
    assert any(row["item"]["action"] == "stake" for row in entries("Operation", module="aave-umbrella", name="stake"))
    page = client.get("/knowledge?module=aave-umbrella&name=stake")
    assert page.status_code == 200
    assert "slashable stake shares" in page.text
    assert "Knowledge only" in page.text
