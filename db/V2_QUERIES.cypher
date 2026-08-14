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
