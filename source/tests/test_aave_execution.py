import asyncio
from decimal import Decimal

from source.api import app as api_module
from source.core.models import ApprovedOperation, Decision, ExecuteRequest, IntentCandidate, IntentResolution, PromptRequest
from source.core.state import VerificationCapabilityStore
from source.services import pipeline
from source.wallet import erc4337


def aave_operation(action="withdraw"):
    signatures = {
        "supply": ("supply(address,uint256,address,uint16)", "0x617ba037"),
        "withdraw": ("withdraw(address,uint256,address)", "0x69328dec"),
        "borrow": ("borrow(address,uint256,uint256,uint16,address)", "0xa415bcad"),
        "repay": ("repay(address,uint256,uint256,address)", "0x573ade81"),
    }
    signature, selector = signatures[action]
    return ApprovedOperation(
        intent=IntentCandidate(
            action=action, protocol="Aave V3", token_in="USDT",
            amount=Decimal("10"), chain="Ethereum Sepolia", chain_id=11155111,
        ),
        protocol="Aave V3", action=action, chain_id=11155111,
        network="Ethereum Sepolia", verified_address="0x" + "1" * 40,
        verified_asset="0x" + "2" * 40, verified_asset_symbol="USDT",
        verified_asset_decimals=6, verified_function=signature,
        verified_selector=selector,
        interest_rate_mode=2 if action in {"borrow", "repay"} else None,
    )


def graph_result(operation):
    return {
        "decision": "APPROVED",
        "protocol": "Aave V3",
        "action": operation.action,
        "chain_id": 11155111,
        "network": "Ethereum Sepolia",
        "verified_address": operation.verified_address,
        "verified_pool": None,
        "verified_asset": operation.verified_asset,
        "verified_asset_decimals": operation.verified_asset_decimals,
        "verified_function": operation.verified_function,
        "verified_selector": operation.verified_selector,
        "latency_ms": 1,
    }


def test_pipeline_issues_execution_capability_for_aave(monkeypatch):
    operation = aave_operation()
    async def parse(_prompt):
        return IntentResolution(
            status=Decision.APPROVED,
            intent=operation.intent,
            message="ready",
        )
    store = VerificationCapabilityStore()
    monkeypatch.setattr(pipeline, "parse_intent", parse)
    monkeypatch.setattr(pipeline, "verify_intent", lambda *args: graph_result(operation))
    monkeypatch.setattr(pipeline, "capability_store", store)
    result = asyncio.run(pipeline.process_prompt(PromptRequest(prompt="withdraw 10 usdt from aave")))
    assert result["decision"] == "APPROVED"
    assert result["executable"] is True
    assert store.claim(result["verification_id"]).action == "withdraw"


def test_execute_uses_graph_approved_aave_operation(monkeypatch):
    operation = aave_operation("repay")
    store = VerificationCapabilityStore()
    token = store.issue(operation)
    captured = {}
    monkeypatch.setattr(api_module, "capability_store", store)
    monkeypatch.setattr(api_module, "verify_intent", lambda *args: graph_result(operation))
    monkeypatch.setattr(api_module, "add_to_whitelist", lambda address: {"success": True})
    def execute(payload):
        captured.update(payload)
        return {
            "executed": True, "tx_hash": "0xabc", "smart_wallet": "0x" + "3" * 40,
            "verified_address": operation.verified_address, "asset_address": operation.verified_asset,
            "token_in": "USDT", "amount_in": "10", "action": "repay",
        }
    monkeypatch.setattr(api_module, "execute_aave", execute)
    result = asyncio.run(api_module.execute(ExecuteRequest(
        verification_id=token,
        wallet_address="0x" + "4" * 40,
    )))
    assert result["decision"] == "EXECUTED"
    assert captured == {
        "action": "repay",
        "pool_address": operation.verified_address,
        "asset_address": operation.verified_asset,
        "asset_symbol": "USDT",
        "asset_decimals": 6,
        "amount": "10",
        "function_signature": operation.verified_function,
        "function_selector": operation.verified_selector,
        "interest_rate_mode": 2,
        "referral_code": 0,
    }


def test_python_wallet_wrapper_passes_only_structured_aave_payload(monkeypatch):
    captured = {}
    monkeypatch.setattr(erc4337, "_call_js", lambda command, args: captured.update(command=command, args=args) or {"success": True})
    payload = {"action": "withdraw", "pool_address": "0x" + "1" * 40}
    assert erc4337.execute_aave(payload)["success"] is True
    assert captured == {"command": "send_aave", "args": payload}
