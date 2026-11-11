import asyncio

import pytest

from source.core.models import Decision, IntentCandidate
from source.core.slippage import parse_slippage
from source.llm import intent_parser
from source.llm.normalization import normalize_candidate, validate_candidate
from source.llm.request_constraints import enforce_request_constraints


BASE = {"action": "swap", "protocol": "Uniswap V3", "token_in": "USDC",
        "token_out": "WETH", "amount": "10", "chain": "Sepolia"}
PROMPT = "Swap 10 USDC for WETH on Uniswap V3 on Sepolia"


@pytest.mark.parametrize("value,unit,expected", [("0.25", "percent", 25), ("25", "bps", 25),
    ("1", "percent", 100), ("0.01", "percent", 1), ("5", "percent", 500), ("25.0", "bps", 25)])
def test_exact_slippage_conversion(value, unit, expected):
    assert parse_slippage({"value": value, "unit": unit}) == expected


@pytest.mark.parametrize("slippage", [
    {"value": "0", "unit": "percent"}, {"value": "-0.25", "unit": "percent"},
    {"value": "5.01", "unit": "percent"}, {"value": "0.255", "unit": "percent"},
    {"value": "0.250000000000000000000000000001", "unit": "percent"},
    {"value": "2.5", "unit": "bps"}, {"value": "NaN", "unit": "percent"},
    {"value": "1e-2", "unit": "percent"}, {"value": True, "unit": "bps"},
    {"value": 0.25, "unit": "percent"}, {"value": "25", "unit": None}, "0.25%",
])
def test_invalid_slippage_is_never_defaulted_or_rounded(slippage):
    result = normalize_candidate({**BASE, "slippage": slippage})
    assert result.status == Decision.REJECTED
    assert result.error_code == "invalid_slippage"


@pytest.mark.parametrize("suffix", [
    ", maximum slippage 0.25%.", ", with at most 0.25% slippage.",
    ", slippage tolerance of 0.25 percent.", ", with 25 bps slippage.",
    ", slippage at most 25 basis points.", ", slippage <=0.25%.",
])
def test_valid_slippage_survives_real_parser_boundary(monkeypatch, suffix):
    monkeypatch.setattr(intent_parser, "_call_model", lambda _: {**BASE, "slippage": {"value": "0.25", "unit": "percent"}})
    result = asyncio.run(intent_parser.parse_intent(PROMPT + suffix))
    assert result.status == Decision.APPROVED
    assert result.intent.slippage_bps == 25


@pytest.mark.parametrize("suffix,flag", [
    (", finish within one minute.", "deadline"),
    (", before 2030-01-01.", "deadline"),
    (", send the output to 0x1111111111111111111111111111111111111111.", "custom_recipient_or_beneficiary"),
    (", keep gas below 0.001 ETH.", "gas_or_fee_condition"),
    (", receive at least 0.002 WETH.", "minimum_output"),
    (", only if my health factor stays above 2.", "position_condition"),
    (", then supply 5 USDT to Aave V3.", "multiple_operations"),
    (", with price impact at most 1%.", "price_impact_condition"),
])
def test_known_conditions_are_blocked_even_if_model_drops_them(monkeypatch, suffix, flag):
    monkeypatch.setattr(intent_parser, "_call_model", lambda _: BASE)
    result = asyncio.run(intent_parser.parse_intent(PROMPT + suffix))
    assert result.status == Decision.UNSUPPORTED
    assert result.error_code == "unsupported_constraints"
    assert flag in result.unhandled_constraints


@pytest.mark.parametrize("query", [
    "Swap $100 worth of ETH for USDC using Uniswap V3.",
    "Withdraw all my USDT from Aave V3.",
    "Repay my entire USDT debt on Aave V3.",
    "Borrow 5 USDT using Aave V3 at a fixed interest rate.",
])
def test_unsupported_quantity_or_rate_not_reduced_to_plain_amount(monkeypatch, query):
    monkeypatch.setattr(intent_parser, "_call_model", lambda _: BASE)
    assert asyncio.run(intent_parser.parse_intent(query)).status == Decision.UNSUPPORTED


def test_usd_coin_alias_is_not_a_fiat_amount():
    guarded = enforce_request_constraints("Swap 10 USD Coin for WETH on Uniswap V3.", BASE)
    assert not guarded["unhandled_constraints"]


def test_arbitrary_model_reported_condition_is_not_discarded():
    result = normalize_candidate({**BASE, "unhandled_constraints": ["execute only after an external approval"]})
    assert result.status == Decision.UNSUPPORTED


@pytest.mark.parametrize("raw", [{**BASE}, {**BASE, "slippage": {"value": "1", "unit": "percent"}}])
def test_slippage_omission_or_change_blocks_progress(raw):
    result = normalize_candidate(enforce_request_constraints(PROMPT + ", maximum slippage 0.25%.", raw))
    assert result.status == Decision.UNSUPPORTED
    assert "slippage_not_preserved" in result.unhandled_constraints


@pytest.mark.parametrize("suffix", [", slippage must be low.", ", slippage 0.25.",
    ", less than 0.25% slippage.", ", slippage 0.25% and slippage 1%."])
def test_ambiguous_strict_or_conflicting_slippage_is_not_silently_accepted(suffix):
    raw = {**BASE, "slippage": {"value": "0.25", "unit": "percent"}}
    assert normalize_candidate(enforce_request_constraints(PROMPT + suffix, raw)).status == Decision.UNSUPPORTED


def test_model_cannot_invent_slippage():
    raw = {**BASE, "slippage": {"value": "0.25", "unit": "percent"}}
    assert normalize_candidate(enforce_request_constraints(PROMPT, raw)).status == Decision.UNSUPPORTED


def test_slippage_plus_deadline_still_blocks():
    raw = {**BASE, "slippage": {"value": "0.25", "unit": "percent"}}
    assert normalize_candidate(enforce_request_constraints(PROMPT + ", slippage 0.25%, finish within one minute.", raw)).status == Decision.UNSUPPORTED


def test_lending_slippage_is_unsupported():
    result = normalize_candidate({**BASE, "action": "supply", "protocol": "Aave V3",
                                  "token_out": None, "slippage": {"value": "1", "unit": "percent"}})
    assert result.error_code == "unsupported_slippage_action"


def test_typed_candidate_cannot_bypass_constraint_validation():
    candidate = IntentCandidate(**BASE, unhandled_constraints=["deadline"])
    assert validate_candidate(candidate).status == Decision.UNSUPPORTED


def test_constrained_clarification_is_also_blocked(monkeypatch):
    monkeypatch.setattr(intent_parser, "_call_model", lambda *args: {"amount": "10"})
    result = asyncio.run(intent_parser.parse_clarification("10 USDC, finish within one minute", BASE, ["amount"]))
    assert result.status == Decision.UNSUPPORTED
