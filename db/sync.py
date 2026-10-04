"""Reliable authoritative-knowledge acquisition, admission, and synchronization.

Run independently from request handling:
    python -m db.sync
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from db.connection import get_session
from db.graph_v2 import (
    AAVE_SOURCES,
    UNISWAP_DEPLOYMENTS_URL,
    _cleanup_orphan_asset_support_nodes,
    _parse_address_book,
    _uniswap_records,
    build_demo_view,
    build_fixture_graph,
    ensure_v2_schema,
    load_aave_v2,
    load_uniswap_v2,
    v2_summary,
)
from db.loaders.common import fetch_json, fetch_text


logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SyncTask:
    source_id: str
    deployment_key: str
    source_url: str
    acquire: Callable[[], Any]
    validate: Callable[[Any], None]
    admit: Callable[[Any], dict]


@dataclass
class SyncTaskResult:
    source_id: str
    deployment_key: str
    status: str
    attempted_at: str
    completed_at: str
    summary: dict | None = None
    error: str | None = None


def _record_attempt(task: SyncTask, attempted_at: str):
    with get_session() as session:
        session.run(
            """
            MERGE (source:KnowledgeSource {key:$source_id})
            SET source.url=$source_url, source.last_attempt_at=$attempted_at,
                source.last_status='RUNNING'
            WITH source
            OPTIONAL MATCH (deployment:ProtocolDeployment {key:$deployment_key})
            FOREACH (_ IN CASE WHEN deployment IS NULL THEN [] ELSE [1] END |
              MERGE (deployment)-[:SYNCHRONIZED_FROM]->(source)
              SET deployment.last_sync_attempt_at=$attempted_at,
                  deployment.last_sync_status='RUNNING'
            )
            """,
            source_id=task.source_id,
            source_url=task.source_url,
            attempted_at=attempted_at,
            deployment_key=task.deployment_key,
        ).consume()


def _record_result(task: SyncTask, status: str, completed_at: str, error: str | None):
    with get_session() as session:
        session.run(
            """
            MERGE (source:KnowledgeSource {key:$source_id})
            SET source.url=$source_url, source.last_status=$status,
                source.last_error=$error
            FOREACH (_ IN CASE WHEN $status='SUCCESS' THEN [1] ELSE [] END |
              SET source.last_success_at=$completed_at,
                  source.last_verified_at=$completed_at
            )
            WITH source
            OPTIONAL MATCH (deployment:ProtocolDeployment {key:$deployment_key})
            FOREACH (_ IN CASE WHEN deployment IS NULL THEN [] ELSE [1] END |
              SET deployment.last_sync_status=$status,
                  deployment.last_sync_error=$error
            )
            FOREACH (_ IN CASE WHEN deployment IS NOT NULL AND $status='SUCCESS' THEN [1] ELSE [] END |
              SET deployment.last_successful_sync_at=$completed_at,
                  deployment.last_verified_at=$completed_at
              MERGE (deployment)-[:SYNCHRONIZED_FROM]->(source)
            )
            """,
            source_id=task.source_id,
            source_url=task.source_url,
            deployment_key=task.deployment_key,
            status=status,
            completed_at=completed_at,
            error=error,
        ).consume()


def run_task(task: SyncTask) -> SyncTaskResult:
    attempted_at = _now()
    try:
        _record_attempt(task, attempted_at)
    except Exception as exc:
        completed_at = _now()
        message = f"{type(exc).__name__}: {exc}"
        logger.exception("Could not connect to record synchronization attempt")
        return SyncTaskResult(
            task.source_id, task.deployment_key, "FAILED",
            attempted_at, completed_at, error=message,
        )
    try:
        payload = task.acquire()
        task.validate(payload)
        summary = task.admit(payload)
        completed_at = _now()
        _record_result(task, "SUCCESS", completed_at, None)
        return SyncTaskResult(
            task.source_id, task.deployment_key, "SUCCESS",
            attempted_at, completed_at, summary=summary,
        )
    except Exception as exc:
        completed_at = _now()
        message = f"{type(exc).__name__}: {exc}"
        logger.exception("Knowledge synchronization failed for %s", task.source_id)
        try:
            _record_result(task, "FAILED", completed_at, message[:1000])
        except Exception:
            logger.exception("Could not record synchronization failure")
        return SyncTaskResult(
            task.source_id, task.deployment_key, "FAILED",
            attempted_at, completed_at, error=message,
        )


def _validate_aave(source: str):
    contracts, assets = _parse_address_book(source)
    if not contracts or not assets:
        raise ValueError("Aave address book contains no contracts or reserves")
    if not any(item["role"] == "pool" for item in contracts):
        raise ValueError("Aave address book contains no Pool deployment")


def _validate_uniswap(feed: dict, chain_id: int):
    if not isinstance(feed, dict) or not isinstance(feed.get("records"), list):
        raise ValueError("Malformed Uniswap deployment feed")
    records = _uniswap_records(feed, chain_id)
    if not records or not any(item["role"] == "factory" for item in records):
        raise ValueError(f"Uniswap feed has no active V3 factory for chain {chain_id}")


def build_tasks() -> list[SyncTask]:
    # Each source is acquired and admitted independently. An Aave failure does
    # not deactivate Uniswap knowledge, and vice versa.
    tasks: list[SyncTask] = []
    for chain_id, source_url in AAVE_SOURCES.items():
        tasks.append(SyncTask(
            source_id=f"aave-address-book:{chain_id}",
            deployment_key=f"aave-v3:{chain_id}",
            source_url=source_url,
            acquire=lambda url=source_url: fetch_text(url),
            validate=_validate_aave,
            admit=lambda source, cid=chain_id: load_aave_v2(cid, source=source),
        ))
    for chain_id in (1, 11155111):
        tasks.append(SyncTask(
            source_id=f"uniswap-v3:{chain_id}",
            deployment_key=f"uniswap-v3:{chain_id}",
            source_url=UNISWAP_DEPLOYMENTS_URL,
            acquire=lambda: fetch_json(UNISWAP_DEPLOYMENTS_URL),
            validate=lambda feed, cid=chain_id: _validate_uniswap(feed, cid),
            admit=lambda feed, cid=chain_id: load_uniswap_v2(cid, feed=feed),
        ))
    return tasks


def synchronize(selected: set[str] | None = None) -> dict:
    ensure_v2_schema()
    removed_orphans = _cleanup_orphan_asset_support_nodes()
    tasks = [
        task for task in build_tasks()
        if not selected or task.source_id in selected or task.deployment_key in selected
    ]
    results = [run_task(task) for task in tasks]
    if any(result.status == "SUCCESS" for result in results):
        build_demo_view()
        build_fixture_graph()
    output = {
        "started_at": min((r.attempted_at for r in results), default=_now()),
        "completed_at": _now(),
        "ok": bool(results) and all(r.status == "SUCCESS" for r in results),
        "migration": {"removed_orphan_asset_support_nodes": removed_orphans},
        "tasks": [asdict(result) for result in results],
    }
    try:
        output["summary"] = v2_summary()
    except Exception as exc:
        output["summary_error"] = f"{type(exc).__name__}: {exc}"
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Synchronize authoritative DeFi knowledge")
    parser.add_argument(
        "--source", action="append", default=[],
        help="Optional source/deployment key to sync; may be repeated",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        result = synchronize(set(args.source) or None)
    except Exception as exc:
        logger.exception("Synchronization could not start")
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
