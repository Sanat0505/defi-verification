"""Build two presentation selections over the existing canonical graph.

Run: python -m db.presentation_views
Only these views' INCLUDES relationships are replaced; domain data is shared.
"""

import json
from pathlib import Path

from db.connection import get_session

SMALL_KEY = "small-verification"
LARGE_KEY = "large-graph"

SMALL_SELECTION = """
MATCH (family:ProtocolFamily)-[:HAS_DEPLOYMENT]->
      (d:ProtocolDeployment {key:'aave-v3:11155111', verified:true})
MATCH (chain:Chain)-[:HOSTS]->(d)
MATCH (d)-[:SUPPORTS_ACTION]->(action:Action {name:'supply'})
MATCH (d)-[:DEPLOYED_CONTRACT {role:'pool', active:true}]->
      (contract:Contract {verified:true})-[:EXPOSES_FUNCTION]->
      (fn:Function {verified:true, purpose:'execute'})-[:IMPLEMENTS_ACTION]->(action)
MATCH (d)-[:HAS_RESERVE {active:true}]->(reserve:Reserve {active:true, verified:true})
      -[:UNDERLYING_ASSET]->(token:Token {symbol:'USDC', verified:true})
MATCH (reserve)-[:SUPPORTS_ACTION]->(action)
WITH collect(DISTINCT [family, chain, d, action, contract, fn, reserve, token]) AS groups
UNWIND groups AS members
UNWIND members AS node
RETURN DISTINCT node
"""

LARGE_SELECTION = """
MATCH (d:ProtocolDeployment {graph_version:'official-v2'})
CALL (d) {
  MATCH path=(d)-[:DEPLOYED_ON|DEPLOYED_CONTRACT|SUPPORTS_ACTION|HAS_POOL|HAS_RESERVE|
    EXPOSES_FUNCTION|IMPLEMENTS_ACTION|UNDERLYING_ASSET|TOKEN0|TOKEN1|SUPPORTS_TOKEN|
    HAS_A_TOKEN|HAS_VARIABLE_DEBT_TOKEN|HAS_STABLE_DEBT_TOKEN|HAS_STATIC_A_TOKEN|
    USES_ORACLE|USES_INTEREST_RATE_STRATEGY|USES_FEE_TIER*0..3]->(node)
  WHERE all(rel IN relationships(path) WHERE coalesce(rel.active,true))
    AND all(n IN nodes(path) WHERE coalesce(n.active,true))
  RETURN node
  UNION
  WITH d
  MATCH (node:ProtocolFamily)-[:HAS_DEPLOYMENT]->(d)
  RETURN node
}
RETURN DISTINCT node
"""


def _build(tx):
    counts = {}
    for key, name, selection in (
        (SMALL_KEY, "One verification - Aave USDC supply on Sepolia", SMALL_SELECTION),
        (LARGE_KEY, "Larger graph - Mainnet and Sepolia inventory", LARGE_SELECTION),
    ):
        # Validate selection before replacing membership; the transaction is atomic.
        node_ids = [record["node"].element_id for record in tx.run(selection)]
        if not node_ids:
            raise ValueError(f"No data for {key}; synchronize the canonical graph first")
        tx.run(
            """
            MERGE (view:GraphView {key:$key})
            SET view.name=$name, view.graph_version='official-v2',
                view.last_built_at=toString(datetime()), view.member_count=$count,
                view.purpose='presentation only'
            WITH view
            OPTIONAL MATCH (view)-[old:INCLUDES]->()
            DELETE old
            """,
            key=key, name=name, count=len(node_ids),
        ).consume()
        tx.run(
            """
            MATCH (view:GraphView {key:$key})
            UNWIND $ids AS id
            MATCH (node) WHERE elementId(node)=id
            MERGE (view)-[:INCLUDES]->(node)
            """,
            key=key, ids=node_ids,
        ).consume()
        counts[key] = len(node_ids)
    return counts


def build_presentation_views():
    with get_session() as session:
        counts = session.execute_write(_build)
        # Execute the exact display queries as a read-only smoke check.
        for key, filename in (
            (SMALL_KEY, "SMALL_VERIFICATION_VIEW.cypher"),
            (LARGE_KEY, "LARGE_PROPERTY_GRAPH_VIEW.cypher"),
        ):
            query = Path(__file__).with_name(filename).read_text(encoding="utf-8")
            edges = sum(1 for _ in session.run(query))
            if edges == 0:
                raise ValueError(f"Display query returned no relationships for {key}")
            counts[key] = {"nodes": counts[key], "relationships": edges}
    return counts


if __name__ == "__main__":
    print(json.dumps(build_presentation_views(), indent=2))
