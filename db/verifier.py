import time
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.connection import get_session

CYPHER_SWAP = """
    MATCH (family:ProtocolFamily)-[:HAS_DEPLOYMENT]->
          (deployment:ProtocolDeployment {verified:true, chain_id:$chain_id})
    WHERE toLower(family.name) = toLower($protocol)
    MATCH (deployment)-[:SUPPORTS_ACTION]->(:Action {name:'swap'})
    MATCH (deployment)-[:HAS_POOL]->(pool:Pool {verified:true, chain_id:$chain_id})
    MATCH (pool)-[:SUPPORTS_TOKEN]->(t1:Token {symbol:$token_in, verified:true, chain_id:$chain_id})
    MATCH (pool)-[:SUPPORTS_TOKEN]->(t2:Token {symbol:$token_out, verified:true, chain_id:$chain_id})
    MATCH (deployment)-[:DEPLOYED_CONTRACT {role:'swap_router'}]->(router:Contract {verified:true})
    MATCH (deployment)-[:DEPLOYED_CONTRACT {role:'quoter'}]->(quoter:Contract {verified:true})
    WHERE t1.address <> t2.address
      AND t1.decimals IS NOT NULL
      AND t2.decimals IS NOT NULL
      AND pool.fee IS NOT NULL
    RETURN router.address AS address, quoter.address AS quoter_address,
           pool.address AS pool_address, pool.fee AS pool_fee,
           coalesce(pool.featured, false) AS featured,
           t1.address AS token_in_address, t1.symbol AS token_in_symbol,
           t1.decimals AS token_in_decimals,
           t2.address AS token_out_address, t2.symbol AS token_out_symbol,
           t2.decimals AS token_out_decimals,
           family.name AS protocol, $chain_id AS chain_id
    ORDER BY featured DESC, pool.fee ASC, pool.address ASC
    LIMIT 20
"""

CYPHER_LENDING = """
    MATCH (family:ProtocolFamily)-[:HAS_DEPLOYMENT]->
          (deployment:ProtocolDeployment {verified:true, chain_id:$chain_id})
    WHERE toLower(family.name) = toLower($protocol)
    MATCH (deployment)-[:SUPPORTS_ACTION]->(:Action {name:$action})
    MATCH (deployment)-[:HAS_RESERVE]->(reserve:Reserve {verified:true})
    MATCH (reserve)-[:UNDERLYING_ASSET]->(token:Token {symbol:$token_in, chain_id:$chain_id, verified:true})
    MATCH (reserve)-[:SUPPORTS_ACTION]->(:Action {name:$action})
    MATCH (deployment)-[:DEPLOYED_CONTRACT {role:'pool'}]->(pool:Contract {verified:true})
    RETURN pool.address AS address, null AS pool_address,
           family.name AS protocol, $chain_id AS chain_id
    LIMIT 1
"""

def verify_intent(protocol, token_in, token_out=None, action="swap", chain_id=11155111):
    start = time.time()
    action = (action or "").lower()
    token_in = (token_in or "").upper()
    token_out = (token_out or "").upper() or None
    with get_session() as s:
        if action == "swap":
            records = list(s.run(CYPHER_SWAP,
                protocol=protocol,
                token_in=token_in,
                token_out=token_out,
                chain_id=chain_id))
            latency = round((time.time() - start) * 1000, 2)
            if records:
                routes = [
                    {
                        "router_address": record["address"],
                        "quoter_address": record["quoter_address"],
                        "pool_address": record["pool_address"],
                        "pool_fee": record["pool_fee"],
                        "token_in_address": record["token_in_address"],
                        "token_in_symbol": record["token_in_symbol"],
                        "token_in_decimals": record["token_in_decimals"],
                        "token_out_address": record["token_out_address"],
                        "token_out_symbol": record["token_out_symbol"],
                        "token_out_decimals": record["token_out_decimals"],
                    }
                    for record in records
                ]
                first = records[0]
                return {
                    "decision":         "APPROVED",
                    "verified_address": first["address"],
                    "verified_pool":    first["pool_address"],
                    "protocol":         first["protocol"],
                    "action":           action,
                    "chain_id":         first["chain_id"],
                    "network":          _network_name(chain_id),
                    "routes":           routes,
                    "latency_ms":       latency,
                }
            return _blocked(
                f"No trusted path: {protocol} / {action} / {token_in}",
                protocol, token_in, token_out, action, start, chain_id
            )
        elif action in ("supply", "deposit", "withdraw", "borrow", "repay"):
            graph_action = "supply" if action == "deposit" else action
            result = s.run(CYPHER_LENDING,
                protocol=protocol,
                token_in=token_in,
                action=graph_action,
                chain_id=chain_id)
        else:
            return _blocked(f"Unsupported action: {action}",
                protocol, token_in, token_out, action, start, chain_id)

        record = result.single()
        latency = round((time.time() - start) * 1000, 2)

        if record:
            return {
                "decision":         "APPROVED",
                "verified_address": record["address"],
                "verified_pool":    record["pool_address"],
                "protocol":         record["protocol"],
                "action":           action,
                "chain_id":         record["chain_id"],
                "network":          _network_name(chain_id),
                "latency_ms":       latency
            }
        return _blocked(
            f"No trusted path: {protocol} / {action} / {token_in}",
            protocol, token_in, token_out, action, start, chain_id)

def _blocked(reason, protocol, token_in, token_out, action, start, chain_id=11155111):
    return {
        "decision":         "BLOCKED",
        "verified_address": None,
        "reason":           reason,
        "protocol":         protocol,
        "action":           action,
        "chain_id":         chain_id,
        "network":          _network_name(chain_id),
        "latency_ms":       round((time.time() - start) * 1000, 2)
    }


def _network_name(chain_id):
    if chain_id == 1:
        return "Ethereum Mainnet"
    if chain_id == 11155111:
        return "Ethereum Sepolia"
    return f"Chain {chain_id}"

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
