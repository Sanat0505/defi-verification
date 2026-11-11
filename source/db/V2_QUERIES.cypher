// 1. Thesis overview: exactly two families and four deployments.
MATCH path=(family:ProtocolFamily)-[:HAS_DEPLOYMENT]->
           (deployment:ProtocolDeployment)<-[:HOSTS]-(chain:Chain)
RETURN path;

// 2. Curated, readable demo scene (induced subgraph).
MATCH (view:GraphView {key:'thesis-demo-v2'})-[:INCLUDES]->(left)
MATCH path=(left)-[relationship]-(right)
WHERE EXISTS {
  MATCH (view)-[:INCLUDES]->(right)
}
RETURN path
LIMIT 250;

// 3. Full resources for one deployment. Change the key as needed.
MATCH root=(chain:Chain)-[:HOSTS]->
           (deployment:ProtocolDeployment {key:'uniswap-v3:11155111'})
OPTIONAL MATCH resource=(deployment)-[:HAS_POOL|HAS_RESERVE]->(item)
RETURN root, resource
LIMIT 100;

// 4. Inspect a Uniswap pool and both token relationships.
MATCH path=(deployment:ProtocolDeployment {key:'uniswap-v3:11155111'})
           -[:HAS_POOL]->(pool:Pool)-[:TOKEN0|TOKEN1]->(token:Token)
WHERE pool.featured=true
RETURN path;

// 5. Inspect featured Aave reserves and their contract/token relationships.
MATCH path=(deployment:ProtocolDeployment {key:'aave-v3:11155111'})
           -[:HAS_RESERVE]->(reserve:Reserve)-[relationship]->(child)
WHERE reserve.featured=true
RETURN path;

// 6. Small deterministic security-test scene.
MATCH (fixture:FixtureGraph {key:'fixture-root'})-[:INCLUDES]->(left)
MATCH path=(left)-[relationship]-(right)
WHERE right:FixtureNode
RETURN path
LIMIT 100;

// 7. Complete asset inventory; relationship type separates trusted from discovered-only.
MATCH (deployment:ProtocolDeployment)-[relationship:SUPPORTS_ASSET|DISCOVERED_ASSET]->(token:Token)
RETURN deployment.key AS deployment, token.symbol AS symbol,
       token.address AS address, token.decimals AS decimals,
       type(relationship) AS asset_status, token.source AS source,
       token.trust_source AS trust_source,
       token.verification_eligible AS verification_eligible
ORDER BY deployment, toLower(symbol), address, asset_status;

// 8. Authorized contract/function/action paths.
MATCH path=(deployment:ProtocolDeployment)-[deployed:DEPLOYED_CONTRACT]->
           (contract:Contract)-[:EXPOSES_FUNCTION]->
           (fn:Function)-[:IMPLEMENTS_ACTION]->(action:Action)
WHERE deployed.active=true
RETURN path;

// 9. Aave reserve and every published related-contract relationship.
MATCH path=(deployment:ProtocolDeployment {key:'aave-v3:11155111'})
           -[active:HAS_RESERVE]->(reserve:Reserve)-[relationship]->(child)
WHERE active.active=true AND reserve.active=true
RETURN path
LIMIT 500;

// 10. Uniswap discovery coverage and trust-filter counts.
MATCH (deployment:ProtocolDeployment {protocol_key:'uniswap-v3'})
RETURN deployment.key AS deployment,
       deployment.pool_discovery_complete AS complete,
       deployment.pool_discovery_mode AS mode,
       deployment.factory_scanned_to_block AS scanned_to_block,
       deployment.discovered_pool_count AS discovered,
       deployment.accepted_pool_count AS accepted,
       deployment.rejected_untrusted_pool_count AS rejected_untrusted,
       deployment.discovered_asset_count AS discovered_assets,
       deployment.trusted_asset_count AS trusted_assets;
