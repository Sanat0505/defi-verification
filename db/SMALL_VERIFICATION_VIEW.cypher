// Small presentation: one Aave USDC supply relationship-verification example.
// Graph approval does not imply lending execution is implemented.
MATCH (view:GraphView {key:'small-verification'})-[:INCLUDES]->(left)
MATCH path=(left)-[rel:HOSTS|DEPLOYED_ON|HAS_DEPLOYMENT|DEPLOYED_CONTRACT|
  SUPPORTS_ACTION|HAS_RESERVE|UNDERLYING_ASSET|EXPOSES_FUNCTION|IMPLEMENTS_ACTION]->(right)
WHERE EXISTS { MATCH (view)-[:INCLUDES]->(right) }
  AND coalesce(rel.active,true)
RETURN path;
