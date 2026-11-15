"""Python wrapper for the ZeroDev/ERC-4337 wallet subprocess."""

import json
import os
import subprocess
import time
from pathlib import Path

WALLET_JS = Path(__file__).parent / "wallet.mjs"
NODE_CMD = os.getenv("NODE_CMD", "node")


def _wallet_environment(*, authority: bool = False) -> dict:
    """Separate signing roles. Never inherit the owner key or load .env in Node."""
    allowed = {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE",
        "SEPOLIA_RPC", "ZERODEV_RPC", "ZERODEV_PROJECT_ID", "WALLET_WHITELIST_FILE",
        "RESTRICTED_ACCOUNT_ADDRESS", "RESTRICTED_VALIDATOR_ADDRESS",
    }
    allowed.add("GRAPH_AUTHORITY_PRIVATE_KEY" if authority else "RESTRICTED_EXECUTOR_PRIVATE_KEY")
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def _call_js(command: str, args: dict | None = None) -> dict:
    authority = command == "authorize"
    cmd = [NODE_CMD, str(WALLET_JS.with_name("authority.mjs"))] if authority else [NODE_CMD, str(WALLET_JS), command, "--stdin"]

    timeout_map = {
        "add_whitelist": 15,    # Local I/O; allow for slow Windows cold starts
        "check_session": 15,    # Local I/O; allow for slow Windows cold starts
        "evaluate_policy": 15,  # Deterministic local wallet-policy evaluation
        "create_wallet": 120,   # First load plus Sepolia/ZeroDev RPC calls
        "prepare_swap": 120,    # Read-only balance/allowance/quote checks
        "send_swap": 180,       # Quote plus sponsored UserOperation receipt
        "prepare_aave": 120,    # Validate Aave calldata and wallet state
        "send_aave": 180,       # Sponsored Aave V3 UserOperation
        "authorize": 120,
        "send_authorized": 180,
    }
    timeout = timeout_map.get(command, 60)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            input=json.dumps(args or {}),
            env=_wallet_environment(authority=authority),
            timeout=timeout,
        )
        lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        for line in reversed(lines):
            try:
                response = json.loads(line)
                if result.returncode != 0:
                    response["success"] = False
                return response
            except json.JSONDecodeError:
                continue
        return {"success": False, "error": "No JSON response from wallet script"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Wallet script '{command}' timed out (>{timeout}s). Check Node.js, RPC endpoint, or network connectivity."}
    except FileNotFoundError:
        return {"success": False, "error": "Node.js not found. Install from nodejs.org"}
    except Exception:
        return {"success": False, "error": "Wallet subprocess failed"}


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
    """Compatibility wrapper: raw swaps are rejected; use execute_approved."""
    return _call_js("send_swap", {
        "routes": routes,
        "amount": str(amount),
        "slippage_bps": slippage_bps,
    })


def prepare_aave(operation: dict) -> dict:
    """Build and validate an approved graph-derived Aave V3 call without sending."""
    return _call_js("prepare_aave", operation)


def execute_aave(operation: dict) -> dict:
    """Compatibility wrapper: raw Aave calls are rejected; use execute_approved."""
    return _call_js("send_aave", operation)


def execute_approved(operation, verification_id: str) -> dict:
    """Called only after atomic capability claim and graph re-verification.

    The signer worker receives a frozen authorization, not the authority key.
    Raw execute_swap/execute_aave commands fail closed in this branch.
    """
    expires_at = operation.approval_expires_at
    if (operation.decision.value != "APPROVED" or operation.chain_id != 11155111
            or not expires_at or expires_at <= time.time()
            or not operation.smart_account
            or operation.smart_account.lower() != os.getenv("RESTRICTED_ACCOUNT_ADDRESS", "").lower()):
        return {"executed": False, "reason": "Live approved operation required"}
    if operation.action == "swap":
        prepared = prepare_swap(operation.routes, format(operation.intent.amount, "f"), operation.slippage_bps)
    else:
        prepared = prepare_aave({
            "action": operation.action, "pool_address": operation.verified_address,
            "asset_address": operation.verified_asset, "asset_symbol": operation.verified_asset_symbol,
            "asset_decimals": operation.verified_asset_decimals,
            "amount": format(operation.intent.amount, "f"),
            "function_signature": operation.verified_function, "function_selector": operation.verified_selector,
            "interest_rate_mode": operation.interest_rate_mode, "referral_code": operation.referral_code,
        })
    if not prepared.get("success") or not prepared.get("authorization_plan"):
        return {"executed": False, "reason": prepared.get("reason", "Authorization preparation failed")}
    authorized = _call_js("authorize", {
        "approved": operation.model_dump(mode="json"), "verificationId": verification_id,
        "expiresAt": expires_at, "plan": prepared["authorization_plan"],
    })
    if not authorized.get("success"):
        return {"executed": False, "reason": authorized.get("reason", "Wallet authorization failed")}
    result = _call_js("send_authorized", authorized["permit"])
    summary = {k: v for k, v in prepared.items() if k not in {"authorization_plan", "success", "executed"}}
    summary.update(verified_address=operation.verified_address, action=operation.action)
    if result.get("tx_hash"):
        summary["explorer"] = f"https://sepolia.etherscan.io/tx/{result['tx_hash']}"
    return {**summary, **result}


def execute(*_args, **_kwargs) -> dict:
    """Reject the removed empty-calldata ETH-transfer execution path."""
    return {
        "success": False,
        "executed": False,
        "reason": (
            "Legacy execution is disabled because it was not a protocol call. "
            "Use execute_approved() after capability claim and re-verification."
        ),
    }
