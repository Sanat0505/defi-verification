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
                          │                       └─ EXPOSES_FUNCTION → Function
                          │                                                  └─ IMPLEMENTS_ACTION → Action
                          ├─ SUPPORTS_ASSET → Token
                          ├─ SUPPORTS_ACTION → Action
                          ├─ HAS_POOL → Pool
                          └─ HAS_RESERVE → Reserve

Pool
  ├─ TOKEN0 → Token
  ├─ TOKEN1 → Token
  ├─ USES_FEE_TIER → FeeTier
  ├─ SUPPORTS_ACTION → Action
  └─ Factory ─ CREATED_POOL → Pool

Reserve
  ├─ UNDERLYING_ASSET → Token
  ├─ HAS_A_TOKEN → Contract
  ├─ HAS_VARIABLE_DEBT_TOKEN → Contract
  ├─ HAS_STABLE_DEBT_TOKEN → Contract
  ├─ HAS_STATIC_A_TOKEN → Contract
  ├─ USES_ORACLE → Contract
  ├─ USES_INTEREST_RATE_STRATEGY → Contract
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

Run `python -m db.sync` to synchronize all three layers. Useful Neo4j
visualization queries are in `db/V2_QUERIES.cypher`.

## Mainnet pool ingestion

The Aave loader reads every current core contract constant and every reserve
from the official Aave address book. This includes mixed-case symbols such as
`wstETH` and related aToken, variable/stable debt token, oracle, static aToken,
and interest-rate-strategy contracts when the address book publishes them.

Uniswap V3 is permissionless, so "every Uniswap asset" is not a safe allowlist:
anyone can deploy a token and create a pool. The canonical graph stores every
factory-discovered pool, token endpoint, fee tier, and relationship as the
discovery layer. A pool becomes verification-eligible only when both endpoint
assets are independently trusted by the active Aave reserve list (canonical
WETH is also admitted). The deployment stores discovered, accepted, and
rejected pool counts so this boundary is auditable.

Set both `MAINNET_RPC` and `SEPOLIA_RPC` for complete factory scans. Without a
Mainnet RPC, only the two curated real Mainnet pools are available and the
deployment is explicitly marked `pool_discovery_complete=false`; it must not be
described as complete in the evaluation.

Each synchronization marks old reserve, pool, and deployment-contract
relationships inactive before reactivating current official data. The verifier
uses only active relationships and also requires an authorized ABI function and
selector, not merely a trusted contract address.

After loading, run `python -m db.validate_graph_v2`. It prints the per-deployment
asset/contract/pool/function inventory and exits non-zero if a required
relationship is missing.

The legacy nodes remain available for comparison, but application verification
now queries only `ProtocolFamily` and `ProtocolDeployment` from the v2 model.
