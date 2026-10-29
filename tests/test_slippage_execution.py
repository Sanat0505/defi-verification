"""Real parser/pipeline/API boundaries with every external dependency mocked."""

import asyncio
import importlib
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from core.models import PromptRequest
from core.state import ConversationStore, VerificationCapabilityStore
from llm import intent_parser
from services import pipeline


api = importlib.import_module("api.app")
BASE = {"action": "swap", "protocol": "Uniswap V3", "amount": "10",
        "token_in": "USDC", "token_out": "WETH", "chain": "Sepolia"}
QUERY = "Swap 10 USDC for WETH on Uniswap V3 on Sepolia"
WALLET = "0x" + "1" * 40


@pytest.fixture
def isolated(monkeypatch):
    store = VerificationCapabilityStore()
    monkeypatch.setattr(pipeline, "capability_store", store)
    monkeypatch.setattr(api, "capability_store", store)
    monkeypatch.setattr(pipeline, "conversation_store", ConversationStore())
    monkeypatch.setattr(pipeline, "settings", replace(pipeline.settings, swap_slippage_bps=100))
    calls = {"graph": 0, "whitelist": [], "wallet": []}

    def graph(*_args):
        calls["graph"] += 1
        return {"decision": "APPROVED", "protocol": "Uniswap V3", "action": "swap",
                "chain_id": 11155111, "network": "Ethereum Sepolia",
                "verified_address": "0x" + "2" * 40,
                "verified_function": "exactInputSingle(tuple)", "verified_selector": "0x04e45aaf",
                "routes": [{"router_address": "0x" + "2" * 40, "pool_address": "0x" + "3" * 40,
                            "pool_fee": 3000, "token_in_address": "0x" + "4" * 40,
                            "token_out_address": "0x" + "5" * 40}]}

    def whitelist(address):
        calls["whitelist"].append(address)
        return {"success": True}

    def swap(routes, amount, slippage):
        calls["wallet"].append((routes, amount, slippage))
        return {"executed": True, "slippage_bps": slippage, "tx_hash": "mock-only"}

    monkeypatch.setattr(pipeline, "verify_intent", graph)
    monkeypatch.setattr(api, "verify_intent", graph)
    monkeypatch.setattr(api, "add_to_whitelist", whitelist)
    monkeypatch.setattr(api, "execute_swap", swap)
    return store, calls


def verify(monkeypatch, raw, query=QUERY):
    monkeypatch.setattr(intent_parser, "_call_model", lambda *args: raw)
    return asyncio.run(pipeline.process_prompt(PromptRequest(prompt=query, conversation_id="slippage-test")))


def execute(token, **extra):
    return TestClient(api.app).post("/api/execute", json={
        "verification_id": token, "wallet_address": WALLET, **extra})


@pytest.mark.parametrize("user_bps", [None, 25])
def test_effective_slippage_is_frozen_from_verification_to_execution(monkeypatch, isolated, user_bps):
    store, calls = isolated
    raw = dict(BASE)
    query = QUERY
    if user_bps is not None:
        raw["slippage"] = {"value": "0.25", "unit": "percent"}
        query += ", maximum slippage 0.25%"
    result = verify(monkeypatch, raw, query)
    expected = user_bps if user_bps is not None else 100
    assert result["execution_parameters"] == {"slippage_bps": expected,
        "slippage_source": "user" if user_bps is not None else "configured_default"}
    assert result["intent"].get("slippage_bps") == user_bps
    monkeypatch.setenv("SWAP_SLIPPAGE_BPS", "500")
    monkeypatch.setattr(pipeline, "settings", replace(pipeline.settings, swap_slippage_bps=500))
    response = execute(result["verification_id"]).json()
    assert response["decision"] == "EXECUTED"
    assert calls["wallet"][0][1:] == ("10", expected)
    assert calls["graph"] == 2
    assert execute(result["verification_id"]).json()["execution"]["reason_code"] == "VERIFICATION_REUSED"
    assert len(calls["wallet"]) == 1


@pytest.mark.parametrize("saved_bps", [None, 400])
def test_missing_or_inconsistent_saved_slippage_cannot_execute(monkeypatch, isolated, saved_bps):
    store, calls = isolated
    result = verify(monkeypatch, {**BASE, "slippage": {"value": "25", "unit": "bps"}}, QUERY + ", 25 bps slippage")
    # Simulate stale/internal malformed capability; clients cannot send this field.
    store._items[result["verification_id"]].operation.slippage_bps = saved_bps
    response = execute(result["verification_id"]).json()
    assert response["execution"]["reason_code"] == "INVALID_APPROVED_SLIPPAGE"
    assert calls["graph"] == 1
    assert calls["whitelist"] == calls["wallet"] == []


def test_client_cannot_override_slippage(monkeypatch, isolated):
    _, calls = isolated
    result = verify(monkeypatch, BASE)
    assert execute(result["verification_id"], slippage_bps=500).status_code == 422
    assert not calls["wallet"]
    assert execute(result["verification_id"]).json()["decision"] == "EXECUTED"


def test_issuing_capability_snapshots_mutable_intent(monkeypatch, isolated):
    store, _ = isolated
    result = verify(monkeypatch, BASE)
    original = store.claim(result["verification_id"])
    token = store.issue(original)
    original.intent.amount = 999
    original.slippage_bps = 500
    saved = store.claim(token)
    assert saved.intent.amount == 10
    assert saved.slippage_bps == 100


@pytest.mark.parametrize("suffix", [", finish within one minute", ", then supply 5 USDT to Aave V3"])
def test_unsupported_condition_cannot_reach_graph_or_wallet(monkeypatch, isolated, suffix):
    store, calls = isolated
    result = verify(monkeypatch, BASE, QUERY + suffix)
    assert result["decision"] == "UNSUPPORTED"
    assert not result["executable"]
    assert not store._items
    assert calls == {"graph": 0, "whitelist": [], "wallet": []}


@pytest.mark.parametrize("new_limit", [None, 25, 50])
def test_clarification_preserves_or_explicitly_blocks_limit_change(monkeypatch, isolated, new_limit):
    _, calls = isolated
    partial = {**BASE, "amount": None, "slippage": {"value": "25", "unit": "bps"}}
    first = verify(monkeypatch, partial, "Swap USDC for WETH on Uniswap V3, 25 bps slippage")
    assert first["decision"] == "NEEDS_CLARIFICATION"
    update = {"amount": "10"}
    query = "10 USDC"
    if new_limit is not None:
        update["slippage"] = {"value": str(new_limit), "unit": "bps"}
        query += f", {new_limit} bps slippage"
    result = verify(monkeypatch, update, query)
    if new_limit in (None, 25):
        assert result["decision"] == "APPROVED"
        assert result["execution_parameters"]["slippage_bps"] == 25
    else:
        assert result["error_code"] == "clarification_changes_constraints"
        assert calls["graph"] == 0


def test_invalid_config_default_blocks_before_graph(monkeypatch, isolated):
    _, calls = isolated
    monkeypatch.setattr(pipeline, "settings", replace(pipeline.settings, swap_slippage_bps=0))
    result = verify(monkeypatch, BASE)
    assert result["error_code"] == "invalid_slippage_configuration"
    assert calls["graph"] == 0
