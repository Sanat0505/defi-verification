"""Build an auditable, assistant-authored evaluation draft from pinned sources.

This is not a faithful V3 subset of INTENT-TX-18K: the pinned Uniswap file is
V2/mainnet only. Originals, constraint-preserving adaptations, and deliberately
simplified synthetic controls are separate strata. No production verifier or
model output is used to assign reference labels. Researcher review is required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from evaluation.source_import import CACHE, COMMIT, FILES, ROOT, constraint_flags, load_source, source_family

UNISWAP_DOC = "https://developers.uniswap.org/docs/protocols/v3/guides/swapping/single-hop-swapping"
AAVE_DOC = "https://aave.com/docs/aave-v3/smart-contracts/pool"
OUTPUT = ROOT / "evaluation" / "datasets" / "sourced_cases.json"
REVIEW = "assistant_draft_pending_researcher_review"


def record_id(record):
    return record.get("test_id") or record["sample_id"]


def select_families(records, count):
    families = {}
    for record in records:
        families.setdefault(source_family(record), []).append(record)
    selected = []
    for index, variants in enumerate(list(families.values())[:count]):
        # Include both upstream labels, solely as a sampling choice, not gold.
        preferred = "PASS" if index % 2 == 0 else "REJECT"
        selected.append(next((r for r in variants if r.get("label") == preferred), variants[0]))
    return selected


def source_reference(name, record):
    path = FILES[name]
    return {
        "source_id": f"intent_tx_18k_{name}",
        "url": f"https://github.com/duanyiyao/intent-tx-18k/blob/{COMMIT}/{path}",
        "commit": COMMIT,
        "record_id": record_id(record),
        "record_sha256": hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "original_query": record["human_intent"],
        "upstream_label_not_gold": record.get("label"),
        "upstream_reason_not_gold": record.get("reason"),
        "transaction_protocol_context_only": record.get("proposed_tx", {}).get("protocol"),
        "transaction_chain_context_only": record.get("proposed_tx", {}).get("chain_id"),
    }


def intent(action, amount, asset="USDT", protocol="Aave V3", output=None):
    return {
        "action": action, "protocol": protocol, "amount": amount,
        "token_in": asset, "token_out": output,
        "chain": "Ethereum Sepolia", "chain_id": 11155111,
    }


def make_case(case_id, category, query, status, family, split="test", expected=None,
              rationale="", **extra):
    return {
        "id": case_id, "category": category, "query": query,
        "family_id": family, "split": split,
        "expected_intent_status": status,
        "expected_intent": expected,
        "expected_graph_outcome": None,
        "reference_rationale": rationale,
        "review_status": REVIEW,
        "authorship": "assistant-curated; not independently human-reviewed",
        **extra,
    }


def build():
    cases = []
    for i, source in enumerate(select_families(load_source("uniswap"), 12), 1):
        family = "source:" + source_family(source)
        split = "development" if i <= 3 else "test"
        ref = source_reference("uniswap", source)
        original = source["human_intent"]
        flags = constraint_flags(original)
        common = dict(family=family, split=split, sources=[ref], original_constraint_flags=flags)
        rationale = (
            "User specifies constraints/fiat-denominated quantities not representable by the current intent schema. "
            "Reference disposition is UNSUPPORTED, not an approval of a reduced swap. "
            "No version/network is inferred from proposed_tx; upstream alignment label is not reused."
        )
        cases.append(make_case(f"SRC-U{i:02}", "source_uniswap_constraints", original,
                               "UNSUPPORTED", rationale=rationale,
                               origin="unchanged_source", transformations=[], **common))
        # Only the named protocol context changes. Every constraint remains.
        adapted = re.sub(r"\bUniswap\b", "Uniswap V3 on Ethereum Sepolia", original)
        if adapted == original:
            adapted = "Use Uniswap V3 on Ethereum Sepolia. " + original
        cases.append(make_case(f"ADP-U{i:02}", "adapted_constraints_preserved", adapted,
                               "UNSUPPORTED", rationale=rationale,
                               origin="constraint_preserving_adaptation",
                               transformations=["Explicitly set Uniswap V3 and Ethereum Sepolia; retain the original amount expression, assets and all constraints."], **common))
        # Not a paraphrase of the original: an explicitly simplified control.
        amount = ["0.25", "1.5", "3", "0.75", "2.25", "4", "0.05", "7.5", "12", "0.125", "6", "15"][i-1]
        token_in, token_out = ("USDC", "WETH") if i % 2 else ("WETH", "USDC")
        expected = intent("swap", amount, token_in, "Uniswap V3", token_out)
        controls = [
            f"Swap {amount} {token_in} for {token_out} using Uniswap V3 on Ethereum Sepolia.",
            f"On Ethereum Sepolia, please exchange {amount} {token_in} into {token_out} through Uniswap V3.",
        ]
        for variant, query in enumerate(controls, 1):
            cases.append(make_case(f"CTL-U{i:02}-{variant}", "synthetic_uniswap_core", query,
                "APPROVED", expected=expected, group_id=f"core-U{i:02}",
                rationale="A complete exact-input, single-action semantic request. APPROVED here means ready for graph verification, not graph approval or execution success.",
                origin="source_inspired_simplified_control",
                transformations=[
                    "Create a NEW scenario, not a semantically equivalent source paraphrase.",
                    f"Replace source assets with {token_in}/{token_out} for the prototype control scenario; native ETH is NOT normalized to WETH.",
                    f"Replace the fiat/approximate quantity with an exact {amount} {token_in}; this is NOT a currency conversion.",
                    "Omit the original slippage, minimum-output, deadline and other additional conditions ONLY in this labelled simplified control. The paired SRC/ADP cases preserve them.",
                    "Explicitly set Uniswap V3 and Ethereum Sepolia.",
                ], conditional_graph_reference={
                    "outcome": "APPROVED",
                    "preconditions": "Independently review a fresh admitted Sepolia snapshot containing the required router, quoter, function and active token-pair pool relationships before scoring graph results.",
                }, **common))

    for name, abbreviation, protocol in [("compound", "CMP", "Compound V2"), ("cow", "COW", "CoW Protocol")]:
        for i, source in enumerate(select_families(load_source(name), 3), 1):
            original = source["human_intent"]
            # A token named COW is not evidence that CoW Protocol was requested.
            explicit = bool(re.search(r"\bCompound\b" if name == "compound" else r"\bCoW\s+(?:Protocol|Swap)\b", original, re.I))
            ref = source_reference(name, source)
            common = dict(family="source:" + source_family(source),
                          split="development" if i == 1 else "test", sources=[ref],
                          original_constraint_flags=constraint_flags(original))
            cases.append(make_case(f"SRC-{abbreviation}{i:02}", "source_other_protocol", original,
                "UNSUPPORTED" if explicit else "NEEDS_CLARIFICATION",
                rationale=("Explicit protocol is outside the declared prototype scope." if explicit else
                           "Protocol is absent from the query; it must not be inferred from the source filename, transaction, or a token ticker. Clarify protocol before proceeding. Additional unsupported conditions are retained."),
                expected_missing_fields=[] if explicit else ["protocol"],
                origin="unchanged_source", transformations=[], **common))
            cases.append(make_case(f"ADP-{abbreviation}{i:02}", "explicit_unsupported_protocol",
                f"Use {protocol}. {original}", "UNSUPPORTED",
                rationale="The newly explicit protocol is outside the declared scope; original constraints are unchanged.",
                origin="explicit_protocol_adaptation",
                transformations=[f"Prepend an explicit {protocol} instruction; no original wording or constraints removed."], **common))

    for action in ("supply", "withdraw", "borrow", "repay"):
        for j, (amount, asset) in enumerate((("1.25", "USDT"), ("2.5", "USDC"), ("0.025", "WETH"))):
            family = f"aave:{action}:{asset}:{amount}"
            expected = intent(action, amount, asset)
            variants = {
                "supply": [f"Supply {amount} {asset} to Aave V3 on Ethereum Sepolia.", f"On Ethereum Sepolia, deposit {amount} {asset} into Aave V3."],
                "withdraw": [f"Withdraw {amount} {asset} from Aave V3 on Ethereum Sepolia.", f"Please withdraw {amount} {asset} from my Aave V3 supply position on Ethereum Sepolia."],
                "borrow": [f"Borrow {amount} {asset} from Aave V3 on Ethereum Sepolia.", f"On Ethereum Sepolia, I would like to borrow {amount} {asset} using Aave V3."],
                "repay": [f"Repay {amount} {asset} on Aave V3 on Ethereum Sepolia.", f"Use {amount} {asset} to repay my Aave V3 debt on Ethereum Sepolia."],
            }[action]
            for k, query in enumerate(variants, 1):
                cases.append(make_case(f"AAVE-{action.upper()}-{j+1}-{k}", "synthetic_aave_core", query,
                    "APPROVED", family, split="development" if j == 0 else "test", expected=expected,
                    rationale="The documented Pool operation defines the action. This is a semantic extraction reference, not proof of reserve support, balances, debt, collateral or execution feasibility.",
                    origin="documentation_based_synthetic", group_id=family,
                    sources=[{"source_id": "aave_pool_docs", "url": AAVE_DOC + "#" + action}],
                    conditional_graph_reference={"outcome": "APPROVED", "preconditions": "Independently review current deployment/function/reserve membership for this asset/action before scoring graph outcomes."}))
        boundary_specs = [
            ("missing_amount", f"{action.title()} USDT using Aave V3 on Ethereum Sepolia.", "NEEDS_CLARIFICATION", ["amount"], {"action": action, "protocol": "Aave V3", "token_in": "USDT", "amount": None, "chain": "Ethereum Sepolia", "chain_id": 11155111}),
            ("zero_amount", f"{action.title()} 0 USDT using Aave V3 on Ethereum Sepolia.", "REJECTED", [], None),
            ("missing_asset", f"{action.title()} 3 tokens using Aave V3 on Ethereum Sepolia; I have not selected the token yet.", "NEEDS_CLARIFICATION", ["token_in"], {"action": action, "protocol": "Aave V3", "token_in": None, "amount": "3", "chain": "Ethereum Sepolia", "chain_id": 11155111}),
            ("unsupported_network", f"{action.title()} 4 USDT using Aave V3 on Ethereum mainnet.", "UNSUPPORTED", [], None),
        ]
        for j, (category, query, status, missing, expected) in enumerate(boundary_specs):
            cases.append(make_case(f"AAVE-{action.upper()}-B{j+1}", category, query, status,
                f"aave-boundary:{action}:{category}", split="development" if j == 0 else "test",
                expected=expected, expected_missing_fields=missing,
                rationale="Independently specified input-validation/scope boundary: missing values require clarification, zero is invalid, and mainnet is not the configured network.",
                origin="documentation_based_synthetic", sources=[{"source_id": "aave_pool_docs", "url": AAVE_DOC + "#" + action}]))
    for i, query in enumerate([
        "Supply 5 USDT to Aave V3 on Ethereum Sepolia on behalf of 0x1111111111111111111111111111111111111111.",
        "Withdraw all of my USDT from Aave V3 on Ethereum Sepolia.",
        "Borrow 5 USDT from Aave V3 on Ethereum Sepolia using a fixed interest rate.",
        "Repay my entire USDT debt on Aave V3 on Ethereum Sepolia.",
    ], 1):
        cases.append(make_case(f"AAVE-CONSTRAINT-{i}", "unsupported_aave_constraint", query,
            "UNSUPPORTED", f"aave-constraint:{i}",
            rationale="Custom beneficiary, whole-position quantity, or non-variable interest mode cannot be represented by the current semantic intent schema. Do not silently substitute a supported operation.",
            origin="documentation_based_synthetic", sources=[{"source_id": "aave_pool_docs", "url": AAVE_DOC}]))

    edge_specs = [
        ("Swap 2 USDC for WETH using Uniswap V2 on Ethereum Sepolia.", "UNSUPPORTED", "unsupported_version", None),
        ("Swap 2 USDC for WETH using Uniswap V4 on Ethereum Sepolia.", "UNSUPPORTED", "unsupported_version", None),
        ("Swap 2 USDC for WETH using Uniswap V3 on Ethereum mainnet.", "UNSUPPORTED", "unsupported_network", None),
        ("Swap 2 USDC for WETH using Uniswap V3 on Arbitrum.", "UNSUPPORTED", "unsupported_network", None),
        ("Swap 2 USDC for WETH using Uniswap V3 on Base.", "UNSUPPORTED", "unsupported_network", None),
        ("Swap 2 USDC for WETH using Uniswap V3 on Polygon.", "UNSUPPORTED", "unsupported_network", None),
        ("Swap USDC for WETH using Uniswap V3 on Ethereum Sepolia.", "NEEDS_CLARIFICATION", "missing_amount", intent("swap", None, "USDC", "Uniswap V3", "WETH")),
        ("Swap 2 USDC using Uniswap V3 on Ethereum Sepolia.", "NEEDS_CLARIFICATION", "missing_output", intent("swap", "2", "USDC", "Uniswap V3", None)),
        ("Swap 2 USDC for WETH on Ethereum Sepolia; I have not selected a protocol.", "NEEDS_CLARIFICATION", "missing_protocol", intent("swap", "2", "USDC", None, "WETH")),
        ("Use Uniswap V3 on Ethereum Sepolia; I have not decided what operation to perform.", "NEEDS_CLARIFICATION", "missing_action", {"action": None, "protocol": "Uniswap V3"}),
        ("Swap 0 USDC for WETH using Uniswap V3 on Ethereum Sepolia.", "REJECTED", "zero_amount", None),
        ("Swap -2 USDC for WETH using Uniswap V3 on Ethereum Sepolia.", "REJECTED", "negative_amount", None),
        ("Swap 2 USDC for USDC using Uniswap V3 on Ethereum Sepolia.", "REJECTED", "identical_assets", intent("swap", "2", "USDC", "Uniswap V3", "USDC")),
        ("Swap 2 WETH for WETH using Uniswap V3 on Ethereum Sepolia.", "REJECTED", "identical_assets", intent("swap", "2", "WETH", "Uniswap V3", "WETH")),
        ("Swap 2 USDC for WETH using Uniswap V3 on Ethereum Sepolia, with at most 0.3% slippage.", "UNSUPPORTED", "unsupported_slippage", intent("swap", "2", "USDC", "Uniswap V3", "WETH")),
        ("Swap 2 USDC for WETH using Uniswap V3 on Ethereum Sepolia and send the output to 0x1111111111111111111111111111111111111111.", "UNSUPPORTED", "unsupported_recipient", intent("swap", "2", "USDC", "Uniswap V3", "WETH")),
    ]
    for i, (query, status, category, expected) in enumerate(edge_specs, 1):
        cases.append(make_case(f"UNI-BOUNDARY-{i:02}", category, query, status,
            f"uniswap-boundary:{i}", split="development" if i in {1, 15} else "test", expected=expected,
            rationale="Scope/validation boundary specified independently of model output. Constraint cases must not be approved merely because their basic fields are extracted correctly.",
            origin="documentation_based_synthetic", sources=[{"source_id": "uniswap_swap_docs", "url": UNISWAP_DOC}]))

    dataset = {
        "version": "2.0.0-draft", "requires_sourced_runner": True, "source_commit": COMMIT,
        "review_status": REVIEW, "case_count": len(cases),
        "description": "Source-traceable query evaluation draft; not the original Arbiter benchmark and not a verified V3 subset.",
        "scope": {"chain_id": 11155111, "network": "Ethereum Sepolia", "protocols": ["Uniswap V3", "Aave V3"]},
        "source_manifest": "evaluation/sources/intent_tx_18k_manifest.json",
        "reference_policy": {
            "APPROVED": "In intent mode: complete, in-scope interpretation ready for graph verification, never transaction approval.",
            "UNSUPPORTED": "Explicit out-of-scope protocol/network/feature; unrepresented constraints must not be silently dropped.",
            "NEEDS_CLARIFICATION": "Required semantic information is missing; do not infer it from transaction metadata.",
            "REJECTED": "Invalid stated value or identical swap assets.",
            "graph": "No unconditional graph gold labels are assigned. Conditional graph references require independent snapshot review.",
        },
        "limitations": [
            "Small purposive sample, not a representative or statistically powered sample of the upstream corpus.",
            "All 6000 upstream Uniswap proposed transactions are V2/mainnet at the pinned commit. No source human_intent explicitly mentions V3.",
            "Assistant-authored reference labels require researcher review; no claim of human review or model-unseen data.",
            "The 90-case test split is a proposed holdout. Freeze its reviewed labels before tuning; this build does not send it to any model.",
            "Synthetic controls share templates across splits. The split isolates source ancestry and declared paraphrase families, NOT linguistic templates; do not claim template-disjoint generalization.",
            "Constraint tests measure safe scope handling. They do not establish implementation of those features.",
            "No wallet, receipt, live funding, isolated-graph mutation or R6 experiment is performed by building this dataset.",
        ],
        "cases": cases,
    }
    validate_dataset(dataset)
    return dataset


def validate_dataset(dataset):
    cases = dataset["cases"]
    ids, prompts, family_splits, group_signatures = set(), set(), {}, {}
    for case in cases:
        if case["expected_intent_status"] not in {"APPROVED", "REJECTED", "UNSUPPORTED", "NEEDS_CLARIFICATION"}:
            raise ValueError("Invalid interpretation reference status")
        if case["split"] not in {"development", "test"}:
            raise ValueError("Invalid split")
        if case["id"] in ids or case["query"] in prompts:
            raise ValueError("Duplicate case ID or query")
        ids.add(case["id"]); prompts.add(case["query"])
        if not 0 < len(case["query"]) <= 2000:
            raise ValueError("Query exceeds application input boundary")
        family = case["family_id"]
        if family_splits.setdefault(family, case["split"]) != case["split"]:
            raise ValueError("Source/scenario family leaks across splits")
        if case.get("group_id"):
            signature = json.dumps([case["expected_intent"], case["expected_intent_status"]], sort_keys=True)
            if group_signatures.setdefault(case["group_id"], signature) != signature:
                raise ValueError("A paraphrase group changes the reference semantics")
        if not case["reference_rationale"] or not case["sources"]:
            raise ValueError("Missing annotation rationale or provenance")
        if case["origin"] == "unchanged_source" and case["query"] != case["sources"][0]["original_query"]:
            raise ValueError("An original query was modified")
        if case["origin"] == "constraint_preserving_adaptation":
            recovered = case["query"].replace("Uniswap V3 on Ethereum Sepolia", "Uniswap")
            if recovered != case["sources"][0]["original_query"]:
                raise ValueError("A constraint-preserving adaptation changed more than protocol context")
    return dict(Counter(case["split"] for case in cases))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--review-output", type=Path, default=OUTPUT.with_name("SOURCED_CASE_REVIEW.md"))
    args = parser.parse_args(argv)
    dataset = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    review_lines = ["# Source-derived case review", "",
        "Status: assistant-authored DRAFT; researcher review is pending. Expected statuses below refer to interpretation/scope only, not graph or transaction outcomes.", "",
        "Review the query, rationale, provenance, and transformations in sourced_cases.json. Do not change labels merely to agree with observed outputs. Set a case's review_status to researcher_reviewed only after actually reviewing it. Freeze a versioned copy before the final test run.", "",
        "The test split is ancestry/family-disjoint, not template-disjoint. Similar synthetic sentence templates occur in both splits.", ""]
    for split in ("development", "test"):
        review_lines.extend([f"## {split.title()}", "", "| ID | Origin | Query | Reference status |", "|---|---|---|---|"])
        for case in dataset["cases"]:
            if case["split"] == split:
                query = case["query"].replace("|", "\\|").replace("\n", " ")
                review_lines.append(f"| {case['id']} | {case['origin']} | {query} | {case['expected_intent_status']} |")
        review_lines.append("")
    args.review_output.parent.mkdir(parents=True, exist_ok=True)
    args.review_output.write_text("\n".join(review_lines), encoding="utf-8")
    license_path = ROOT / "evaluation" / "sources" / "INTENT_TX_18K_LICENSE.txt"
    license_path.parent.mkdir(parents=True, exist_ok=True)
    license_path.write_bytes((CACHE / "LICENSE").read_bytes())
    print(json.dumps({"dataset": str(args.output), "cases": len(dataset["cases"]),
                      "splits": validate_dataset(dataset),
                      "categories": dict(Counter(c["category"] for c in dataset["cases"]))}, indent=2))


if __name__ == "__main__":
    main()
