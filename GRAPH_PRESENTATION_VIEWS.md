# Two separate presentation views

Both views select nodes from the same canonical Neo4j database. They are named
presentation selections, not database copies. Rebuilding changes only their
membership links. Legacy seeded nodes and fixture scenarios are not selected.

The stored view keys are `small-verification` and `large-graph`. To check the
actual stored keys and memberships, including empty views:

```cypher
MATCH (view:GraphView)
OPTIONAL MATCH (view)-[:INCLUDES]->(node)
RETURN view.key AS key, count(DISTINCT node) AS nodes
ORDER BY key;
```

## Small: explain one verification

Open `db/SMALL_VERIFICATION_VIEW.cypher`, copy the query into Neo4j Browser,
and run it in the database configured by the application.

Example: "Supply USDC to Aave V3 on Sepolia."
Show the network, protocol family, deployment, supply action, Pool contract,
supply function, USDC reserve and token. Explain how the function and reserve
connect to the same deployment and action. This is structural relationship
verification; amount validation and live reserve configuration are separate.
After approval, the application can construct and submit Aave V3 `supply`,
`withdraw`, `borrow`, and `repay` calls through the Sepolia ERC-4337 wallet.

## Large: show the populated knowledge graph

Open `db/LARGE_PROPERTY_GRAPH_VIEW.cypher`, copy the query into a separate
Neo4j Browser query card, and run it. It returns the selected graph's relationships
without a query limit. Browser display limits may still hide nodes; use the
inventory command below to establish actual size.

This view contains Mainnet and Sepolia protocol deployments, contracts,
functions, actions, reserves, discovered pool/token relationships and fee tiers.
The displayed graph is a stored snapshot. Uniswap Mainnet coverage remains
curated until a full RPC synchronization is performed. Discovered Uniswap assets
and pools are not automatically verification-eligible. Inspect their
`verification_eligible` properties when discussing the trust policy.

## Refresh selections and inspect counts

```powershell
python -m db.presentation_views
python -m db.validate_graph_v2
```

The first command rebuilds both selections from existing data and checks both
display queries. It does not fetch official sources or submit transactions.
The normal synchronization entry points rebuild the separate demonstration
and fixture graphs; run `db.presentation_views` explicitly when these two
presentation selections need rebuilding.

In Neo4j Browser, list the view membership counts:

```cypher
MATCH (view:GraphView)-[:INCLUDES]->(node)
WHERE view.key IN ['small-verification', 'large-graph']
RETURN view.name AS view, count(DISTINCT node) AS nodes;
```
