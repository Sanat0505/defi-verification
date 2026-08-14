"""Manual full-pipeline preflight that never broadcasts a transaction."""

import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from db.verifier import verify_intent
from wallet.erc4337 import add_to_whitelist, prepare_swap


load_dotenv()


def run():
    amount = "0.001"
    graph_result = verify_intent("Uniswap V3", "USDC", "WETH", "swap")
    print(json.dumps(graph_result, indent=2))
    if graph_result["decision"] != "APPROVED":
        return

    routes = graph_result.get("routes", [])
    destinations = {
        graph_result["verified_address"],
        *(route["token_in_address"] for route in routes),
    }
    for address in destinations:
        print(json.dumps(add_to_whitelist(address), indent=2))

    # Read-only balance, allowance, liquidity, quote, and calldata checks.
    result = prepare_swap(routes, amount)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    run()
