from db.verifier import verify_intent

def process(intent):
    print(f"\nIntent received: {intent}")
    result = verify_intent(
        protocol  = intent["protocol"],
        token_in  = intent["token_in"],
        token_out = intent.get("token_out"),
        action    = intent.get("action", "swap")
    )
    if result["decision"] == "APPROVED":
        print("  APPROVED")
        print(f"  Verified address : {result['verified_address']}")
        print(f"  Protocol         : {result['protocol']}")
        print(f"  Latency          : {result['latency_ms']}ms")
        print("  Next step        : build payload -> send to ERC-4337 wallet")
    else:
        print("  BLOCKED")
        print(f"  Reason           : {result['reason']}")
        print(f"  Latency          : {result['latency_ms']}ms")
        print("  No payload built. Funds safe.")
    return result

if __name__ == "__main__":
    intents = [
        {"protocol":"Uniswap V3","token_in":"USDC","token_out":"WETH","action":"swap"},
        {"protocol":"Aave V3",   "token_in":"USDC","action":"supply"},
        {"protocol":"FakeSwap",  "token_in":"USDC","token_out":"WETH","action":"swap"},
        {"protocol":"Uniswap V3","token_in":"USDC","token_out":"RUGTOKEN","action":"swap"},
    ]
    for intent in intents:
        process(intent)
