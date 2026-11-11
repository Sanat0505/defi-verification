"""Capture read-only inspection evidence in a NEW output directory.

Run from the repository root; never use this to overwrite retained evidence.
No LLM calls, synchronization, database writes, or wallet execution are performed.
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from dotenv import dotenv_values, load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def selected_graph(session, query):
    nodes, edges = {}, {}
    for record in session.run(query):
        for path in record.values():
            for node in path.nodes:
                nodes[node.element_id] = {
                    "id": node.element_id, "labels": sorted(node.labels),
                    "properties": dict(node),
                }
            for edge in path.relationships:
                edges[edge.element_id] = {
                    "id": edge.element_id, "type": edge.type,
                    "start": edge.start_node.element_id,
                    "end": edge.end_node.element_id,
                    "properties": dict(edge),
                }
    return {"nodes": sorted(nodes.values(), key=lambda x: x["id"]),
            "relationships": sorted(edges.values(), key=lambda x: x["id"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database", default="neo4j")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output directory; saved evidence is never overwritten.")
    load_dotenv(ROOT / ".env")
    logging.disable(logging.CRITICAL)
    with GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        connection_timeout=5, max_transaction_retry_time=0,
    ) as driver:
        with driver.session(database=args.database, default_access_mode="READ") as session:
            # Refuse to package graph properties containing configured secrets.
            secrets = {k: v for k, v in dotenv_values(ROOT / ".env").items()
                       if v and len(v) >= 8 and any(s in k.upper()
                           for s in ("PASSWORD", "PRIVATE_KEY", "API_KEY", "SECRET", "RPC"))}
            for query in ("MATCH (n) RETURN properties(n) AS p",
                          "MATCH ()-[r]->() RETURN properties(r) AS p"):
                for record in session.run(query):
                    value = json.dumps(record["p"], default=str)
                    if any(secret in value for secret in secrets.values()):
                        raise RuntimeError("A configured secret appears in graph properties; do not distribute this database.")
            overview = selected_graph(session, (HERE / "queries/01_overview.cypher").read_text())
            supply = selected_graph(session, (HERE / "queries/02_aave_supply.cypher").read_text())
            if not overview["relationships"] or not supply["relationships"]:
                raise RuntimeError("Expected presentation paths are missing; no evidence written.")
            counts = {
                "nodes": session.run("MATCH (n) RETURN count(n) AS n").single()["n"],
                "relationships": session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"],
            }
            tables = {}
            for key, filename in (("node_counts", "03_node_counts.cypher"),
                                  ("relationship_counts", "04_relationship_counts.cypher"),
                                  ("knowledge_state", "05_knowledge_state.cypher")):
                tables[key] = session.run((HERE / "queries" / filename).read_text()).data()
            components = session.run("CALL dbms.components() YIELD name, versions, edition RETURN name,versions,edition").data()
            constraints = session.run("SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties RETURN name,type,labelsOrTypes,properties ORDER BY name").data()
        from source.db import verifier
        # Only replace the connection factory: the verifier and freshness policy
        # are unchanged, and the selected database is explicit.
        with patch.object(verifier, "get_session", lambda: driver.session(database=args.database, default_access_mode="READ")):
            verification = verifier.verify_intent("Aave V3", "USDC", None, "supply", 11155111)
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "overview.json", overview)
    write_json(args.output / "aave_supply.json", supply)
    write_json(args.output / "verification_example.json", {
        "illustrative_request": "Supply 10 USDC to Aave V3 on Ethereum Sepolia.",
        "stage": "relationship verifier called directly with a reference intent",
        "llm_called": False, "wallet_called": False,
        "freshness_policy_modified": False,
        "input": {"protocol": "Aave V3", "token_in": "USDC", "token_out": None,
                  "action": "supply", "chain_id": 11155111},
        "note": "Amount is not an argument to the relationship verifier. This is not a full-pipeline execution.",
        "result": verification,
    })
    for name, rows in tables.items():
        write_json(args.output / (name + ".json"), rows)
        if rows:
            with (args.output / (name + ".csv")).open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    write_json(args.output / "inventory.json", {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_kind": "submission inspection; not asserted to be the historical evaluation state",
        "database": args.database, "components": components, "counts": counts,
        "count_scope": "whole user database, including presentation and fixture metadata",
        "constraints": constraints,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "query_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((HERE / "queries").glob("*.cypher"))},
        "read_only": True, "configured_secret_property_scan": "passed",
    })
    print(json.dumps({"counts": counts, "overview_nodes": len(overview["nodes"]),
                      "supply_nodes": len(supply["nodes"]), "verification_decision": verification["decision"]}))


if __name__ == "__main__":
    main()
