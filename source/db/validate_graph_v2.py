"""Audit canonical graph-v2 completeness and trust invariants.

Run after synchronization:
    python -m source.db.validate_graph_v2
"""

import json
import sys

from source.db.connection import get_session


INVENTORY_QUERY = """
MATCH (deployment:ProtocolDeployment)
WHERE deployment.graph_version='official-v2'
CALL (deployment) {
  OPTIONAL MATCH (deployment)-[rel:HAS_RESERVE]->(reserve:Reserve {active:true})
  WHERE rel.active=true
  RETURN count(DISTINCT reserve) AS active_reserves
}
CALL (deployment) {
  OPTIONAL MATCH (deployment)-[rel:HAS_POOL]->(pool:Pool {active:true})
  WHERE rel.active=true
  RETURN count(DISTINCT pool) AS active_pools,
         count(DISTINCT CASE WHEN pool.verification_eligible=true THEN pool END)
           AS verification_eligible_pools
}
CALL (deployment) {
  OPTIONAL MATCH (deployment)-[:SUPPORTS_ASSET]->(token:Token {verified:true})
  RETURN count(DISTINCT token) AS trusted_assets
}
CALL (deployment) {
  OPTIONAL MATCH (deployment)-[:DISCOVERED_ASSET]->(token:Token)
  RETURN count(DISTINCT token) AS discovered_assets
}
CALL (deployment) {
  OPTIONAL MATCH (deployment)-[rel:DEPLOYED_CONTRACT]->(contract:Contract)
  WHERE rel.active=true
  OPTIONAL MATCH (contract)-[:EXPOSES_FUNCTION]->(fn:Function {verified:true})
  RETURN count(DISTINCT contract) AS active_contracts,
         count(DISTINCT fn) AS authorized_functions
}
RETURN deployment.key AS deployment,
       active_reserves, active_pools, verification_eligible_pools,
       trusted_assets, discovered_assets,
       active_contracts, authorized_functions,
       deployment.pool_discovery_complete AS pool_discovery_complete,
       deployment.pool_discovery_mode AS pool_discovery_mode
ORDER BY deployment
"""

CHECKS = {
    "orphan_asset_support_nodes": """
        MATCH (orphan)-[:SUPPORTS_ASSET]->(:Token)
        WHERE labels(orphan)=[]
          AND NOT EXISTS { MATCH ()-[]->(orphan) }
          AND NOT EXISTS {
            MATCH (orphan)-[other]->()
            WHERE type(other) <> 'SUPPORTS_ASSET'
          }
        RETURN count(DISTINCT orphan) AS failures
    """,
    "aave_reserve_missing_underlying": """
        MATCH (:ProtocolDeployment {protocol_key:'aave-v3'})-[rel:HAS_RESERVE]->
              (reserve:Reserve {active:true})
        WHERE rel.active=true AND NOT EXISTS {
          MATCH (reserve)-[:UNDERLYING_ASSET]->(:Token {verified:true})
        }
        RETURN count(reserve) AS failures
    """,
    "aave_reserve_missing_supply_or_withdraw": """
        MATCH (:ProtocolDeployment {protocol_key:'aave-v3'})-[rel:HAS_RESERVE]->
              (reserve:Reserve {active:true})
        WHERE rel.active=true AND (
          NOT EXISTS { MATCH (reserve)-[:SUPPORTS_ACTION]->(:Action {name:'supply'}) }
          OR NOT EXISTS { MATCH (reserve)-[:SUPPORTS_ACTION]->(:Action {name:'withdraw'}) }
        )
        RETURN count(reserve) AS failures
    """,
    "aave_variable_debt_missing_borrow_or_repay": """
        MATCH (:ProtocolDeployment {protocol_key:'aave-v3'})-[rel:HAS_RESERVE]->
              (reserve:Reserve {active:true})-[:HAS_VARIABLE_DEBT_TOKEN]->(:Contract)
        WHERE rel.active=true AND (
          NOT EXISTS { MATCH (reserve)-[:SUPPORTS_ACTION]->(:Action {name:'borrow'}) }
          OR NOT EXISTS { MATCH (reserve)-[:SUPPORTS_ACTION]->(:Action {name:'repay'}) }
        )
        RETURN count(reserve) AS failures
    """,
    "uniswap_pool_invalid_token_endpoints": """
        MATCH (:ProtocolDeployment {protocol_key:'uniswap-v3'})-[rel:HAS_POOL]->
              (pool:Pool {active:true})
        WHERE rel.active=true
        OPTIONAL MATCH (pool)-[:TOKEN0]->(token0:Token)
        OPTIONAL MATCH (pool)-[:TOKEN1]->(token1:Token)
        WITH pool, count(DISTINCT token0) AS token0_count,
             count(DISTINCT token1) AS token1_count,
             collect(DISTINCT token0.address) + collect(DISTINCT token1.address) AS addresses
        WHERE token0_count <> 1 OR token1_count <> 1
           OR size(addresses) <> 2 OR addresses[0] = addresses[1]
        RETURN count(pool) AS failures
    """,
    "uniswap_pool_missing_fee_or_action": """
        MATCH (:ProtocolDeployment {protocol_key:'uniswap-v3'})-[rel:HAS_POOL]->
              (pool:Pool {active:true})
        WHERE rel.active=true AND (
          NOT EXISTS { MATCH (pool)-[:USES_FEE_TIER]->(:FeeTier) }
          OR NOT EXISTS { MATCH (pool)-[:SUPPORTS_ACTION]->(:Action {name:'swap'}) }
        )
        RETURN count(pool) AS failures
    """,
    "uniswap_pool_asset_missing_deployment_support": """
        MATCH (deployment:ProtocolDeployment {protocol_key:'uniswap-v3'})
              -[rel:HAS_POOL]->(pool:Pool {active:true, verification_eligible:true})
        MATCH (pool)-[:SUPPORTS_TOKEN]->
              (token:Token {verified:true, verification_eligible:true})
        WHERE rel.active=true AND NOT EXISTS {
          MATCH (deployment)-[:SUPPORTS_ASSET]->(token)
        }
        RETURN count(DISTINCT token) AS failures
    """,
    "uniswap_pool_trust_mismatch": """
        MATCH (:ProtocolDeployment {protocol_key:'uniswap-v3'})-[rel:HAS_POOL]->
              (pool:Pool {active:true})
        MATCH (pool)-[:TOKEN0]->(token0:Token)
        MATCH (pool)-[:TOKEN1]->(token1:Token)
        WHERE rel.active=true AND
          coalesce(pool.verification_eligible, false) <>
          (coalesce(token0.verification_eligible, false)
           AND coalesce(token1.verification_eligible, false))
        RETURN count(DISTINCT pool) AS failures
    """,
    "execution_role_missing_authorized_function": """
        MATCH (deployment:ProtocolDeployment)-[rel:DEPLOYED_CONTRACT]->(contract:Contract)
        WHERE deployment.graph_version='official-v2' AND rel.active=true
          AND ((deployment.protocol_key='aave-v3' AND rel.role='pool')
            OR (deployment.protocol_key='uniswap-v3' AND rel.role IN ['swap_router','quoter']))
          AND NOT EXISTS {
            MATCH (contract)-[:EXPOSES_FUNCTION]->(:Function {verified:true})
          }
        RETURN count(DISTINCT contract) AS failures
    """,
}


def validate():
    with get_session() as session:
        inventory = session.run(INVENTORY_QUERY).data()
        checks = {
            name: session.run(query).single()["failures"]
            for name, query in CHECKS.items()
        }
    return {
        "valid": all(value == 0 for value in checks.values()),
        "inventory": inventory,
        "checks": checks,
    }


if __name__ == "__main__":
    result = validate()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)
