// Read-only overview of canonical protocol families, deployments and networks.
// This is a selected subgraph, not the complete database or a verification rule.
MATCH path=(family:ProtocolFamily)-[:HAS_DEPLOYMENT]->
  (deployment:ProtocolDeployment {graph_version:'official-v2'})<-[:HOSTS]-(chain:Chain)
RETURN path;
