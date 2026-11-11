"""Manual swap preparation; updates the wallet allowlist but never broadcasts.

Run only with authorization to update the policy and prepare the swap.
For a check using the existing policy, use evaluation.wallet_live_check.
"""

import json

from dotenv import load_dotenv

from source.db.verifier import verify_intent
from source.wallet.erc4337 import add_to_whitelist, prepare_swap


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

    result = prepare_swap(routes, amount)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    run()
