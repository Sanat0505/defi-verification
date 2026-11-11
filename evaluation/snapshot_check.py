"""Read-only graph prerequisite check; never synchronizes or labels test cases."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inspect_snapshot():
    from source.core.config import settings
    from source.db.connection import close_driver, get_driver

    now = datetime.now(timezone.utc)
    report = {
        "checked_at_utc": now.isoformat(), "read_only": True,
        "chain_id": settings.supported_chain_id,
        "knowledge_max_age_hours": settings.knowledge_max_age_hours,
        "graph_cases_scored": 0, "transactions_broadcast": 0,
        "note": "Freshness is a prerequisite, not proof of graph relationship correctness. No labels are derived from the production verifier.",
        "deployments": [],
    }
    try:
        rows, _, _ = get_driver().execute_query(
            "MATCH (f:ProtocolFamily)-[:HAS_DEPLOYMENT]->(d:ProtocolDeployment {chain_id:$chain_id}) "
            "RETURN f.name AS protocol, d.key AS deployment, d.verified AS verified, "
            "d.last_successful_sync_at AS last_successful_sync_at, d.last_synced_at AS last_synced_at, "
            "d.last_sync_status AS last_sync_status, d.asset_coverage AS asset_coverage, "
            "d.pool_discovery_complete AS pool_discovery_complete, d.source_url AS source_url "
            "ORDER BY protocol",
            chain_id=settings.supported_chain_id, routing_="r",
        )
        for row in rows:
            value = dict(row)
            raw = value.get("last_successful_sync_at") or value.get("last_synced_at")
            age = None
            if raw:
                try:
                    stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                    stamp = stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
                    age = (now - stamp).total_seconds() / 3600
                except ValueError:
                    pass
            value["age_hours"] = round(age, 3) if age is not None else None
            value["fresh"] = age is not None and 0 <= age <= settings.knowledge_max_age_hours
            report["deployments"].append(value)
        available = {d["protocol"] for d in report["deployments"] if d["fresh"] and d["verified"]}
        report["freshness_prerequisite_met"] = {"Uniswap V3", "Aave V3"}.issubset(available)
        report["status"] = "freshness_ready_relationship_review_still_required" if report["freshness_prerequisite_met"] else "blocked_stale_missing_or_unverified_deployment"
    except Exception as exc:
        report["status"] = "blocked_database_unavailable"
        report["error_type"] = type(exc).__name__
        report["freshness_prerequisite_met"] = False
    finally:
        close_driver()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / '.cache/evaluation-runs/graph_snapshot_preflight.json')
    args = parser.parse_args(argv)
    report = inspect_snapshot()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["freshness_prerequisite_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
