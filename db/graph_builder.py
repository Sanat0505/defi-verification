import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.connection import get_session

CONSTRAINTS = (
    "CREATE CONSTRAINT chain_id IF NOT EXISTS FOR (n:Chain) REQUIRE n.chain_id IS UNIQUE",
    "CREATE CONSTRAINT protocol_key IF NOT EXISTS FOR (n:Protocol) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT contract_identity IF NOT EXISTS FOR (n:Contract) REQUIRE (n.chain_id, n.address) IS UNIQUE",
    "CREATE CONSTRAINT token_identity IF NOT EXISTS FOR (n:Token) REQUIRE (n.chain_id, n.address) IS UNIQUE",
    "CREATE CONSTRAINT action_name IF NOT EXISTS FOR (n:Action) REQUIRE n.name IS UNIQUE",
)


def ensure_schema():
    """Create uniqueness constraints shared by the official-data loaders."""
    with get_session() as session:
        for statement in CONSTRAINTS:
            session.run(statement).consume()


def graph_summary():
    with get_session() as session:
        nodes = session.run(
            "MATCH (n) UNWIND labels(n) AS label "
            "RETURN label, count(*) AS count ORDER BY label"
        ).data()
        relationships = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY type"
        ).data()
    return {"nodes": nodes, "relationships": relationships}


def sync_official_sources():
    """Build the canonical v2 Mainnet/Sepolia thesis graph."""
    from db.sync import synchronize

    ensure_schema()
    return synchronize()

def create_protocol(name):
    with get_session() as s:
        s.run("MERGE (:Protocol {name:$n, verified:true})", n=name)

def create_token(symbol):
    with get_session() as s:
        s.run("MERGE (:Token {symbol:$s})", s=symbol)

def create_pool(address, name, protocol, token_a, token_b, action="swap"):
    with get_session() as s:
        s.run("""
            MERGE (pool:Pool {address:$addr})
            SET pool.name=$name, pool.verified=true, pool.action=$action
            WITH pool
            MATCH (proto:Protocol {name:$proto})
            MATCH (ta:Token {symbol:$ta})
            MATCH (tb:Token {symbol:$tb})
            MERGE (proto)-[:DEPLOYED_CONTRACT]->(pool)
            MERGE (pool)-[:SWAPS_TOKEN]->(ta)
            MERGE (pool)-[:SWAPS_TOKEN]->(tb)
        """, addr=address, name=name, proto=protocol,
             ta=token_a, tb=token_b, action=action)

def add_malicious_test_pool(address, name):
    with get_session() as s:
        s.run("""
            MERGE (pool:Pool:MaliciousTest {address:$addr})
            SET pool.name=$name, pool.verified=false
        """, addr=address, name=name)

def seed_graph():
    print("Creating protocols...")
    create_protocol("Uniswap V3")
    create_protocol("Aave V3")

    print("Creating tokens...")
    for symbol in ["USDC", "WETH", "DAI", "WBTC"]:
        create_token(symbol)

    print("Creating verified pools...")
    create_pool(
        address  = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640",
        name     = "USDC/WETH 0.05%",
        protocol = "Uniswap V3",
        token_a  = "USDC",
        token_b  = "WETH"
    )
    create_pool(
        address  = "0xC2e9F25Be6257c210d7Adf0D4Cd6E3E881ba25f8",
        name     = "DAI/WETH 0.3%",
        protocol = "Uniswap V3",
        token_a  = "DAI",
        token_b  = "WETH"
    )
    create_pool(
        address  = "0x87870Bca3F3fD92394C0020B0ec9b4d71Fc3f5640",
        name     = "Aave V3 USDC pool",
        protocol = "Aave V3",
        token_a  = "USDC",
        token_b  = "USDC",
        action   = "supply"
    )

    print("Adding malicious test pools...")
    add_malicious_test_pool(
        "0xFake000000000000000000000000000000000001",
        "Official-Uniswap-USDC-WETH (FAKE)"
    )
    add_malicious_test_pool(
        "0xFake000000000000000000000000000000000002",
        "Aave-High-Yield-Scam-Pool (FAKE)"
    )

    print("Graph seeded successfully.")

if __name__ == "__main__":
    import json
    print(json.dumps(sync_official_sources(), indent=2))
