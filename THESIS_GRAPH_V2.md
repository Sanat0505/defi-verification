# Thesis Knowledge Graph v2

The v2 ontology separates a protocol concept from each chain-specific
deployment. It is built alongside the legacy graph, so migration is
non-destructive.

## Canonical official graph

```text
ProtocolFamily
  └─ HAS_DEPLOYMENT → ProtocolDeployment
                          ├─ DEPLOYED_ON → Chain
Chain ─ HOSTS ────────────┘
                          ├─ DEPLOYED_CONTRACT → Contract
                          ├─ SUPPORTS_ACTION → Action
                          ├─ HAS_POOL → Pool
                          └─ HAS_RESERVE → Reserve

Pool
  ├─ TOKEN0 → Token
  ├─ TOKEN1 → Token
  └─ Factory ─ CREATED_POOL → Pool

Reserve
  ├─ UNDERLYING_ASSET → Token
  ├─ HAS_A_TOKEN → Contract
  ├─ HAS_VARIABLE_DEBT_TOKEN → Contract
  ├─ HAS_STATIC_A_TOKEN → Contract
  ├─ USES_ORACLE → Contract
  └─ SUPPORTS_ACTION → Action
```

The four deployment keys are:

- `uniswap-v3:1`
- `uniswap-v3:11155111`
- `aave-v3:1`
- `aave-v3:11155111`

## Three graph layers

1. The canonical graph contains official Mainnet and Sepolia deployments.
2. `GraphView {key: 'thesis-demo-v2'}` selects a readable subset of real data.
3. `FixtureGraph {key: 'fixture-root'}` contains deterministic approved and
   blocked security scenarios without influencing the main verifier.

Run `python -m db.graph_builder` to synchronize all three layers. Useful Neo4j
visualization queries are in `db/V2_QUERIES.cypher`.

## Mainnet pool ingestion

Official Mainnet Aave contracts and all 28 address-book reserves load without
an RPC. Uniswap core contracts and two curated real pools also load. Set
`MAINNET_RPC` to scan every `PoolCreated` event from the official Mainnet V3
factory. `SEPOLIA_RPC` performs the equivalent complete Sepolia scan.

The legacy nodes remain available for comparison, but application verification
now queries only `ProtocolFamily` and `ProtocolDeployment` from the v2 model.
