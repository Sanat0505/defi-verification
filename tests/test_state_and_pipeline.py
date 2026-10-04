import asyncio
from decimal import Decimal

from core.models import ApprovedOperation, Decision, IntentCandidate, IntentResolution, PromptRequest
from core.state import ConversationStore, VerificationCapabilityStore
from services import pipeline


def _partial():
    return IntentResolution(
        status=Decision.NEEDS_CLARIFICATION,
        intent=IntentCandidate(
            action="swap", protocol="Uniswap V3", token_in="WETH",
            token_out="USDT", chain="Ethereum Sepolia", chain_id=11155111,
        ),
        message="amount needed",
        missing_fields=["amount"],
    )


def test_multi_turn_clarification_uses_explicit_candidate(monkeypatch):
    responses = [
        _partial(),
        IntentResolution(
            status=Decision.NEEDS_CLARIFICATION,
            intent=IntentCandidate(amount=Decimal("0.1"), token_in="WETH"),
            message="partial", missing_fields=["action", "protocol", "token_out"],
        ),
    ]
    async def fake_parse(_prompt):
        return responses.pop(0)
    monkeypatch.setattr(pipeline, "parse_intent", fake_parse)
    monkeypatch.setattr(pipeline, "conversation_store", ConversationStore())
    monkeypatch.setattr(pipeline, "verify_intent", lambda *args: {
        "decision": "REJECTED", "reason": "test graph miss", "latency_ms": 1,
    })
    first = asyncio.run(pipeline.process_prompt(PromptRequest(prompt="Swap WETH to USDT", conversation_id="c1")))
    second = asyncio.run(pipeline.process_prompt(PromptRequest(prompt="0.1 WETH", conversation_id="c1")))
    assert first["decision"] == "NEEDS_CLARIFICATION"
    assert second["intent"]["amount"] == "0.1"
    assert second["intent"]["action"] == "swap"


def test_capability_is_one_time():
    store = VerificationCapabilityStore(ttl_seconds=60)
    operation = ApprovedOperation(
        intent=IntentCandidate(
            action="swap", protocol="Uniswap V3", token_in="WETH", token_out="USDT",
            amount=Decimal("0.1"), chain="Ethereum Sepolia", chain_id=11155111,
        ),
        protocol="Uniswap V3", action="swap", chain_id=11155111,
        network="Ethereum Sepolia", verified_address="0x" + "1" * 40,
        verified_function="exactInputSingle(tuple)", verified_selector="0x04e45aaf",
    )
    token = store.issue(operation)
    assert store.claim(token) is not None
    assert store.claim(token) is None


def test_capability_claim_reports_expired_and_reused_statuses():
    operation = ApprovedOperation(
        intent=IntentCandidate(
            action="swap", protocol="Uniswap V3", token_in="WETH", token_out="USDT",
            amount=Decimal("0.1"), chain="Ethereum Sepolia", chain_id=11155111,
        ),
        protocol="Uniswap V3", action="swap", chain_id=11155111,
        network="Ethereum Sepolia", verified_address="0x" + "1" * 40,
        verified_function="exactInputSingle(tuple)", verified_selector="0x04e45aaf",
    )
    live_store = VerificationCapabilityStore(ttl_seconds=60)
    token = live_store.issue(operation)
    assert live_store.claim_with_status(token)[1] == "VERIFICATION_CLAIMED"
    assert live_store.claim_with_status(token)[1] == "VERIFICATION_REUSED"

    expired_store = VerificationCapabilityStore(ttl_seconds=-1)
    expired = expired_store.issue(operation)
    assert expired_store.claim_with_status(expired)[1] == "VERIFICATION_EXPIRED"


def test_contextual_clarification_can_fill_output_asset(monkeypatch):
    responses = [
        IntentResolution(
            status=Decision.NEEDS_CLARIFICATION,
            intent=IntentCandidate(
                action="swap", protocol="Uniswap V3", token_in="USDC",
                amount=Decimal("0.1"), chain="Ethereum Sepolia", chain_id=11155111,
            ),
            message="output needed", missing_fields=["token_out"],
        ),
        IntentResolution(
            status=Decision.NEEDS_CLARIFICATION,
            intent=IntentCandidate(token_in="WETH"),
            message="partial", missing_fields=["action", "protocol", "amount", "token_out"],
        ),
    ]
    async def fake_parse(_prompt):
        return responses.pop(0)
    async def fake_context(*_args):
        return IntentResolution(
            status=Decision.NEEDS_CLARIFICATION,
            intent=IntentCandidate(token_out="WETH"),
            message="partial", missing_fields=["action", "protocol", "amount", "token_in"],
        )
    monkeypatch.setattr(pipeline, "parse_intent", fake_parse)
    monkeypatch.setattr(pipeline, "parse_clarification", fake_context)
    monkeypatch.setattr(pipeline, "conversation_store", ConversationStore())
    monkeypatch.setattr(pipeline, "verify_intent", lambda *args: {
        "decision": "REJECTED", "reason": "test graph miss", "latency_ms": 1,
    })
    asyncio.run(pipeline.process_prompt(PromptRequest(
        prompt="Swap 0.1 USDC on Uniswap V3", conversation_id="c2"
    )))
    result = asyncio.run(pipeline.process_prompt(PromptRequest(
        prompt="I want WETH", conversation_id="c2"
    )))
    assert result["intent"]["token_out"] == "WETH"
