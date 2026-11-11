"""Schema setup, graph inventory, and official-source synchronization."""

from source.db.connection import get_session

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
    from source.db.sync import synchronize

    ensure_schema()
    return synchronize()


if __name__ == "__main__":
    import json
    print(json.dumps(sync_official_sources(), indent=2))
