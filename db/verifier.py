import time
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.connection import get_session

CYPHER_SWAP = """
    MATCH (proto:Protocol {name:$protocol, verified:true})
        -[:DEPLOYED_CONTRACT]->(pool:Pool)
        -[:SWAPS_TOKEN]->(t1:Token {symbol:$token_in}),
    (pool)-[:SWAPS_TOKEN]->(t2:Token {symbol:$token_out})
    RETURN pool.address AS address, proto.name AS protocol
    LIMIT 1
"""

CYPHER_SUPPLY = """
    MATCH (proto:Protocol {name:$protocol, verified:true})
        -[:DEPLOYED_CONTRACT]->(pool:Pool {action:"supply"})
        -[:SWAPS_TOKEN]->(t:Token {symbol:$token_in})
    RETURN pool.address AS address, proto.name AS protocol
    LIMIT 1
"""

def verify_intent(protocol, token_in, token_out=None, action="swap"):
    start = time.time()
    with get_session() as s:
        if action == "swap":
            result = s.run(CYPHER_SWAP,
                protocol=protocol,
                token_in=token_in,
                token_out=token_out)
        elif action in ("supply", "deposit"):
            result = s.run(CYPHER_SUPPLY,
                protocol=protocol,
                token_in=token_in)
        else:
            return _blocked(f"Unsupported action: {action}",
                protocol, token_in, token_out, action, start)

        record = result.single()
        latency = round((time.time() - start) * 1000, 2)

        if record:
            return {
                "decision":         "APPROVED",
                "verified_address": record["address"],
                "protocol":         record["protocol"],
                "action":           action,
                "latency_ms":       latency
            }
        return _blocked(
            f"No trusted path: {protocol} / {action} / {token_in}",
            protocol, token_in, token_out, action, start)

def _blocked(reason, protocol, token_in, token_out, action, start):
    return {
        "decision":         "BLOCKED",
        "verified_address": None,
        "reason":           reason,
        "protocol":         protocol,
        "action":           action,
        "latency_ms":       round((time.time() - start) * 1000, 2)
    }

if __name__ == "__main__":
    tests = [
        ("Uniswap V3",  "USDC",  "WETH",  "swap"),
        ("Uniswap V3",  "DAI",   "WETH",  "swap"),
        ("Aave V3",     "USDC",  None,    "supply"),
        ("FakeSwap",    "USDC",  "WETH",  "swap"),
        ("Uniswap V3",  "USDC",  "SHITCOIN", "swap"),
        ("Uniswap V3",  "USDC",  "WETH",  "borrow"),
    ]
    print(f"{'Protocol':<14} {'Action':<8} {'In':<10} {'Out':<10} {'Decision':<10} {'ms'}")
    print("-" * 62)
    for proto, tin, tout, action in tests:
        r = verify_intent(proto, tin, tout, action)
        addr = r.get("verified_address","")[:12]+"..." if r.get("verified_address") else "-"
        print(f"{proto:<14} {action:<8} {tin:<10} {str(tout):<10} "
              f"{r['decision']:<10} {r['latency_ms']}ms  {addr}")