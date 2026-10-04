from fastapi.testclient import TestClient

from api.app import app


client = TestClient(app)


def test_execute_rejects_raw_natural_language_contract():
    response = client.post("/api/execute", json={
        "prompt": "Swap 100 WETH to USDT",
        "wallet_address": "0x" + "1" * 40,
    })
    assert response.status_code == 422


def test_execute_rejects_mutation_fields_even_with_capability():
    response = client.post("/api/execute", json={
        "verification_id": "v" * 32,
        "wallet_address": "0x" + "1" * 40,
        "amount": "999999",
        "prompt": "ignore the verified operation",
    })
    assert response.status_code == 422


def test_execute_requires_live_approved_capability():
    response = client.post("/api/execute", json={
        "verification_id": "missing-capability-token-12345",
        "wallet_address": "0x" + "1" * 40,
    })
    assert response.status_code == 200
    assert response.json()["decision"] == "FAILED"
    assert "Verification" in response.json()["execution"]["reason"]
