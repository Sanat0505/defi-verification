// Check these timestamps before interpreting the structural example as approval.
MATCH (deployment:ProtocolDeployment {graph_version:'official-v2'})
RETURN deployment.key AS deployment,
       deployment.verified AS verified,
       deployment.last_successful_sync_at AS last_successful_sync_at,
       deployment.last_sync_status AS last_sync_status,
       deployment.asset_coverage AS asset_coverage,
       deployment.pool_discovery_complete AS pool_discovery_complete,
       deployment.source_url AS source_url
ORDER BY deployment;
