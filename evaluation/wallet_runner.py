"""Deterministic wallet-policy and execution-boundary evaluation.

This runner never broadcasts. Local policy and transaction-data checks execute
inside wallet.mjs; RPC, bundler, paymaster, and successful submission outcomes
are controlled fixtures at the Python wallet boundary.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import platform
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import app as api_module
from core.models import ApprovedOperation, ExecuteRequest, IntentCandidate
from core.state import VerificationCapabilityStore
from wallet import erc4337


DEFAULT_DATASET = Path(__file__).parent / "datasets" / "wallet_cases.json"
DEFAULT_REPORTS = Path(__file__).parent / "wallet_reports"
TEST_ADDRESS = "0x" + "1" * 40
OTHER_ADDRESS = "0x" + "9" * 40


def _find_node() -> str | None:
    configured = os.getenv("NODE_CMD")
    if configured and Path(configured).exists():
        return configured
    discovered = shutil.which(configured or "node")
    if discovered:
        return discovered
    if os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "node.exe"
        if candidate.exists():
            return str(candidate)
    return None


def _operation(action: str = "withdraw") -> ApprovedOperation:
    signatures = {
        "supply": ("supply(address,uint256,address,uint16)", "0x617ba037"),
        "withdraw": ("withdraw(address,uint256,address)", "0x69328dec"),
        "borrow": ("borrow(address,uint256,uint256,uint16,address)", "0xa415bcad"),
        "repay": ("repay(address,uint256,uint256,address)", "0x573ade81"),
    }
    signature, selector = signatures[action]
    return ApprovedOperation(
        intent=IntentCandidate(
            action=action,
            protocol="Aave V3",
            token_in="USDT",
            amount=Decimal("10"),
            chain="Ethereum Sepolia",
            chain_id=11155111,
        ),
        protocol="Aave V3",
        action=action,
        chain_id=11155111,
        network="Ethereum Sepolia",
        verified_address=TEST_ADDRESS,
        verified_asset="0x" + "2" * 40,
        verified_asset_symbol="USDT",
        verified_asset_decimals=6,
        verified_function=signature,
        verified_selector=selector,
        interest_rate_mode=2 if action in {"borrow", "repay"} else None,
    )


def _graph_result(operation: ApprovedOperation) -> dict:
    return {
        "decision": "APPROVED",
        "protocol": operation.protocol,
        "action": operation.action,
        "chain_id": operation.chain_id,
        "network": operation.network,
        "verified_address": operation.verified_address,
        "verified_pool": None,
        "verified_asset": operation.verified_asset,
        "verified_asset_decimals": operation.verified_asset_decimals,
        "verified_function": operation.verified_function,
        "verified_selector": operation.verified_selector,
        "latency_ms": 0,
    }


def _write_whitelist(path: Path, state: str) -> None:
    now_ms = int(time.time() * 1000)
    addresses = [TEST_ADDRESS.lower()] if state in {"allowed", "expired"} else [OTHER_ADDRESS.lower()]
    expires_at = now_ms - 1000 if state == "expired" else now_ms + 60_000
    path.write_text(json.dumps({
        "created_at": now_ms - 1000,
        "expires_at": expires_at,
        "addresses": addresses,
    }), encoding="utf-8")


async def _run_api_case(case: dict) -> tuple[str, str, dict]:
    operation = _operation()
    store = VerificationCapabilityStore(ttl_seconds=60)
    verification_id = store.issue(operation)
    current = _graph_result(operation)
    if case["mode"] == "api_authority_changed":
        current = {**current, "verified_address": OTHER_ADDRESS}

    whitelist_result = {"success": True}
    if case["mode"] == "api_whitelist_failure":
        whitelist_result = {
            "success": False,
            "reason_code": "DESTINATION_NOT_ALLOWED",
            "error": "controlled policy rejection",
        }

    wallet_result = {
        "executed": True,
        "tx_hash": "0x" + "a" * 64,
        "smart_wallet": "0x" + "3" * 40,
        "verified_address": operation.verified_address,
        "asset_address": operation.verified_asset,
        "token_in": "USDT",
        "amount_in": "10",
        "action": "withdraw",
    }
    if case["mode"] == "api_wallet_failure":
        code = case["wallet_reason_code"]
        wallet_result = {
            "executed": False,
            "reason_code": code,
            "reason": f"Controlled fixture: {code}",
        }

    with ExitStack() as stack:
        stack.enter_context(patch.object(api_module, "capability_store", store))
        stack.enter_context(patch.object(api_module, "verify_intent", lambda *args: current))
        stack.enter_context(patch.object(api_module, "add_to_whitelist", lambda address: whitelist_result))
        stack.enter_context(patch.object(api_module, "execute_aave", lambda payload: wallet_result))
        response = await api_module.execute(ExecuteRequest(
            verification_id=verification_id,
            wallet_address="0x" + "4" * 40,
        ))
    execution = response.get("execution") or {}
    outcome = "EXECUTED" if response.get("decision") == "EXECUTED" else "BLOCKED"
    return outcome, execution.get("reason_code", "MISSING_REASON_CODE"), {
        "response": response,
        "submission_simulated": case["mode"] == "api_wallet_success",
    }


async def run_case(case: dict, whitelist_file: Path) -> dict:
    started = time.perf_counter()
    mode = case["mode"]
    evidence: dict = {}
    if mode == "wallet_policy":
        if case.get("whitelist_state"):
            _write_whitelist(whitelist_file, case["whitelist_state"])
        result = erc4337.evaluate_policy(case["input"])
        outcome = "PASS" if result.get("allowed") else "BLOCKED"
        reason_code = result.get("reason_code", "MISSING_REASON_CODE")
        evidence = {"wallet_result": result}
    elif mode == "request_mutation":
        try:
            ExecuteRequest.model_validate({
                "verification_id": "v" * 32,
                "wallet_address": "0x" + "4" * 40,
                "amount": "999999",
                "pool_address": OTHER_ADDRESS,
            })
            outcome, reason_code = "PASS", "MUTATION_ACCEPTED"
        except ValidationError as exc:
            outcome, reason_code = "BLOCKED", "REQUEST_SCHEMA_REJECTED"
            evidence = {"validation_errors": len(exc.errors())}
    elif mode == "capability_replay":
        store = VerificationCapabilityStore(ttl_seconds=60)
        token = store.issue(_operation())
        first, first_status = store.claim_with_status(token)
        second, second_status = store.claim_with_status(token)
        outcome = "BLOCKED" if first and not second else "PASS"
        reason_code = second_status
        evidence = {"first_claim": first_status, "second_claim": second_status}
    elif mode == "capability_expired":
        store = VerificationCapabilityStore(ttl_seconds=-1)
        token = store.issue(_operation())
        operation, status = store.claim_with_status(token)
        outcome = "BLOCKED" if operation is None else "PASS"
        reason_code = status
    elif mode.startswith("api_"):
        outcome, reason_code, evidence = await _run_api_case(case)
    elif mode == "not_implemented":
        outcome = "NOT_IMPLEMENTED"
        reason_code = case["expected_reason_code"]
        evidence = {"requirement": case["requirement"]}
    else:
        outcome, reason_code = "ERROR", "UNKNOWN_SCENARIO_MODE"

    expected_outcome = case["expected_outcome"]
    expected_reason = case["expected_reason_code"]
    return {
        "id": case["id"],
        "category": case["category"],
        "mode": mode,
        "expected_outcome": expected_outcome,
        "actual_outcome": outcome,
        "expected_reason_code": expected_reason,
        "actual_reason_code": reason_code,
        "passed": outcome == expected_outcome and reason_code == expected_reason,
        "implemented": mode != "not_implemented",
        "transaction_broadcast": False,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "evidence": evidence,
    }


def calculate_wallet_metrics(records: list[dict]) -> dict:
    implemented = [record for record in records if record["implemented"]]
    gaps = [record for record in records if not record["implemented"]]
    categories: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        categories[record["category"]].append(record)
    return {
        "total_scenarios": len(records),
        "implemented_scenarios": len(implemented),
        "documented_gaps": len(gaps),
        "passed_implemented": sum(record["passed"] for record in implemented),
        "failed_implemented": sum(not record["passed"] for record in implemented),
        "implemented_conformance": (
            sum(record["passed"] for record in implemented) / len(implemented)
            if implemented else None
        ),
        "transactions_broadcast": sum(record["transaction_broadcast"] for record in records),
        "average_latency_ms": round(
            sum(record["latency_ms"] for record in records) / len(records), 2
        ) if records else None,
        "by_category": {
            category: {
                "scenarios": len(values),
                "passed": sum(record["passed"] for record in values),
                "gaps": sum(not record["implemented"] for record in values),
            }
            for category, values in sorted(categories.items())
        },
        "gap_ids": [record["id"] for record in gaps],
    }


def _markdown(metadata: dict, metrics: dict, records: list[dict]) -> str:
    conformance = metrics["implemented_conformance"]
    pct = "n/a" if conformance is None else f"{conformance * 100:.2f}%"
    lines = [
        "# Wallet evaluation summary",
        "",
        f"- Timestamp (UTC): {metadata['timestamp_utc']}",
        f"- Dataset version: `{metadata['dataset_version']}`",
        f"- Implemented scenarios: {metrics['implemented_scenarios']}",
        f"- Implemented scenarios passed: {metrics['passed_implemented']}",
        f"- Implemented conformance: {pct}",
        f"- Explicitly documented gaps: {metrics['documented_gaps']}",
        f"- Transactions broadcast: {metrics['transactions_broadcast']}",
        "",
        "## Scenario results",
        "",
        "| ID | Category | Expected | Actual | Reason code | Result |",
        "|---|---|---|---|---|---|",
    ]
    for record in records:
        result = "PASS" if record["passed"] else "FAIL"
        lines.append(
            f"| {record['id']} | {record['category']} | {record['expected_outcome']} | "
            f"{record['actual_outcome']} | `{record['actual_reason_code']}` | {result} |"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "`NOT_IMPLEMENTED` rows are declared scope gaps and are excluded from the implemented-conformance denominator. "
        "All RPC, bundler, paymaster, simulation, and success responses are controlled fixtures. "
        "The runner exercises the real local JavaScript destination and transaction-data policy but never broadcasts.",
    ])
    return "\n".join(lines) + "\n"


async def run(args) -> int:
    dataset_path = Path(args.dataset)
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = dataset["cases"]
    if args.case:
        selected = set(args.case)
        cases = [case for case in cases if case["id"] in selected]

    node = _find_node()
    if not node:
        raise RuntimeError("Node.js is required for wallet-policy evaluation")
    erc4337.NODE_CMD = node

    with tempfile.TemporaryDirectory(prefix="defi-wallet-eval-") as temp_dir:
        whitelist_file = Path(temp_dir) / "session-whitelist.json"
        previous = os.environ.get("WALLET_WHITELIST_FILE")
        os.environ["WALLET_WHITELIST_FILE"] = str(whitelist_file)
        try:
            records = [await run_case(case, whitelist_file) for case in cases]
        finally:
            if previous is None:
                os.environ.pop("WALLET_WHITELIST_FILE", None)
            else:
                os.environ["WALLET_WHITELIST_FILE"] = previous

    metrics = calculate_wallet_metrics(records)
    timestamp = datetime.now(timezone.utc)
    metadata = {
        "timestamp_utc": timestamp.isoformat(),
        "dataset": str(dataset_path.resolve()),
        "dataset_version": dataset.get("version"),
        "python": platform.python_version(),
        "node": node,
        "broadcasting_enabled": False,
    }
    report = {"metadata": metadata, "metrics": metrics, "results": records}
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"wallet-evaluation-{stamp}.json"
    csv_path = output_dir / f"wallet-evaluation-{stamp}.csv"
    md_path = output_dir / f"wallet-evaluation-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "id", "category", "mode", "expected_outcome", "actual_outcome",
            "expected_reason_code", "actual_reason_code", "passed", "implemented",
            "transaction_broadcast", "latency_ms",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    summary = _markdown(metadata, metrics, records)
    md_path.write_text(summary, encoding="utf-8")
    print(summary)
    print(f"JSON: {json_path}\nCSV: {csv_path}\nSummary: {md_path}")
    return 0 if metrics["failed_implemented"] == 0 else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic non-broadcasting wallet evaluation"
    )
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORTS))
    parser.add_argument("--case", action="append", default=[])
    return asyncio.run(run(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
