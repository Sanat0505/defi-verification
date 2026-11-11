// Larger presentation: all selected active canonical resources and discovered pools.
// No query LIMIT. Neo4j Browser may still cap the rendered node count.
// Discovery does not imply verification eligibility or transaction feasibility.
MATCH (view:GraphView {key:'large-graph'})-[:INCLUDES]->(left)
MATCH path=(left)-[rel:HOSTS|DEPLOYED_ON|HAS_DEPLOYMENT|DEPLOYED_CONTRACT|
  SUPPORTS_ACTION|SUPPORTS_ASSET|DISCOVERED_ASSET|HAS_POOL|HAS_RESERVE|
  EXPOSES_FUNCTION|IMPLEMENTS_ACTION|UNDERLYING_ASSET|TOKEN0|TOKEN1|SUPPORTS_TOKEN|
  HAS_A_TOKEN|HAS_VARIABLE_DEBT_TOKEN|HAS_STABLE_DEBT_TOKEN|HAS_STATIC_A_TOKEN|
  USES_ORACLE|USES_INTEREST_RATE_STRATEGY|USES_FEE_TIER|CREATED_POOL|
  REPRESENTS_ASSET|DEBT_FOR|PRICES|CONFIGURES_RATES_FOR]->(right)
WHERE EXISTS { MATCH (view)-[:INCLUDES]->(right) }
  AND coalesce(rel.active,true)
RETURN path;
