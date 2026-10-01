"""
wallet/erc4337.py

Python wrapper around wallet.mjs (ZeroDev JS SDK).
Called from FastAPI after graph verification APPROVES a transaction.

Architecture:
    Graph layer APPROVED
        → add_to_whitelist(verified_address)   ← registers address in JS session
        → execute(verified_address, ...)        ← sends UserOperation via ZeroDev
"""

import os
import json
import time
import subprocess
from pathlib import Path

# Path to the JS wallet script — sits in wallet/ folder
WALLET_JS = Path(__file__).parent / "wallet.mjs"
NODE_CMD  = "node"


def _call_js(command: str, args: dict = None) -> dict:
    """Call wallet.mjs with a command and JSON args, return parsed response."""
    cmd = [NODE_CMD, str(WALLET_JS), command]
    if args:
        cmd.append(json.dumps(args))

    # Passes PRIVATE_KEY, SEPOLIA_RPC, and ZeroDev configuration from .env.
    env = {**os.environ}

    # Command-specific timeouts: add_whitelist is fast (file I/O only),
    # Swap preflight and execution need RPC/bundler time.
    timeout_map = {
        "add_whitelist": 15,    # Local I/O; allow for slow Windows cold starts
        "check_session": 15,    # Local I/O; allow for slow Windows cold starts
        "create_wallet": 120,   # First load plus Sepolia/ZeroDev RPC calls
        "prepare_swap": 120,    # Read-only balance/allowance/quote checks
        "send_swap": 180        # Quote plus sponsored UserOperation receipt
    }
    timeout = timeout_map.get(command, 60)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )
        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr.strip() or "JS script failed"
            }
        # Parse the last JSON line from stdout
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
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
    """
    Create and return the ERC-4337 smart wallet address.
    Call this once on startup to confirm the wallet is reachable.
    """
    return _call_js("create_wallet")


def add_to_whitelist(address: str) -> dict:
    """
    Add a graph-verified address to the ERC-4337 session key whitelist.
    Must be called BEFORE execute() — otherwise ERC-4337 will block the tx.
    """
    return _call_js("add_whitelist", {"address": address})


def _legacy_execute(verified_address: str, amount_eth: float, action: str) -> dict:
    """
    Send a UserOperation via ZeroDev on Ethereum Sepolia.

    Args:
        verified_address: address resolved from graph (NOT from LLM)
        amount_eth:       transaction value in ETH
        action:           swap / supply / transfer etc.

    Returns dict with:
        executed (bool)
        tx_hash (str) if executed
        blocked_by (str) if blocked
        reason (str) if blocked
        latency_ms (int)
        explorer (str) — Sepolia Etherscan link if executed
    """
    return {
        "success": False,
        "executed": False,
        "reason": "Legacy empty-calldata execution is disabled",
    }


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


# ── Quick test ────────────────────────────────────────────
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    print("Step 1: Creating ERC-4337 smart wallet...")
    wallet = create_wallet()
    print(json.dumps(wallet, indent=2))

    if wallet.get("success"):
        test_addr = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"

        print("\nStep 2: Adding address to whitelist...")
        wl = add_to_whitelist(test_addr)
        print(json.dumps(wl, indent=2))

        print("\nStep 3: Sending UserOperation...")
        result = execute(test_addr, 0.0001, "swap")
        print(json.dumps(result, indent=2))

        if result.get("executed"):
            print(f"\nSUCCESS — view on explorer: {result.get('explorer')}")
        else:
            print(f"\nBLOCKED by {result.get('blocked_by')}: {result.get('reason')}")
