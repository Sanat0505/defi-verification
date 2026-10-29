"""python -m knowledge: build, publish and inspect the isolated catalog."""

import argparse
import json
from pathlib import Path

from db.connection import close_driver, get_driver
from knowledge.database import database_name, entries, fingerprint, provision, publish, summary
from knowledge.sources import refresh_sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["refresh-sources", "build", "sync", "summary", "operations", "functions", "contracts", "gaps"])
    parser.add_argument("--database", default=None)
    parser.add_argument("--rpc", action="store_true", help="Observe configured networks at pinned blocks using read-only RPC calls")
    parser.add_argument("--pool-limit", type=int, default=80, help="Maximum token-pair/fee lookups per network, not a complete pool census")
    parser.add_argument("--module", choices=["aave-v3", "aave-umbrella", "uniswap-v3"])
    parser.add_argument("--name", help="Case-insensitive operation or function name filter")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--output", type=Path, help="Write the JSON result to a file")
    args = parser.parse_args()
    database = database_name(args.database)
    try:
        if args.command == "refresh-sources":
            result = refresh_sources()
        elif args.command in {"build", "sync"}:
            from knowledge.model import build_graph
            from knowledge.observations import add_observations
            graph = add_observations(build_graph(), enabled=args.rpc, pool_limit=args.pool_limit)
            result = graph.report()
            if args.command == "sync":
                driver = get_driver()
                # Hash all existing non-knowledge graphs, not only the current default.
                with driver.session(database="system") as session:
                    preserved = [r["name"] for r in session.run("SHOW DATABASES YIELD name, currentStatus RETURN name, currentStatus")
                                 if r["name"] != "system" and not r["name"].startswith("defi-knowledge-") and r["currentStatus"] == "online"]
                before = {name: fingerprint(name, driver) for name in preserved}
                provision(driver, database)
                result.update(publish(graph, driver, database))
                after = {name: fingerprint(name, driver) for name in preserved}
                result["preservation_check"] = {"unchanged": before == after, "before": before, "after": after}
                if before != after:
                    raise RuntimeError("An existing database changed during the import window; investigate concurrent writers")
        elif args.command == "summary":
            result = summary(database=database)
        else:
            kind = {"operations": "Operation", "functions": "Function", "contracts": "Contract", "gaps": "CoverageGap"}[args.command]
            result = entries(kind, module=args.module, name=args.name, limit=args.limit, offset=args.offset, database=database)
        text = json.dumps(result, indent=2, ensure_ascii=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + "\n", encoding="utf-8")
            compact = {k: v for k, v in result.items() if k not in {"gaps", "sources"}} if isinstance(result, dict) else {"entries": len(result)}
            print(json.dumps(compact, indent=2))
            print(f"Saved {args.output}")
        else:
            print(text)
    finally:
        close_driver()


if __name__ == "__main__":
    main()
