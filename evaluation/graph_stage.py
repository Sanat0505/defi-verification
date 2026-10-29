"""Read-only graph snapshot/evaluation, with a separately explicit Sepolia refresh.

Never calls the LLM, the wallet or transaction submission. Refresh is the only
database-writing mode, and runs only the two selected deployment sync tasks.
"""

import argparse
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from db.connection import close_driver, get_driver
from evaluation.snapshot_check import inspect_snapshot


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '.cache/evaluation-runs/graph'
TARGETS = {"aave-v3:11155111", "uniswap-v3:11155111"}

DEPLOYMENTS = """
MATCH (d:ProtocolDeployment {chain_id:11155111})
RETURN d.key AS key, d.verified AS verified, d.asset_coverage AS asset_coverage,
       d.pool_discovery_complete AS pool_discovery_complete,
       d.factory_scanned_to_block AS factory_scanned_to_block,
       [(d)-[:SUPPORTS_ACTION]->(a:Action)|a.name] AS actions
ORDER BY key
"""
CONTRACTS = """
MATCH (d:ProtocolDeployment {chain_id:11155111})-[r:DEPLOYED_CONTRACT]->(c:Contract)
WHERE r.active=true AND r.role IN ['pool','swap_router','quoter']
OPTIONAL MATCH (c)-[:EXPOSES_FUNCTION]->(f:Function)-[:IMPLEMENTS_ACTION]->(a:Action)
RETURN d.key AS deployment, r.role AS role, c.address AS address,
       c.verified AS verified, f.signature AS signature, f.selector AS selector,
       f.verified AS function_verified, f.purpose AS purpose, a.name AS action
ORDER BY deployment, role, signature
"""
RESERVES = """
MATCH (d:ProtocolDeployment {chain_id:11155111})-[r:HAS_RESERVE]->(x:Reserve)
MATCH (x)-[:UNDERLYING_ASSET]->(t:Token)
RETURN d.key AS deployment, r.active AS link_active, x.active AS active,
       x.verified AS verified, t.symbol AS symbol, t.address AS address,
       t.verified AS token_verified, t.chain_id AS token_chain_id,
       t.decimals AS decimals, [(x)-[:SUPPORTS_ACTION]->(a:Action)|a.name] AS actions
ORDER BY deployment, symbol, address
"""
POOLS = """
MATCH (d:ProtocolDeployment {chain_id:11155111})-[r:HAS_POOL]->(p:Pool)
WHERE r.active=true AND p.verification_eligible=true
MATCH (p)-[:SUPPORTS_TOKEN]->(t:Token)
RETURN d.key AS deployment, p.address AS address, p.fee AS fee,
       p.active AS active, p.verified AS verified, p.chain_id AS chain_id,
       p.verification_eligible AS eligible,
       collect({symbol:t.symbol,address:t.address,decimals:t.decimals,
                verified:t.verified,eligible:t.verification_eligible,chain_id:t.chain_id}) AS tokens
ORDER BY deployment, address
"""


def write_report(kind, payload):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = OUTPUT / f"{kind}-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"JSON: {path}", flush=True)
    return path


def snapshot():
    from db.validate_graph_v2 import validate

    result = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "read_only": True,
              "transaction_broadcast": False, "preflight": inspect_snapshot()}
    try:
        result["invariants"] = validate()
        for key, query in [("deployments", DEPLOYMENTS), ("contracts", CONTRACTS),
                           ("reserves", RESERVES), ("pools", POOLS)]:
            rows, _, _ = get_driver().execute_query(query, routing_="r")
            result[key] = [dict(row) for row in rows]
            for row in result[key]:
                if "actions" in row:
                    row["actions"].sort()
                if "tokens" in row:
                    row["tokens"].sort(key=lambda token: token["address"])
    finally:
        close_driver()
    return result


def refresh():
    from db.sync import build_tasks, run_task

    # Do not call synchronize(): it also performs global cleanup/demo rebuilding.
    # These selected tasks refresh only the authorized Sepolia deployment data.
    tasks = [task for task in build_tasks() if task.deployment_key in TARGETS]
    assert {task.deployment_key for task in tasks} == TARGETS
    logging.disable(logging.CRITICAL)  # Upstream error strings may contain RPC credentials.
    results = []
    try:
        for task in tasks:
            print(f"Refreshing {task.deployment_key} from configured source...", flush=True)
            result = asdict(run_task(task))
            if result.get("error"):
                result["error"] = "Upstream error details omitted to protect configured RPC credentials."
            results.append(result)
            print(f"{task.deployment_key}: {result['status']}", flush=True)
    finally:
        close_driver()
        logging.disable(logging.NOTSET)
    return {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "authorized_deployments": sorted(TARGETS), "transaction_broadcast": False,
            "global_cleanup_or_demo_rebuild": False, "tasks": results,
            "ok": all(item["status"] == "SUCCESS" for item in results)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["audit", "refresh"])
    parser.add_argument("--confirm-sepolia-refresh", action="store_true")
    args = parser.parse_args()
    if args.mode == "refresh":
        if not args.confirm_sepolia_refresh:
            parser.error("Refresh needs explicit authorization and --confirm-sepolia-refresh")
        result = refresh()
        write_report("sepolia-refresh", result)
        return 0 if result["ok"] else 1
    result = snapshot()
    write_report("snapshot", result)
    print(json.dumps({"fresh": result["preflight"]["freshness_prerequisite_met"],
                      "invariants": result["invariants"], "reserves": result["reserves"],
                      "eligible_pools": len(result["pools"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
