"""Python wrapper for the ZeroDev/ERC-4337 wallet subprocess."""

import json
import os
import subprocess
from pathlib import Path

WALLET_JS = Path(__file__).parent / "wallet.mjs"
NODE_CMD = os.getenv("NODE_CMD", "node")


def _call_js(command: str, args: dict | None = None) -> dict:
    cmd = [NODE_CMD, str(WALLET_JS), command]
    if args:
        cmd.append(json.dumps(args))

    timeout_map = {
        "add_whitelist": 15,    # Local I/O; allow for slow Windows cold starts
        "check_session": 15,    # Local I/O; allow for slow Windows cold starts
        "evaluate_policy": 15,  # Deterministic local wallet-policy evaluation
        "create_wallet": 120,   # First load plus Sepolia/ZeroDev RPC calls
        "prepare_swap": 120,    # Read-only balance/allowance/quote checks
        "send_swap": 180,       # Quote plus sponsored UserOperation receipt
        "prepare_aave": 120,    # Validate Aave calldata and wallet state
        "send_aave": 180,       # Sponsored Aave V3 UserOperation
    }
    timeout = timeout_map.get(command, 60)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr.strip() or "JS script failed"
            }
        lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        for line in reversed(lines):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        return {"success": False, "error": "No JSON response from wallet script"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Wallet script '{command}' timed out (>{timeout}s). Check Node.js, RPC endpoint, or network connectivity."}
    except FileNotFoundError:
        return {"success": False, "error": "Node.js not found. Install from nodejs.org"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_wallet() -> dict:
    """Initialize the ERC-4337 client and return its smart-wallet address."""
    return _call_js("create_wallet")


def add_to_whitelist(address: str) -> dict:
    """Add a destination to the local wallet policy; may renew an expired policy."""
    return _call_js("add_whitelist", {"address": address})


def check_session(address: str, value_eth: float = 0) -> dict:
    """Evaluate the local destination/value policy without broadcasting."""
    return _call_js("check_session", {"to": address, "value_eth": value_eth})


def evaluate_policy(case: dict) -> dict:
    """Run a deterministic policy or transaction-data check in wallet.mjs."""
    return _call_js("evaluate_policy", case)


def prepare_swap(routes: list[dict], amount: str, slippage_bps: int = 100) -> dict:
    """Validate and quote a graph-derived Uniswap swap without broadcasting."""
    return _call_js("prepare_swap", {
        "routes": routes,
        "amount": str(amount),
        "slippage_bps": slippage_bps,
    })


def execute_swap(routes: list[dict], amount: str, slippage_bps: int = 100) -> dict:
    """Quote and submit a graph-derived Uniswap V3 ERC-20 swap."""
    return _call_js("send_swap", {
        "routes": routes,
        "amount": str(amount),
        "slippage_bps": slippage_bps,
    })


def prepare_aave(operation: dict) -> dict:
    """Build and validate an approved graph-derived Aave V3 call without sending."""
    return _call_js("prepare_aave", operation)


def execute_aave(operation: dict) -> dict:
    """Submit an approved graph-derived Aave V3 operation."""
    return _call_js("send_aave", operation)


def execute(*_args, **_kwargs) -> dict:
    """Reject the removed empty-calldata ETH-transfer execution path."""
    return {
        "success": False,
        "executed": False,
        "reason": (
            "Legacy execution is disabled because it was not a protocol call. "
            "Use execute_swap() with graph-derived routes."
        ),
    }
