"""Evaluate live graph relationships directly from draft reference intents.

References are constructed from an independently exported adjacency snapshot,
not by asking verify_intent for its own expected answer. This is implementation
conformance to admitted knowledge, not independent validation of source truth.
"""

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from core.config import settings
from db.connection import close_driver
from db.verifier import verify_intent
from evaluation.graph_stage import ROOT, snapshot, write_report


SOURCE_FILES = [ROOT / "evaluation/datasets/expanded_500_cases.json",
                ROOT / "evaluation/datasets/constraint_regression_v1.json"]


def graph_key(intent):
    return (intent["protocol"], intent["action"], intent.get("token_in"),
            intent.get("token_out"), intent.get("chain_id", 11155111))


def build_cases():
    cases = []
    for path in SOURCE_FILES:
        data = json.loads(path.read_bytes())
        for case in data["cases"]:
            if case["expected_intent_status"] == "APPROVED" and case.get("expected_intent"):
                cases.append({"id": case["id"], "query": case["query"],
                              "category": case["category"], "intent": case["expected_intent"],
                              "source_dataset": str(path.relative_to(ROOT)),
                              "review_status": case["review_status"]})
    controls = [
        ("Uniswap V3", "swap", "RUGTOKEN", "WETH", 11155111),
        ("Uniswap V3", "swap", "AAVE", "USDT", 11155111),
        ("Uniswap V3", "swap", "WBTC", "GHO", 11155111),
        ("Uniswap V3", "swap", "USDC", "USDC", 11155111),
        ("Aave V3", "supply", "RUGTOKEN", None, 11155111),
        ("Aave V3", "borrow", "FAKECOIN", None, 11155111),
        ("Aave V3", "supply", "ETH", None, 11155111),
        ("Uniswap V3", "swap", "LINK", "USDT", 11155111),
        ("Uniswap V3", "swap", "USDC", "WETH", 1),
        ("Uniswap V3", "swap", "USDC", "WETH", 84532),
        ("Compound V2", "supply", "USDT", None, 11155111),
        ("Curve", "swap", "USDC", "USDT", 11155111),
        ("Uniswap V3", "borrow", "USDT", None, 11155111),
        ("Aave V3", "swap", "USDT", "WETH", 11155111),
    ]
    for index, (protocol, action, token_in, token_out, chain_id) in enumerate(controls, 1):
        cases.append({"id": f"GRAPH-CONTROL-{index:02}", "query": None,
                      "category": "structured_graph_boundary_control",
                      "intent": {"protocol": protocol, "action": action, "token_in": token_in,
                                 "token_out": token_out, "chain_id": chain_id, "amount": "1"},
                      "source_dataset": "assistant-authored structured graph controls",
                      "review_status": "assistant_draft_pending_researcher_review"})
    return cases


def reference(intent, facts):
    """Apply documented scope/path policy to exported facts, without verifier calls."""
    protocol, action, token_in, token_out, chain_id = graph_key(intent)
    names = {"Uniswap V3": "uniswap-v3:11155111", "Aave V3": "aave-v3:11155111"}
    allowed_actions = {"Uniswap V3": {"swap"}, "Aave V3": {"supply", "withdraw", "borrow", "repay"}}
    if chain_id != 11155111 or protocol not in names or action not in allowed_actions[protocol]:
        return {"decision": "UNSUPPORTED", "rationale": "Explicit graph-boundary scope mismatch."}
    if not token_in or (action == "swap" and not token_out):
        return {"decision": "REJECTED", "rationale": "Missing graph-boundary asset field."}
    key = names[protocol]
    state = next((d for d in facts["preflight"]["deployments"] if d["deployment"] == key), None)
    if not state or not state["fresh"]:
        return {"decision": "INSUFFICIENT_EVIDENCE", "rationale": "Missing or stale snapshot."}
    deployment = next((d for d in facts["deployments"] if d["key"] == key), {})
    contracts = [c for c in facts["contracts"] if c["deployment"] == key and c["verified"]
                 and c["function_verified"] and c["action"] == action]
    executors = [c for c in contracts if c["purpose"] == "execute"
                 and c["role"] == ("swap_router" if action == "swap" else "pool")]
    paths = []
    if deployment.get("verified") and action in deployment.get("actions", []) and executors:
        if action == "swap":
            quoters = [c for c in contracts if c["role"] == "quoter" and c["purpose"] == "preflight"]
            for pool in facts["pools"]:
                if pool["deployment"] != key or not all(pool.get(k) for k in ["active", "verified", "eligible"]) or pool["chain_id"] != chain_id or pool["fee"] is None:
                    continue
                tokens = [t for t in pool["tokens"] if t["verified"] and t["eligible"]
                          and t["chain_id"] == chain_id and t["decimals"] is not None]
                for left in [t for t in tokens if t["symbol"] == token_in]:
                    for right in [t for t in tokens if t["symbol"] == token_out and t["address"] != left["address"]]:
                        for executor in executors:
                            for quoter in quoters:
                                paths.append({"router_address": executor["address"], "quoter_address": quoter["address"],
                                              "pool_address": pool["address"], "pool_fee": pool["fee"],
                                              "token_in_address": left["address"], "token_out_address": right["address"],
                                              "token_in_decimals": left["decimals"], "token_out_decimals": right["decimals"],
                                              "function_signature": executor["signature"], "function_selector": executor["selector"]})
        else:
            for reserve in facts["reserves"]:
                if reserve["deployment"] == key and reserve["symbol"] == token_in and reserve["token_chain_id"] == chain_id and action in reserve["actions"] and all(reserve.get(k) for k in ["link_active", "active", "verified", "token_verified"]):
                    for executor in executors:
                        paths.append({"verified_address": executor["address"], "verified_asset": reserve["address"],
                                      "verified_asset_decimals": reserve["decimals"], "verified_function": executor["signature"],
                                      "verified_selector": executor["selector"]})
    if paths:
        return {"decision": "APPROVED", "paths": paths,
                "rationale": "Active, trusted, action-specific path in the exported fresh snapshot."}
    complete = deployment.get("pool_discovery_complete") is True if action == "swap" else deployment.get("asset_coverage") == "official-address-book-complete"
    return {"decision": "REJECTED" if complete else "INSUFFICIENT_EVIDENCE",
            "rationale": "No admitted path; rejection requires declared complete deployment coverage."}


def evidence_matches(actual, expected, action):
    if expected["decision"] != "APPROVED":
        return actual.get("verified_address") is None
    if action == "swap":
        routes = actual.get("routes") or []
        return bool(routes) and all(any(all(route.get(k) == v for k, v in path.items())
                                       for path in expected["paths"]) for route in routes)
    return any(all(actual.get(k) == v for k, v in path.items()) for path in expected["paths"])


def timing(rows):
    values = sorted(r["wall_latency_ms"] for r in rows)
    return {"requests": len(values), "within_2000_ms": sum(v <= 2000 for v in values),
            "percentage_within_2000_ms": 100 * sum(v <= 2000 for v in values) / len(values),
            "p50_ms": values[math.ceil(len(values) * .5) - 1],
            "p95_ms": values[math.ceil(len(values) * .95) - 1], "max_ms": max(values)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    facts = snapshot()
    snapshot_path = write_report("snapshot", facts)
    if not facts["preflight"]["freshness_prerequisite_met"] or not facts["invariants"]["valid"]:
        print("Fresh graph evaluation blocked by snapshot prerequisites. No relationship cases scored.")
        return 2
    cases = build_cases()
    for case in cases:
        case["expected"] = reference(case["intent"], facts)
    references_path = write_report("graph-references", {"snapshot": str(snapshot_path), "cases": cases,
        "review_status": "assistant_draft_pending_researcher_review", "assigned_before_verifier_execution": True})
    records = []
    try:
        for repeat in range(1, args.repeats + 1):
            for case in cases:
                started = time.perf_counter()
                protocol, action, token_in, token_out, chain = graph_key(case["intent"])
                actual = verify_intent(protocol, token_in, token_out, action, chain)
                elapsed = round((time.perf_counter() - started) * 1000, 3)
                decision_ok = actual["decision"] == case["expected"]["decision"]
                evidence_ok = evidence_matches(actual, case["expected"], action)
                records.append({**case, "run": repeat, "actual": actual, "wall_latency_ms": elapsed,
                                "decision_correct": decision_ok, "evidence_correct": evidence_ok,
                                "passed": decision_ok and evidence_ok,
                                "improper_approval": actual["decision"] == "APPROVED" and case["expected"]["decision"] != "APPROVED"})
            print(f"Completed graph repeat {repeat}: {len(cases)} reference intents; no LLM calls.", flush=True)
    finally:
        close_driver()
    after = snapshot()
    after_path = write_report("snapshot-after", after)
    stable_keys = ["deployments", "contracts", "reserves", "pools"]
    stable = all(facts[key] == after[key] for key in stable_keys)
    primary = [r for r in records if r["run"] == 1]
    unique = {}
    for row in primary:
        unique.setdefault(graph_key(row["intent"]), row)
    metrics = {"reference_cases": len(primary), "unique_graph_inputs": len(unique),
               "executions": len(records), "primary_passed": sum(r["passed"] for r in primary),
               "primary_decisions": dict(Counter(r["actual"]["decision"] for r in primary)),
               "primary_improper_approvals": sum(r["improper_approval"] for r in primary),
               "unique_graph_inputs_passed": sum(r["passed"] for r in unique.values()),
               "snapshot_stable": stable, "graph_timing_all_calls": timing(records),
               "graph_timing_first_per_unique_input": timing(list(unique.values()))}
    report = {"metadata": {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "live_neo4j_reference_intents_no_llm", "llm_calls": 0, "wallet_calls": 0,
        "transaction_broadcast": False, "database_mutation_during_evaluation": False,
        "reference_review": "assistant_draft_pending_researcher_review",
        "reference_basis": "Exported admitted adjacency facts plus documented scope policy, NOT verify_intent output; not independent source-truth validation.",
        "snapshot_before": str(snapshot_path), "snapshot_after": str(after_path), "references": str(references_path),
        "repeats": args.repeats, "knowledge_max_age_hours": settings.knowledge_max_age_hours,
        "source_dataset_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE_FILES},
        "code_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(), ROOT / "db/verifier.py", ROOT / "evaluation/graph_stage.py"]},
        "timing_boundary": "verify_intent wall time only; snapshot audit occurred first; not cold-start, end-to-end or production-load latency.",
        "independence_note": "Amounts, slippage and paraphrases can share the exact same graph input. Repeats and duplicate inputs are not independent samples."},
        "metrics": metrics, "results": records}
    path = write_report("graph-evaluation", report)
    summary = "# Graph-only development evaluation\n\n" + "\n".join([
        f"- Reference cases: {len(primary)}; unique graph inputs: {len(unique)}; executions: {len(records)}.",
        f"- Primary conformance: {metrics['primary_passed']}/{len(primary)}; improper approvals: {metrics['primary_improper_approvals']}.",
        f"- Snapshot stable: {stable}. LLM calls: 0. Wallet calls: 0. Transactions: 0.",
        "- References are assistant-drafted snapshot-conformance labels, not independently reviewed source truth.",
        "- Draft expected intents are used directly, including cases whose earlier model extraction failed.",
        "- Timing measures the graph function after snapshot audit, not the full application or cold start.",
        "", "## Metrics", "", "```json", json.dumps(metrics, indent=2), "```", "", "## Mismatches", "",
        *[f"- {r['id']}: expected {r['expected']['decision']}, actual {r['actual']['decision']}; evidence_match={r['evidence_correct']}" for r in primary if not r["passed"]], ""])
    path.with_suffix(".md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0 if stable and all(r["passed"] for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
