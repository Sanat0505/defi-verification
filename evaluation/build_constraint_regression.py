"""Author a versioned 60-case development suite, without calling a model.

These are assistant-authored implementation regressions, NOT new independent
researcher-reviewed thesis test data. Old source datasets/reports are untouched.
"""

import json
from pathlib import Path

from evaluation.build_sourced_dataset import intent, make_case, validate_dataset


OUTPUT = Path(__file__).resolve().parent / "datasets" / "constraint_regression_v1.json"
SWAP = "Swap 10 USDC for WETH on Uniswap V3 on Ethereum Sepolia"


def build():
    cases = []

    def add(category, query, status="APPROVED", expected=None, rationale="", missing=None):
        cases.append(make_case(
            f"CONSTRAINT-V1-{len(cases) + 1:03d}", category, query, status,
            family=f"constraint-v1-{category}", split="development", expected=expected,
            rationale=rationale, origin="implementation_based_synthetic",
            sources=[{"source_id": "constraint_policy_v1", "path": "evaluation/CONSTRAINT_HANDLING.md"}],
            expected_missing_fields=missing or [],
        ))

    def swap(bps=None, **overrides):
        return {**intent("swap", "10", "USDC", "Uniswap V3", "WETH"),
                "slippage_bps": bps, **overrides}

    for network in ["Sepolia", "Ethereum Sepolia", "Sepolia testnet", "Sepolia test network",
                    "Ethereum Sepolia testnet", "Ethereum Sepolia test network",
                    "Sepolia (Ethereum testnet)", "ETHEREUM-SEPOLIA"]:
        add("network_alias", f"Swap 10 USDC for WETH on Uniswap V3 on {network}.", expected=swap(),
            rationale="An explicit Ethereum Sepolia alias maps to chain 11155111; omitted slippage remains null in the intent.")

    for action, preposition in [("supply", "to"), ("withdraw", "from"), ("borrow", "from"), ("repay", "on")]:
        add("aave_core", f"{action.title()} 10 USDT {preposition} Aave V3 on Sepolia test network.",
            expected={**intent(action, "10"), "slippage_bps": None},
            rationale="A supported exact-amount Aave operation; wallet position/balance is not evaluated at interpretation.")

    for suffix, bps in [
        ("maximum slippage 0.25%", 25), ("at most 0.25% slippage", 25),
        ("slippage tolerance of 0.25 percent", 25), ("25 bps slippage", 25),
        ("slippage at most 25 basis points", 25), ("slippage <=0.25%", 25),
        ("slippage 0.01%", 1), ("slippage 5%", 500),
        ("100 basis points slippage", 100), ("slippage 25.0 bps", 25),
    ]:
        add("supported_slippage", SWAP + ", " + suffix + ".", expected=swap(bps),
            rationale="An inclusive maximum in percent/bps is exactly representable as 1..500 whole basis points. Preserve it end to end.")

    for value in ["0%", "-0.25%", "5.01%", "0.255%", "2.5 bps", "501 bps"]:
        add("invalid_slippage", SWAP + ", slippage " + value + ".", "REJECTED",
            rationale="Explicit tolerance is outside the 1..500 bps policy or cannot be represented without rounding. Do not default it.")

    for suffix in [
        "finish within one minute", "complete before 2030-01-01",
        "send the output to 0x1111111111111111111111111111111111111111",
        "keep gas below 0.001 ETH", "receive at least 0.002 WETH",
        "only if my health factor stays above 2", "then supply 5 USDT to Aave V3",
        "price impact at most 1%", "slippage must be low", "slippage 0.25",
        "less than 0.25% slippage", "slippage 0.25% and slippage 1%",
        "slippage 0.25% and finish within one minute",
    ]:
        add("unsupported_condition", SWAP + ", " + suffix + ".", "UNSUPPORTED",
            rationale="The requested additional condition is unsupported, ambiguous, conflicting or strictly bounded; a basic-action approval would lose user meaning.")
    for query in [
        "Swap $100 worth of ETH for USDC using Uniswap V3 on Sepolia.",
        "Withdraw all my USDT from Aave V3 on Sepolia.",
        "Repay my entire USDT debt on Aave V3 on Sepolia.",
        "Borrow 5 USDT from Aave V3 on Sepolia at a fixed interest rate.",
        "Supply 10 USDT to Aave V3 on Sepolia with 1% slippage.",
    ]:
        add("unsupported_condition", query, "UNSUPPORTED",
            rationale="Fiat/relative quantity, fixed-rate lending or slippage on lending is outside the implemented scope.")

    for query in [
        "Swap 10 USDC for WETH on Uniswap V2 on Sepolia.",
        "Swap 10 USDC for WETH on Uniswap V4 on Sepolia.",
        "Swap 10 USDC for WETH on Uniswap V3 on Base Sepolia.",
        "Swap 10 USDC for WETH on Uniswap V3 on Arbitrum Sepolia.",
        "Swap 10 USDC for WETH on Uniswap V3 on Ethereum mainnet.",
        "Supply 10 USDT to Compound V2 on Sepolia.",
    ]:
        add("unsupported_scope", query, "UNSUPPORTED",
            rationale="Preserve the explicit unsupported protocol version or network; do not replace it with the configured default.")

    for query, fields, expected in [
        ("Swap USDC for WETH on Uniswap V3 on Sepolia.", ["amount"], swap(amount=None)),
        ("Swap 10 USDC on Uniswap V3 on Sepolia.", ["token_out"], swap(token_out=None)),
        ("Swap 10 USDC for WETH on Sepolia.", ["protocol"], swap(protocol=None)),
        ("Use Aave V3 with 10 USDT on Sepolia.", ["action"], {**intent(None, "10"), "slippage_bps": None}),
    ]:
        add("missing_fields", query, "NEEDS_CLARIFICATION", expected=expected, missing=fields,
            rationale="A required semantic field is not stated; ask for it instead of guessing.")

    for amount in ["0", "-1", "many", "0.0000000000000000001"]:
        add("invalid_amount", f"Swap {amount} USDC for WETH on Uniswap V3 on Sepolia.", "REJECTED",
            rationale="The exact-input amount is zero, negative, non-numeric, or more precise than the 18-decimal application boundary.")

    dataset = {"version": "constraint-regression-1.0.0-draft", "requires_sourced_runner": True,
               "purpose": "Targeted development regression after alias, constraint and slippage changes; not a replacement for the frozen baseline or final holdout.",
               "reference_policy": "Assistant-authored expected outcomes fixed before live model calls; independent researcher review remains required.",
               "cases": cases}
    validate_dataset(dataset)
    assert len(cases) == 60
    return dataset


if __name__ == "__main__":
    # Refuse to replace a version that might already have recorded results.
    with OUTPUT.open("x", encoding="utf-8") as stream:
        json.dump(build(), stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(f"Wrote 60 development cases: {OUTPUT}")
