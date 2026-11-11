"""Read-only smoke check for the synchronized Sepolia knowledge graph."""

import json

from source.db.connection import get_session
from source.db.verifier import verify_intent


def run_checks():
    aave = verify_intent("Aave V3", "USDC", action="supply")
    blocked = verify_intent("FakeSwap", "USDC", "WETH", "swap")
    with get_session() as session:
        pairs = session.run(
            """
            MATCH (:ProtocolDeployment {key:'uniswap-v3:11155111'})-[:HAS_POOL]->(pool:Pool)
            MATCH (pool)-[:TOKEN0|TOKEN1]->(a:Token {verified:true}),
                  (pool)-[:TOKEN0|TOKEN1]->(b:Token {verified:true})
            WHERE a.address < b.address
            RETURN DISTINCT a.symbol AS token_in, b.symbol AS token_out
            LIMIT 5
            """
        ).data()
    uniswap = None
    if pairs:
        pair = pairs[0]
        uniswap = verify_intent(
            "Uniswap V3", pair["token_in"], pair["token_out"], "swap"
        )
    return {
        "aave_usdc_supply": aave["decision"],
        "fake_protocol": blocked["decision"],
        "verified_uniswap_pairs": pairs,
        "uniswap_pair_check": uniswap["decision"] if uniswap else None,
    }


if __name__ == "__main__":
    print(json.dumps(run_checks(), indent=2))
