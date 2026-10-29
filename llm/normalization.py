"""Deterministic normalization and completeness checks after LLM extraction."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from core.config import settings
from core.models import Decision, IntentCandidate, IntentResolution
from core.slippage import parse_slippage
from llm.request_constraints import constraint_labels


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


PROTOCOL_ALIASES = {
    "uniswap": "Uniswap V3",
    "uniswap v3": "Uniswap V3",
    "uni v3": "Uniswap V3",
    "aave": "Aave V3",
    "aave v3": "Aave V3",
}
ACTION_ALIASES = {
    "swap": "swap",
    "exchange": "swap",
    "trade": "swap",
    "convert": "swap",
    "supply": "supply",
    "deposit": "supply",
    "withdraw": "withdraw",
    "borrow": "borrow",
    "repay": "repay",
}
ASSET_ALIASES = {
    "weth": "WETH",
    "wrapped ether": "WETH",
    "wrapped eth": "WETH",
    "usdt": "USDT",
    "tether": "USDT",
    "tether usd": "USDT",
    "usdc": "USDC",
    "usd coin": "USDC",
    "dai": "DAI",
    "wbtc": "WBTC",
    "wrapped bitcoin": "WBTC",
    "aave": "AAVE",
    "link": "LINK",
    "chainlink": "LINK",
    "gho": "GHO",
}
NETWORK_ALIASES = {
    "ethereum sepolia": ("Ethereum Sepolia", 11155111),
    "sepolia": ("Ethereum Sepolia", 11155111),
    "sepolia testnet": ("Ethereum Sepolia", 11155111),
    "sepolia test network": ("Ethereum Sepolia", 11155111),
    "ethereum sepolia testnet": ("Ethereum Sepolia", 11155111),
    "ethereum sepolia test network": ("Ethereum Sepolia", 11155111),
    "sepolia ethereum testnet": ("Ethereum Sepolia", 11155111),
}


def _field(raw: dict[str, Any], *names: str):
    for name in names:
        if name in raw and raw[name] is not None:
            return raw[name]
    return None


def _amount(value: Any) -> tuple[Decimal | None, str | None]:
    if value is None or value == "":
        return None, None
    text = str(value).strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return None, "Amount must be a plain positive decimal number."
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        return None, "Amount is not numeric."
    if parsed <= 0:
        return None, "Amount must be greater than zero."
    decimals = len(text.partition(".")[2].rstrip("0"))
    if decimals > 18:
        return None, "Amount has more than 18 decimal places."
    return parsed.normalize(), None


def _unsupported_action_message(action: Any) -> str:
    if _key(action) in {"stake", "staking"}:
        return (
            "Staking is not implemented by this prototype. Aave's staking mechanisms "
            "are separate from the Aave V3 lending operations supported here: supply, "
            "withdraw, borrow and repay on Ethereum Sepolia. Staking cannot be "
            "treated as supplying tokens to a lending pool."
        )
    if _key(action) in {
        "transfer", "transferring", "send", "sending", "wallet transfer",
        "wallet to wallet transfer", "token transfer", "erc20 transfer", "erc 20 transfer",
    }:
        return (
            "Wallet transfers send tokens to another address; Aave supply deposits "
            "tokens into a lending pool. This prototype does not implement recipient "
            "verification or standalone wallet transfers. It supports Uniswap V3 "
            "swaps and Aave V3 supply, withdraw, borrow and repay on Ethereum Sepolia."
        )
    return f"The requested action '{action}' is not supported by this prototype."


def normalize_candidate(raw: dict[str, Any]) -> IntentResolution:
    """Normalize untrusted semantic extraction without inventing graph facts."""
    unhandled = constraint_labels(raw.get("unhandled_constraints"))
    if unhandled:
        return IntentResolution(
            status=Decision.UNSUPPORTED,
            message="This prototype cannot safely honor these conditions: " + "; ".join(unhandled) + ". No execution capability was issued.",
            error_code="unsupported_constraints", unhandled_constraints=unhandled,
        )
    try:
        slippage_bps = parse_slippage(raw.get("slippage"))
    except ValueError as exc:
        return IntentResolution(status=Decision.REJECTED, message=str(exc), error_code="invalid_slippage")
    unsupported_action = _field(raw, "unsupported_action")
    if unsupported_action and _key(unsupported_action) not in ACTION_ALIASES:
        return IntentResolution(
            status=Decision.UNSUPPORTED,
            message=_unsupported_action_message(unsupported_action),
            error_code="unsupported_action",
        )
    # The model may put a recognized verb in unsupported_action because its
    # protocol pairing is unsupported. Retain the verb so validate_candidate
    # can explain that mismatch instead of asking for an already stated action.
    action_raw = _field(raw, "action", "operation") or unsupported_action
    protocol_raw = _field(raw, "protocol")
    token_in_raw = _field(raw, "token_in", "input_asset", "inputAsset", "asset")
    token_out_raw = _field(raw, "token_out", "output_asset", "outputAsset")
    chain_raw = _field(raw, "chain", "network")

    action = ACTION_ALIASES.get(_key(action_raw)) if action_raw else None
    protocol = PROTOCOL_ALIASES.get(_key(protocol_raw)) if protocol_raw else None
    token_in = ASSET_ALIASES.get(_key(token_in_raw), str(token_in_raw).upper()) if token_in_raw else None
    token_out = ASSET_ALIASES.get(_key(token_out_raw), str(token_out_raw).upper()) if token_out_raw else None

    if action_raw and not action:
        return IntentResolution(
            status=Decision.UNSUPPORTED,
            message=_unsupported_action_message(action_raw),
            error_code="unsupported_action",
        )
    if protocol_raw and not protocol:
        return IntentResolution(
            status=Decision.UNSUPPORTED,
            message=f"The protocol '{protocol_raw}' is not supported by this prototype.",
            error_code="unsupported_protocol",
        )

    if chain_raw:
        network = NETWORK_ALIASES.get(_key(chain_raw))
        if not network:
            return IntentResolution(
                status=Decision.UNSUPPORTED,
                message=f"The network '{chain_raw}' is unsupported; use {settings.supported_network}.",
                error_code="unsupported_network",
            )
        chain, chain_id = network
    else:
        # The application is explicitly configured as a single-network testnet prototype.
        chain, chain_id = settings.supported_network, settings.supported_chain_id

    amount, amount_error = _amount(_field(raw, "amount"))
    if amount_error:
        return IntentResolution(
            status=Decision.REJECTED,
            message=amount_error,
            error_code="invalid_amount",
        )

    candidate = IntentCandidate(
        action=action,
        protocol=protocol,
        token_in=token_in,
        token_out=token_out,
        amount=amount,
        chain=chain,
        chain_id=chain_id,
        slippage_bps=slippage_bps,
    )
    return validate_candidate(candidate)


def validate_candidate(candidate: IntentCandidate) -> IntentResolution:
    if candidate.unhandled_constraints:
        return IntentResolution(
            status=Decision.UNSUPPORTED, intent=candidate,
            message="Unsupported conditions: " + "; ".join(candidate.unhandled_constraints),
            error_code="unsupported_constraints", unhandled_constraints=candidate.unhandled_constraints,
        )
    if candidate.slippage_bps is not None and candidate.action and candidate.action != "swap":
        return IntentResolution(
            status=Decision.UNSUPPORTED, intent=candidate,
            message="Slippage tolerance is supported only for Uniswap V3 swaps, not Aave lending operations.",
            error_code="unsupported_slippage_action",
        )
    if candidate.action == "swap" and candidate.protocol and candidate.protocol != "Uniswap V3":
        return IntentResolution(
            status=Decision.UNSUPPORTED,
            intent=candidate,
            message="Swap verification is supported only for Uniswap V3.",
            error_code="unsupported_action_protocol_pair",
        )
    if candidate.action in {"supply", "withdraw", "borrow", "repay"} and candidate.protocol and candidate.protocol != "Aave V3":
        return IntentResolution(
            status=Decision.UNSUPPORTED,
            intent=candidate,
            message=f"{candidate.action.title()} verification is supported only for Aave V3.",
            error_code="unsupported_action_protocol_pair",
        )

    required = ["action", "protocol", "amount", "token_in"]
    if candidate.action == "swap":
        required.append("token_out")
    missing = [name for name in required if getattr(candidate, name) is None]
    if missing:
        friendly = {
            "action": "operation",
            "protocol": "protocol",
            "amount": "amount",
            "token_in": "input asset",
            "token_out": "output asset",
        }
        labels = [friendly[name] for name in missing]
        return IntentResolution(
            status=Decision.NEEDS_CLARIFICATION,
            intent=candidate,
            missing_fields=missing,
            message="Please provide the " + ", ".join(labels) + ".",
            error_code="missing_fields",
        )
    if candidate.action == "swap" and candidate.token_in == candidate.token_out:
        return IntentResolution(
            status=Decision.REJECTED,
            intent=candidate,
            message="Input and output assets must be different for a swap.",
            error_code="invalid_asset_pair",
        )
    return IntentResolution(
        status=Decision.APPROVED,
        intent=candidate,
        message="Intent is complete and ready for graph verification.",
    )


def merge_clarification(
    pending: IntentCandidate,
    missing_fields: list[str],
    update: IntentCandidate,
) -> IntentCandidate | None:
    """Merge only fields explicitly missing from the current candidate.

    A message containing a new action or protocol starts a new operation and is
    therefore never merged into stale state.
    """
    if update.action or update.protocol:
        return None
    # Never discard new conditions or silently change a previously specified
    # slippage bound while filling an unrelated missing field.
    if update.unhandled_constraints or (
        update.slippage_bps is not None and update.slippage_bps != pending.slippage_bps
    ):
        return None
    update_data = update.model_dump()
    if not any(update_data.get(name) is not None for name in missing_fields):
        return None
    merged = pending.model_dump()
    for name in missing_fields:
        if update_data.get(name) is not None:
            merged[name] = update_data[name]
    return IntentCandidate.model_validate(merged)
