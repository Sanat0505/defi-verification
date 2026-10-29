"""Build 500 NEW exploratory cases, preserving the original 120-case dataset.

References are assistant/rule-authored drafts, never labels generated from the
system under test. No model, graph, wallet or transaction is called here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

from evaluation.build_sourced_dataset import (
    AAVE_DOC, OUTPUT as BASELINE, REVIEW, ROOT, UNISWAP_DOC,
    intent, make_case, source_reference, validate_dataset,
)
from evaluation.source_import import COMMIT, constraint_flags, load_source, source_family

OUTPUT = ROOT / "evaluation" / "datasets" / "expanded_500_cases.json"
SEED = 20261011


def canonical_query(text):
    return " ".join(text.casefold().split())


def sample_sources(name, count, excluded_families, excluded_queries):
    """Sample unique historical families; exclude all baseline source wording.

    Original and adapted variants stay in the same family. Selection is seeded
    and independent of upstream alignment labels and model predictions.
    """
    families = {}
    for record in load_source(name):
        family = "source:" + source_family(record)
        query = record["human_intent"]
        if family in excluded_families or canonical_query(query) in excluded_queries:
            continue
        if not 0 < len(query) <= 1800:
            continue
        # Narrow evidence for the Uniswap constraint stratum, not broad keywords
        # such as 'before'. Retain the complete original query for human review.
        if name == "uniswap" and not (
            re.search(r"\bUniswap\b", query, re.I)
            and re.search(r"\bslippage\b", query, re.I)
            and re.search(r"\d+(?:\.\d+)?\s*%", query)
        ):
            continue
        families.setdefault(family, []).append(record)
    rng = random.Random(f"{SEED}:{name}")
    candidates = sorted(families)
    rng.shuffle(candidates)
    chosen, seen_queries = [], set(excluded_queries)
    for family in candidates:
        variants = sorted(families[family], key=lambda r: r.get("test_id") or r["sample_id"])
        rng.shuffle(variants)
        for record in variants:
            key = canonical_query(record["human_intent"])
            if key not in seen_queries:
                chosen.append(record)
                seen_queries.add(key)
                break
        if len(chosen) == count:
            return chosen
    raise ValueError(f"Not enough distinct eligible {name} families")


def documented(case_id, query, action, category, status="APPROVED", expected=None,
               missing=(), template=None, rationale=None):
    protocol = "Uniswap V3" if action == "swap" else "Aave V3"
    return make_case(
        case_id, category, query, status, f"expanded-scenario:{case_id}",
        split="development", expected=expected, expected_missing_fields=list(missing),
        origin="documentation_based_synthetic", template_id=template or case_id,
        rationale=rationale or (
            "Assistant-specified semantic reference for a documented operation. "
            "APPROVED means complete interpretation only; no token-pair pool, "
            "reserve, balance, collateral or execution feasibility is asserted."
        ),
        sources=[{"source_id": "uniswap_swap_docs" if action == "swap" else "aave_pool_docs",
                  "url": UNISWAP_DOC if action == "swap" else AAVE_DOC + "#" + action}],
        protocol_under_test=protocol,
    )


def add_core(cases):
    # Twenty language templates x two distinct asset/amount scenarios. These are
    # correlated templates, not forty independent natural-language observations.
    swap_templates = [
        "On Sepolia use Uniswap V3 to trade {n} {a} into {b}.",
        "I'd like {b}; exchange my {n} {a} through Uniswap V3 on Sepolia.",
        "Input: {n} {a}. Output asset: {b}. Swap on Uniswap V3, Ethereum Sepolia.",
        "Can you convert {n} {a} to {b} on Ethereum Sepolia with Uniswap V3?",
        "Use Uniswap V3 on Sepolia for a swap: {n} {a} in, {b} out.",
        "Please sell {n} {a} for {b} via Uniswap V3 on Sepolia.",
        "I have decided to swap {n} {a} into {b}. Use Sepolia and Uniswap V3.",
        "Network Sepolia; protocol Uniswap V3; exchange {n} {a} for {b}.",
        "The amount to spend is {n} {a}; swap it for {b} using Uniswap V3 on Sepolia.",
        "Using Ethereum Sepolia's Uniswap V3, exchange an input of {n} {a} for {b}.",
        "Uniswap V3 / Sepolia: swap {n} {a} -> {b}.",
        "For my Sepolia trade on Uniswap V3, take {n} {a} as input and buy {b}.",
        "I want to trade using Uniswap V3 on Sepolia. Exchange {n} {a} for {b}.",
        "Could Uniswap V3 on Ethereum Sepolia swap {n} {a} into {b} for me?",
        "Buy {b} with {n} {a} using Uniswap V3 on Sepolia.",
        "Swap request on Sepolia: use Uniswap V3, spend {n} {a}, receive {b}.",
        "Please exchange the following on Uniswap V3 (Sepolia): {n} {a} for {b}.",
        "Take {n} {a} and convert it into {b}; the protocol is Uniswap V3 and the network is Sepolia.",
        "On the Sepolia testnet, I'd like a Uniswap V3 exchange from {a} to {b}, input amount {n}.",
        "My requested operation is a swap of {n} {a} into {b}, on Uniswap V3, Ethereum Sepolia.",
    ]
    for t, template in enumerate(swap_templates, 1):
        for v, (amount, asset, output) in enumerate((("3.75", "USDC", "WETH"), ("0.08", "ETH", "USDT")), 1):
            cases.append(documented(f"EXP-UNI-CORE-{t:02}-{v}", template.format(n=amount, a=asset, b=output),
                                    "swap", "expanded_uniswap_core",
                                    expected=intent("swap", amount, asset, "Uniswap V3", output),
                                    template=f"swap-language-{t:02}"))

    verb = {
        "supply": ("supply", "deposit", "to"),
        "withdraw": ("withdraw", "withdraw", "from"),
        "borrow": ("borrow", "borrow", "from"),
        "repay": ("repay", "repay", "on"),
    }
    aave_templates = [
        "On Sepolia, {v} {n} {a} {p} Aave V3.",
        "Aave V3, Ethereum Sepolia: {v} {n} {a}.",
        "Please {alt} {n} {a} {p} Aave V3 using Sepolia.",
        "I'd like to {v} {n} {a}. Use Aave V3 on Ethereum Sepolia.",
        "Could you {v} {n} {a} {p} Aave V3 on Sepolia?",
        "Network: Ethereum Sepolia. Protocol: Aave V3. Operation: {v} {n} {a}.",
        "Use the Aave V3 {v} operation for {n} {a} on Sepolia.",
        "The asset is {a}, the amount is {n}; {v} it {p} Aave V3 on Sepolia.",
        "I want to {v} exactly {n} {a} {p} Aave V3 on the Sepolia testnet.",
        "For Aave V3 on Sepolia, my request is: {v} {n} {a}.",
        "Can we {alt} {n} {a} {p} Aave V3, on Ethereum Sepolia please?",
        "Please use Sepolia's Aave V3 to {v} {n} {a}.",
        "{v} request: amount {n}, token {a}, protocol Aave V3, network Ethereum Sepolia.",
        "I have chosen Aave V3 and Sepolia. I would like to {v} {n} {a}.",
        "On Ethereum Sepolia with Aave V3, please {v} an amount of {n} {a}.",
    ]
    for action, (primary, alternative, preposition) in verb.items():
        for t, template in enumerate(aave_templates, 1):
            amount, asset = [("6.25", "USDT"), ("8.5", "USDC"), ("0.04", "WETH")][(t-1) % 3]
            cases.append(documented(f"EXP-AAVE-{action.upper()}-CORE-{t:02}",
                template.format(v=primary, alt=alternative, p=preposition, n=amount, a=asset),
                action, "expanded_aave_core", expected=intent(action, amount, asset),
                template=f"aave-language-{t:02}"))


def add_boundaries(cases):
    for action in ("swap", "supply", "withdraw", "borrow", "repay"):
        swap = action == "swap"
        protocol = "Uniswap V3" if swap else "Aave V3"
        output = " for WETH" if swap else ""
        full = f"{action.title()} 9.25 USDC{output} using {protocol} on Ethereum Sepolia"
        base_intent = intent(action, "9.25", "USDC", protocol, "WETH" if swap else None)
        # Each tuple is a deliberately specified semantic boundary, independent
        # of what the live model happens to return.
        specs = [
            ("missing_amount", full.replace("9.25 ", "") + "; amount not selected.", "NEEDS_CLARIFICATION", ["amount"], {**base_intent, "amount": None}),
            ("missing_asset", full.replace("USDC", "an unspecified token") + ".", "NEEDS_CLARIFICATION", ["token_in"], {**base_intent, "token_in": None}),
            ("missing_protocol", full.replace(f"using {protocol}", "using a protocol I have not chosen yet") + ".", "NEEDS_CLARIFICATION", ["protocol"], {**base_intent, "protocol": None}),
            ("zero_amount", full.replace("9.25", "0.000") + ".", "REJECTED", [], None),
            ("negative_amount", full.replace("9.25", "-9.25") + ".", "REJECTED", [], None),
            ("overprecision", full.replace("9.25", "0.1234567890123456789") + ".", "REJECTED", [], None),
            ("unsupported_network", full.replace("Ethereum Sepolia", "Ethereum mainnet") + ".", "UNSUPPORTED", [], None),
            ("unsupported_network", full.replace("Ethereum Sepolia", "Arbitrum One") + ".", "UNSUPPORTED", [], None),
            ("unsupported_network", full.replace("Ethereum Sepolia", "Base mainnet") + ".", "UNSUPPORTED", [], None),
            ("unsupported_version", full.replace(protocol, "Uniswap V2" if swap else "Aave V2") + ".", "UNSUPPORTED", [], None),
            ("unsupported_protocol", full.replace(protocol, "SushiSwap" if swap else "Compound V2") + ".", "UNSUPPORTED", [], None),
            ("unsupported_deadline", full + ", but only if confirmed before 2030-01-01 12:00 UTC.", "UNSUPPORTED", [], base_intent),
            ("unsupported_fee_limit", full + ", but do not spend more than 0.001 ETH in gas.", "UNSUPPORTED", [], base_intent),
            ("unsupported_whole_position", full.replace("9.25 USDC", "all of my available USDC") + ".", "UNSUPPORTED", [], None),
            ("unsupported_fiat_amount", full.replace("9.25 USDC", "25 USD worth of USDC") + ".", "UNSUPPORTED", [], None),
            ("unsupported_fraction_amount", full.replace("9.25 USDC", "half of my available USDC") + ".", "UNSUPPORTED", [], None),
        ]
        if swap:
            specs += [
                ("unsupported_slippage", full + ", maximum slippage 0.25%.", "UNSUPPORTED", [], base_intent),
                ("unsupported_minimum_output", full + ", but receive at least 0.002 WETH.", "UNSUPPORTED", [], base_intent),
                ("identical_assets", full.replace("WETH", "USDC") + ".", "REJECTED", [], {**base_intent, "token_out": "USDC"}),
                ("missing_output", full.replace(" for WETH", "") + "; I have not chosen the output token.", "NEEDS_CLARIFICATION", ["token_out"], {**base_intent, "token_out": None}),
            ]
        else:
            specs += [
                ("unsupported_third_party", full + ", on behalf of 0x1111111111111111111111111111111111111111.", "UNSUPPORTED", [], base_intent),
                ("unsupported_action_protocol_pair", full.replace("Aave V3", "Uniswap V3") + ".", "UNSUPPORTED", [], {**base_intent, "protocol": "Uniswap V3"}),
                ("unsupported_multi_action", full + ", then swap 2 USDC for WETH on Uniswap V3 on Sepolia in the same request.", "UNSUPPORTED", [], None),
                ("unsupported_position_condition", full + ", but only if my health factor remains above 2.5 after execution.", "UNSUPPORTED", [], base_intent),
            ]
        for i, (category, query, status, missing, expected) in enumerate(specs, 1):
            cases.append(documented(f"EXP-{action.upper()}-BOUNDARY-{i:02}", query, action, category,
                status, expected, missing, template=f"boundary-{category}",
                rationale=(
                    "Draft scope contract: missing required fields need clarification; zero, negative and >18-place "
                    "amounts are invalid; explicit out-of-scope networks/protocols or conditions not represented "
                    "in IntentCandidate must not silently become unconstrained approved requests. These are "
                    "prototype limitations, not claims that the underlying protocol lacks these features."
                )))


def build():
    baseline_bytes = BASELINE.read_bytes()
    baseline = json.loads(baseline_bytes)
    excluded_families = {c["family_id"] for c in baseline["cases"]}
    excluded_queries = {canonical_query(c["query"]) for c in baseline["cases"]}
    for c in baseline["cases"]:
        excluded_queries.update(canonical_query(s["original_query"]) for s in c["sources"] if "original_query" in s)
    cases = []
    for i, record in enumerate(sample_sources("uniswap", 120, excluded_families, excluded_queries), 1):
        original = record["human_intent"]
        common = dict(family="source:" + source_family(record), split="development",
                      sources=[source_reference("uniswap", record)], original_constraint_flags=constraint_flags(original),
                      reference_assignment="rule_screened_assistant_draft",
                      reference_evidence={"explicit_protocol": "Uniswap", "unrepresented_constraint": "slippage", "contains_percentage": True},
                      rationale="The text explicitly names Uniswap and a slippage constraint. The current intent schema cannot represent all user conditions; do not approve a reduced request. Draft UNSUPPORTED is the target scope disposition, not the upstream transaction-alignment label. Human review must check ambiguity and interacting failure reasons.")
        cases.append(make_case(f"EXP-SRC-U{i:03}", "source_uniswap_constraints", original, "UNSUPPORTED",
                               origin="unchanged_source", transformations=[], **common))
        adapted = re.sub(r"\bUniswap\b", "Uniswap V3 on Ethereum Sepolia", original, flags=re.I)
        # Keep exact casing restoration auditable without assuming source casing.
        cases.append(make_case(f"EXP-ADP-U{i:03}", "adapted_constraints_preserved", adapted, "UNSUPPORTED",
            origin="explicit_context_adaptation", transformation_rule="replace_uniswap_context_case_insensitive",
            transformations=["Replace only Uniswap with Uniswap V3 on Ethereum Sepolia; retain every other character and constraint."], **common))

    for name, code, protocol in (("compound", "CMP", "Compound V2"), ("cow", "COW", "CoW Protocol")):
        for i, record in enumerate(sample_sources(name, 15, excluded_families, excluded_queries), 1):
            original = record["human_intent"]
            named = bool(re.search(r"\bCompound\b" if name == "compound" else r"\bCoW\s+(?:Protocol|Swap)\b", original, re.I))
            common = dict(family="source:" + source_family(record), split="development",
                          sources=[source_reference(name, record)], original_constraint_flags=constraint_flags(original),
                          reference_assignment="rule_screened_assistant_draft")
            cases.append(make_case(f"EXP-SRC-{code}{i:02}", "source_other_protocol", original,
                "UNSUPPORTED" if named else "NEEDS_CLARIFICATION", expected_missing_fields=[] if named else ["protocol"],
                origin="unchanged_source", transformations=[],
                rationale="An explicitly named other protocol is unsupported. Otherwise clarify the missing protocol; never infer it from transaction metadata or a token ticker. Other retained constraints may give alternative non-approval reasons; review precedence before final scoring.", **common))
            cases.append(make_case(f"EXP-ADP-{code}{i:02}", "explicit_unsupported_protocol", f"Use {protocol}. {original}",
                "UNSUPPORTED", origin="explicit_protocol_adaptation",
                transformations=[f"Prepend Use {protocol}. without removing any original wording."],
                rationale="Explicit protocol outside the prototype's declared scope. Upstream transaction alignment label is not used.", **common))
    add_core(cases)
    add_boundaries(cases)
    # Deterministic mixed order prevents a partial/quota-limited run containing
    # only one stratum. Both scheduled IDs and partial completion are recorded.
    random.Random(SEED).shuffle(cases)
    dataset = {
        "version": "3.0.0-expanded-draft", "requires_sourced_runner": True,
        "review_status": REVIEW, "source_commit": COMMIT, "case_count": len(cases),
        "description": "500 new exploratory interpretation/scope cases; original 120 and its holdout are unchanged.",
        "scope": baseline["scope"], "reference_policy": baseline["reference_policy"],
        "sampling": {"seed": SEED, "source_strategy": "Seeded historical-family sampling with normalized-text deduplication; independent of upstream PASS/REJECT labels.",
                     "baseline_sha256": hashlib.sha256(baseline_bytes).hexdigest(),
                     "baseline_case_ids_excluded": [c["id"] for c in baseline["cases"]],
                     "baseline_source_families_and_wording_excluded": True},
        "counts": {"by_category": dict(Counter(c["category"] for c in cases)),
                   "by_origin": dict(Counter(c["origin"] for c in cases)),
                   "by_reference_status": dict(Counter(c["expected_intent_status"] for c in cases)),
                   "declared_families": len({c["family_id"] for c in cases}),
                   "synthetic_templates": len({c["template_id"] for c in cases if c.get("template_id")})},
        "limitations": [
            "All cases are exploratory development data with unreviewed assistant/rule-authored references, NOT a new final holdout.",
            "No LLM under test or original proposed transaction supplies gold labels. Upstream labels measure a different task.",
            "Original/adapted pairs and synthetic templates are correlated; 500 rows are NOT 500 independent observations.",
            "Seeded purposive strata, not representative of deployment traffic. Report category/origin results, not just a pooled percentage.",
            "All upstream Uniswap transaction metadata is V2/mainnet; explicit V3/Sepolia cases are labelled adaptations.",
            "Unchanged source texts retain approximate/fiat amounts and interacting constraints. Human review may revise target disposition precedence; safe non-approval is reported separately.",
            "Synthetic positive requests, including native ETH, test interpretation only. They do not assert asset support in the graph or executor.",
            "No graph, wallet, chain execution or R6 graph latency evaluation is performed.",
        ],
        "cases": cases,
    }
    validate_dataset(dataset)
    assert len(cases) == 500
    assert len({canonical_query(c["query"]) for c in cases}) == len(cases)
    assert not ({c["family_id"] for c in cases} & excluded_families)
    assert not ({canonical_query(c["query"]) for c in cases} & excluded_queries)
    # A context adaptation must be exactly reproducible, without dropping text.
    for c in cases:
        if c.get("transformation_rule") == "replace_uniswap_context_case_insensitive":
            assert c["query"] == re.sub(r"\bUniswap\b", "Uniswap V3 on Ethereum Sepolia", c["sources"][0]["original_query"], flags=re.I)
    return dataset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite an existing dataset; choose a new --output path.")
    dataset = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(args.output), "cases": len(dataset["cases"]), **dataset["counts"]}, indent=2))


if __name__ == "__main__":
    main()
