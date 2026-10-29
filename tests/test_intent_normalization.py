from decimal import Decimal

import pytest

from core.models import Decision, IntentCandidate
from llm.normalization import merge_clarification, normalize_candidate


@pytest.mark.parametrize("chain", [
    "Sepolia", "Ethereum Sepolia", "Sepolia testnet", "Sepolia test network",
    "Ethereum Sepolia testnet", "Ethereum Sepolia test network",
    "Sepolia (Ethereum testnet)", "SEPOLIA TESTNET",
])
def test_sepolia_network_aliases(chain):
    result = normalize_candidate({
        "action": "swap", "protocol": "Uniswap V3", "token_in": "USDC",
        "token_out": "WETH", "amount": "3.75", "chain": chain,
    })
    assert result.status == Decision.APPROVED
    assert result.intent.chain == "Ethereum Sepolia"
    assert result.intent.chain_id == 11155111


@pytest.mark.parametrize("chain", [
    "Base Sepolia", "Arbitrum Sepolia", "Optimism Sepolia", "Ethereum mainnet",
    "Ethereum testnet", "Sepolia or mainnet",
])
def test_explicit_other_or_ambiguous_networks_are_not_aliases(chain):
    result = normalize_candidate({
        "action": "swap", "protocol": "Uniswap V3", "token_in": "USDC",
        "token_out": "WETH", "amount": "3.75", "chain": chain,
    })
    assert result.status == Decision.UNSUPPORTED
    assert result.error_code == "unsupported_network"


@pytest.mark.parametrize("protocol", ["uniswap", "Uniswap", "UNISWAP V3", "Uni v3"])
def test_protocol_aliases_normalize(protocol):
    result = normalize_candidate({
        "action": "exchange",
        "protocol": protocol,
        "token_in": "wrapped ether",
        "token_out": "tether",
        "amount": "0.10",
    })
    assert result.status == Decision.APPROVED
    assert result.intent.protocol == "Uniswap V3"
    assert result.intent.token_in == "WETH"
    assert result.intent.token_out == "USDT"
    assert result.intent.amount == Decimal("0.1")


@pytest.mark.parametrize("amount", ["0", "-1", "one", "1e3", "0.0000000000000000001"])
def test_invalid_amounts_are_controlled_rejections(amount):
    result = normalize_candidate({
        "action": "swap", "protocol": "Uniswap V3",
        "token_in": "WETH", "token_out": "USDT", "amount": amount,
    })
    assert result.status == Decision.REJECTED
    assert result.error_code == "invalid_amount"


def test_missing_amount_requests_clarification():
    result = normalize_candidate({
        "action": "swap", "protocol": "Uniswap V3",
        "token_in": "WETH", "token_out": "USDT", "amount": None,
    })
    assert result.status == Decision.NEEDS_CLARIFICATION
    assert result.missing_fields == ["amount"]


def test_unsupported_protocol_is_not_replaced():
    result = normalize_candidate({
        "action": "swap", "protocol": "Curve", "token_in": "WETH",
        "token_out": "USDT", "amount": "1",
    })
    assert result.status == Decision.UNSUPPORTED
    assert result.error_code == "unsupported_protocol"


def test_explicit_unsupported_action_is_not_mapped_to_supply():
    result = normalize_candidate({
        "action": "supply", "unsupported_action": "stake", "protocol": "Aave V3",
        "token_in": "WETH", "amount": "2",
    })
    assert result.status == Decision.UNSUPPORTED


def test_supported_action_is_not_misclassified_by_model_flag():
    result = normalize_candidate({
        "action": "swap", "unsupported_action": "swap", "protocol": "Uniswap V3",
        "token_in": None, "token_out": None, "amount": None,
    })
    assert result.status == Decision.NEEDS_CLARIFICATION


@pytest.mark.parametrize("action,protocol", [
    ("borrow", "Uniswap V3"), ("supply", "Uniswap V3"),
    ("withdraw", "Uniswap V3"), ("repay", "Uniswap V3"),
    ("swap", "Aave V3"),
])
def test_misplaced_supported_verb_reports_protocol_mismatch(action, protocol):
    result = normalize_candidate({
        "action": None, "unsupported_action": action, "protocol": protocol,
        "token_in": "USDT", "amount": "5",
    })
    assert result.status == Decision.UNSUPPORTED
    assert result.error_code == "unsupported_action_protocol_pair"
    assert result.intent.action == action
    assert result.intent.protocol == protocol
    assert not result.missing_fields


def test_recovered_action_still_requires_missing_amount():
    result = normalize_candidate({
        "action": None, "unsupported_action": "borrow", "protocol": "Aave V3",
        "token_in": "USDT",
    })
    assert result.status == Decision.NEEDS_CLARIFICATION
    assert result.intent.action == "borrow"
    assert result.missing_fields == ["amount"]


def test_unsupported_staking_is_not_recovered_as_supply():
    result = normalize_candidate({
        "action": None, "unsupported_action": "stake", "protocol": "Aave V3",
        "token_in": "WETH", "amount": "2",
    })
    assert result.status == Decision.UNSUPPORTED
    assert result.error_code == "unsupported_action"
    assert result.intent is None


def test_clarification_merges_only_missing_fields():
    pending = IntentCandidate(
        action="swap", protocol="Uniswap V3", token_in="WETH",
        token_out="USDT", chain="Ethereum Sepolia", chain_id=11155111,
    )
    update = IntentCandidate(amount=Decimal("0.1"), token_in="WETH")
    merged = merge_clarification(pending, ["amount"], update)
    assert merged.amount == Decimal("0.1")
    assert merged.token_out == "USDT"


def test_new_action_is_not_merged_into_stale_candidate():
    pending = IntentCandidate(action="swap", protocol="Uniswap V3", token_in="WETH")
    update = IntentCandidate(action="supply", protocol="Aave V3", amount=Decimal("10"))
    assert merge_clarification(pending, ["token_out", "amount"], update) is None
