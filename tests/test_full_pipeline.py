import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from db.verifier import verify_intent
from wallet.erc4337 import add_to_whitelist, prepare_swap

async def test_full_pipeline():
    print("\n=== FULL PIPELINE TEST ===\n")

    # Step 1 — simulate user prompt already parsed by LLM
    intent = {
        "protocol":  "Uniswap V3",
        "token_in":  "USDC",
        "token_out": "WETH",
        "action":    "swap",
        "amount":    0.001
    }
    print(f"Intent: {intent}")

    # Step 2 — graph verification
    graph_result = verify_intent(
        protocol  = intent["protocol"],
        token_in  = intent["token_in"],
        token_out = intent["token_out"],
        action    = intent["action"]
    )
    print(f"\nGraph decision: {graph_result['decision']}")

    if graph_result["decision"] == "BLOCKED":
        print(f"Blocked by graph: {graph_result['reason']}")
        return

    verified_address = graph_result["verified_address"]
    print(f"Verified address from graph: {verified_address}")

    # Step 3 — whitelist the graph-verified address in ERC-4337
    wl = add_to_whitelist(verified_address)
    print(f"\nWhitelisted: {wl}")

    for route in graph_result.get("routes", []):
        add_to_whitelist(route["token_in_address"])

    # Step 4 — send UserOperation
    print("\nPreparing Sepolia swap without broadcasting...")
    result = prepare_swap(graph_result.get("routes", []), str(intent["amount"]))
    print(f"\nWallet result: {result}")

    if result.get("prepared"):
        print("\nPREFLIGHT PASSED (no transaction broadcast)")
    else:
        print(f"\nBLOCKED by {result.get('blocked_by')}: {result.get('reason')}")

asyncio.run(test_full_pipeline())
