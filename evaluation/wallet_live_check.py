"""Read current wallet destination policy and optionally prepare five operations.

Never calls /api/execute, add_whitelist, send_swap, send_aave or any transaction
submission command. A blocked policy stops that case before external preflight.
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from source.core.config import settings
from source.db.connection import close_driver
from source.db.verifier import verify_intent
from evaluation.wallet_runner import _find_node
from source.wallet import erc4337


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '.cache/evaluation-runs/wallet-live'


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def redact(value):
    if isinstance(value, str):
        value = re.sub(r"https?://\S+", "[RPC URL omitted]", value)
        return re.sub(r"0x[a-fA-F0-9]{64}\b", "[64-digit hex omitted]", value)
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def run_case(action, protocol, token_in, token_out, amount):
    started = time.perf_counter()
    result = {"action": action, "protocol": protocol, "token_in": token_in,
              "token_out": token_out, "amount": amount, "chain_id": 11155111,
              "transaction_broadcast": False, "prepare_called": False}
    graph = verify_intent(protocol, token_in, token_out, action, 11155111)
    result["graph"] = graph
    if graph["decision"] != "APPROVED":
        result["status"] = "NOT_REACHED_GRAPH_NOT_APPROVED"
    else:
        destinations = {graph["verified_address"]}
        if action == "swap":
            destinations.update(route["token_in_address"] for route in graph["routes"])
        elif action in {"supply", "repay"}:
            destinations.add(graph["verified_asset"])
        checks = [{"destination": address, **erc4337.check_session(address, 0)} for address in sorted(destinations)]
        result["current_destination_checks"] = checks
        if not all(check.get("success") and check.get("allowed") for check in checks):
            result["status"] = "BLOCKED_BY_CURRENT_POLICY"
        else:
            result["prepare_called"] = True
            if action == "swap":
                result["prepare"] = erc4337.prepare_swap(graph["routes"], amount, settings.swap_slippage_bps)
            else:
                result["prepare"] = erc4337.prepare_aave({
                    "action": action, "pool_address": graph["verified_address"],
                    "asset_address": graph["verified_asset"], "asset_symbol": token_in,
                    "asset_decimals": graph["verified_asset_decimals"], "amount": amount,
                    "function_signature": graph["verified_function"],
                    "function_selector": graph["verified_selector"],
                    "interest_rate_mode": 2 if action in {"borrow", "repay"} else None,
                    "referral_code": 0,
                })
            if result["prepare"].get("executed"):
                raise RuntimeError("Read-only preparation unexpectedly reported execution")
            result["status"] = "PREPARED_NOT_SUBMITTED" if result["prepare"].get("prepared") else "PREPARATION_BLOCKED_OR_UNAVAILABLE"
    result["wall_latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return redact(result)


def main():
    node = _find_node()
    if not node:
        raise RuntimeError("Node.js is required")
    erc4337.NODE_CMD = node
    # Same file resolution as wallet.mjs. Do not print environment credentials.
    policy_file = Path(os.getenv("WALLET_WHITELIST_FILE", str(ROOT / "source/wallet/session-whitelist.json"))).resolve()
    before = file_hash(policy_file)
    timestamp = datetime.now(timezone.utc)
    report = {"metadata": {
        "timestamp_utc": timestamp.isoformat(), "mode": "current_policy_and_read_only_prepare",
        "wallet_policy_file": str(policy_file), "policy_sha256_before": before,
        "transaction_broadcast": False, "whitelist_writes": False,
        "uses_existing_policy_without_auto_whitelisting": True,
        "code_sha256": {str(path.relative_to(ROOT)): file_hash(path) for path in [
            Path(__file__).resolve(), ROOT / "source/wallet/wallet.mjs", ROOT / "source/wallet/erc4337.py"]},
        "limitations": [
            "Observational check, not a labeled accuracy benchmark or an end-to-end execution test.",
            "The execution API normally adds graph-approved destinations before wallet execution; this read-only runner intentionally does not renew/change the real policy.",
            "Aave prepare builds calldata and checks funding/allowance for applicable actions; it does not independently check collateral, debt, withdrawable position or simulate the full Aave call.",
            "A prepared result is not proof of transaction success; user-wallet/backend-signer binding is not implemented.",
        ]}, "results": []}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / ("wallet-live-check-" + timestamp.strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    cases = [("swap", "Uniswap V3", "USDC", "WETH", "10"),
             ("supply", "Aave V3", "USDT", None, "10"),
             ("withdraw", "Aave V3", "USDT", None, "10"),
             ("borrow", "Aave V3", "USDT", None, "5"),
             ("repay", "Aave V3", "USDT", None, "1")]
    try:
        for args in cases:
            result = run_case(*args)
            report["results"].append(result)
            path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"{args[0]}: {result['status']}", flush=True)
    finally:
        close_driver()
        report["metadata"]["policy_sha256_after"] = file_hash(policy_file)
        report["metadata"]["policy_unchanged"] = before == file_hash(policy_file)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"JSON: {path}", flush=True)
    return 0 if report["metadata"]["policy_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
