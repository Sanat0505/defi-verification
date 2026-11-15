"""Mocked API/issuance boundaries; on-chain evidence lives in wallet/test/."""
import asyncio
import copy
import time

import pytest

from source.api import app as api
from source.core.models import Decision, ExecuteRequest
from source.core.state import VerificationCapabilityStore
from source.tests.test_aave_execution import aave_operation, graph_result
from source.wallet import erc4337


@pytest.mark.parametrize("action", ["supply", "withdraw", "borrow", "repay"])
def test_retained_aave_reverified_before_authorization(monkeypatch, action):
    operation = aave_operation(action)
    store = VerificationCapabilityStore()
    token = store.issue(operation)
    events = []
    monkeypatch.setattr(api, "capability_store", store)
    monkeypatch.setattr(api, "verify_intent", lambda *args: events.append("graph") or graph_result(operation))
    monkeypatch.setattr(api, "add_to_whitelist", lambda *_: {"success": True})
    def execute(saved, verification_id):
        assert events == ["graph"]
        assert saved.intent.amount == operation.intent.amount
        assert saved.verified_asset == operation.verified_asset
        assert saved.interest_rate_mode == operation.interest_rate_mode
        assert verification_id == token
        events.append("authorize")
        return {"executed": True}
    monkeypatch.setattr(api, "execute_approved", execute)
    request = ExecuteRequest(verification_id=token, wallet_address="0x" + "4" * 40)
    assert asyncio.run(api.execute(request))["decision"] == "EXECUTED"
    assert asyncio.run(api.execute(request))["execution"]["reason_code"] == "VERIFICATION_REUSED"
    assert events == ["graph", "authorize"]


@pytest.mark.parametrize("change", [
    {"decision": "REJECTED"}, {"decision": "INSUFFICIENT_EVIDENCE"},
    {"chain_id": 1}, {"verified_asset_decimals": 18},
    {"verified_address": "0x" + "8" * 40}, {"verified_selector": "0xdeadbeef"},
    {"verified_function": "withdraw(address,uint256,address)"},
])
def test_changed_or_unresolved_graph_never_authorizes(monkeypatch, change):
    operation = aave_operation("supply")
    store = VerificationCapabilityStore()
    token = store.issue(operation)
    monkeypatch.setattr(api, "capability_store", store)
    monkeypatch.setattr(api, "verify_intent", lambda *args: {**graph_result(operation), **change})
    def forbidden(*args):
        raise AssertionError("Unauthorized operation reached wallet")
    monkeypatch.setattr(api, "execute_approved", forbidden)
    monkeypatch.setattr(api, "add_to_whitelist", forbidden)
    result = asyncio.run(api.execute(ExecuteRequest(verification_id=token, wallet_address="0x" + "4" * 40)))
    assert result["execution"]["reason_code"] == "APPROVAL_MISMATCH"


def test_prepare_authorize_send_freezes_plan_and_separates_roles(monkeypatch):
    operation = aave_operation("repay")
    operation.approval_expires_at = time.time() + 60
    operation.smart_account = "0x" + "3" * 40
    monkeypatch.setenv("RESTRICTED_ACCOUNT_ADDRESS", operation.smart_account)
    captured = []
    frozen = {"callData": "frozen-test-bytes"}
    permit = {"callData": "frozen-test-bytes", "authoritySignature": "test-signature"}
    def call(command, args):
        captured.append((command, copy.deepcopy(args)))
        if command == "prepare_aave":
            assert args["amount"] == "10"
            assert args["asset_address"] == operation.verified_asset
            return {"success": True, "authorization_plan": frozen}
        if command == "authorize":
            assert args["approved"]["decision"] == "APPROVED"
            assert args["expiresAt"] == operation.approval_expires_at
            assert args["plan"] == frozen
            return {"success": True, "permit": permit}
        assert command == "send_authorized" and args == permit
        return {"executed": True}
    monkeypatch.setattr(erc4337, "_call_js", call)
    assert erc4337.execute_approved(operation, "retained-verification-id-12345")["executed"]
    assert [c[0] for c in captured] == ["prepare_aave", "authorize", "send_authorized"]


@pytest.mark.parametrize("fault", ["expired", "rejected", "wrong_chain", "wrong_account", "unbound_account"])
def test_invalid_retained_operation_cannot_reach_issuer(monkeypatch, fault):
    operation = aave_operation()
    operation.approval_expires_at = time.time() + 60
    operation.smart_account = "0x" + "3" * 40
    monkeypatch.setenv("RESTRICTED_ACCOUNT_ADDRESS", operation.smart_account)
    if fault == "expired": operation.approval_expires_at = time.time() - 1
    if fault == "rejected": operation.decision = Decision.REJECTED
    if fault == "wrong_chain": operation.chain_id = 1
    if fault == "wrong_account": operation.smart_account = "0x" + "4" * 40
    if fault == "unbound_account": operation.smart_account = None
    monkeypatch.setattr(erc4337, "_call_js", lambda *_: pytest.fail("must not sign"))
    assert not erc4337.execute_approved(operation, "id")["executed"]


def test_worker_environment_never_inherits_owner_or_authority_credentials(monkeypatch):
    # Deliberately non-secret sentinel values; no actual key is read.
    monkeypatch.setenv("PRIVATE_KEY", "owner-sentinel")
    monkeypatch.setenv("GRAPH_AUTHORITY_PRIVATE_KEY", "authority-sentinel")
    monkeypatch.setenv("RESTRICTED_EXECUTOR_PRIVATE_KEY", "executor-sentinel")
    worker = erc4337._wallet_environment()
    issuer = erc4337._wallet_environment(authority=True)
    assert "PRIVATE_KEY" not in worker and "PRIVATE_KEY" not in issuer
    assert "GRAPH_AUTHORITY_PRIVATE_KEY" not in worker
    assert "RESTRICTED_EXECUTOR_PRIVATE_KEY" not in issuer
    assert worker["RESTRICTED_EXECUTOR_PRIVATE_KEY"] == "executor-sentinel"
    assert issuer["GRAPH_AUTHORITY_PRIVATE_KEY"] == "authority-sentinel"


def test_route_binding_includes_decimals_selector_quoter_and_fee():
    route = {"pool_address": "0x" + "1" * 40, "pool_fee": 3000,
             "token_in_decimals": 6, "token_out_decimals": 18,
             "function_selector": "0x04e45aaf", "quoter_address": "0x" + "2" * 40}
    for field, value in [("token_in_decimals", 18), ("token_out_decimals", 6),
                         ("pool_fee", 500), ("function_selector", "0xdeadbeef"),
                         ("quoter_address", "0x" + "3" * 40)]:
        assert api._route_signature(route) != api._route_signature({**route, field: value})


def test_new_graph_route_cannot_replace_retained_route_at_execution(monkeypatch):
    operation = aave_operation("supply")
    operation.action = operation.intent.action = "swap"
    operation.protocol = operation.intent.protocol = "Uniswap V3"
    operation.intent.token_out = "WETH"
    operation.slippage_bps = 100
    operation.verified_function = "exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))"
    operation.verified_selector = "0x04e45aaf"
    retained = {"router_address": operation.verified_address, "pool_address": "0x" + "5" * 40,
                "pool_fee": 3000, "token_in_address": operation.verified_asset,
                "token_out_address": "0x" + "6" * 40, "token_in_decimals": 6,
                "token_out_decimals": 18, "quoter_address": "0x" + "7" * 40,
                "function_signature": operation.verified_function, "function_selector": operation.verified_selector}
    operation.routes = [retained]
    newly_added = {**retained, "pool_address": "0x" + "8" * 40, "pool_fee": 500}
    current = {**graph_result(operation), "protocol": operation.protocol, "routes": [newly_added, retained]}
    store = VerificationCapabilityStore()
    token = store.issue(operation)
    monkeypatch.setattr(api, "capability_store", store)
    monkeypatch.setattr(api, "verify_intent", lambda *_: current)
    monkeypatch.setattr(api, "add_to_whitelist", lambda *_: {"success": True})
    def execute(saved, verification_id):
        assert saved.routes == [retained]
        return {"executed": True}
    monkeypatch.setattr(api, "execute_approved", execute)
    result = asyncio.run(api.execute(ExecuteRequest(verification_id=token, wallet_address="0x" + "4" * 40)))
    assert result["decision"] == "EXECUTED"
