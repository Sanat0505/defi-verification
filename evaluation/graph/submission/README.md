# Constructed Neo4j graph: submission materials

This package lets a reviewer inspect the graph underlying the prototype, see one
relationship-verification example, and restore a native database copy. It was
prepared on **11 November 2026** from the local `neo4j` user database using
**Neo4j 2026.05.0 Enterprise** and Desktop **2.3.0**.

This is a submission snapshot, not a claim that the database is identical to the
state used in the October experiments. Existing evidence in the parent directory
is unchanged. The source database was inspected read-only and returned to its
original stopped state; no synchronization, model calls or wallet execution were run.

## What is included

| File or directory | Purpose |
|---|---|
| `database/neo4j.dump` | Native export of the complete `neo4j` user database; excludes the `system` database and other local databases |
| `database/export_metadata.json` | Export hash, software version and validation record |
| `queries/01_overview.cypher` | Eight-node overview of protocol families, deployments and networks |
| `queries/02_aave_supply.cypher` | Eight-node, nine-relationship Aave V3 USDC supply example on Sepolia |
| `queries/03_node_counts.cypher` | Whole-database counts by node label |
| `queries/04_relationship_counts.cypher` | Whole-database counts by relationship type |
| `queries/05_knowledge_state.cypher` | Deployment provenance, synchronization and coverage information |
| `evidence/` | Saved query results, CSV counts, inventory and the actual verifier decision |
| `figures/` | PNG and SVG diagrams generated from the saved query results |
| `capture_graph.py` | Read-only script to capture a new inspection in a separate directory |
| `render_figures.py` | Offline figure renderer using Pillow |
| `MANIFEST.sha256` | Checksums for the retained submission files |

## Inspect without installing Neo4j

Open [the overview](figures/overview.png) and
[the Aave supply example](figures/aave_supply.png). These are data-derived diagrams,
not Neo4j screenshots or a visualization of the complete database. Their nodes and
directed edges come from the corresponding saved query results in `evidence/`.
The full node properties, including complete addresses, remain in the JSON files.
The diagrams select one main label per node; the JSON preserves every node label.

The inspected user database contains **3,736 nodes and 20,729 relationships**.
These are whole-database totals, including presentation and fixture metadata.
The label counts may sum to more than the node total because nodes can have
multiple labels. Counts are provided in `evidence/node_counts.csv` and
`evidence/relationship_counts.csv`; they must not be inferred from a displayed
subgraph or a visualization tool's rendering limit.

## Explain relationship verification

Use the illustrative request: **Supply 10 USDC to Aave V3 on Ethereum Sepolia.**

The focused graph connects the Sepolia chain to the Aave deployment, the
deployment to the authorized Pool contract, the contract to its `supply` function,
and that function to the supported action. A separate connected branch links the
same deployment to the active USDC reserve and its underlying token. Both the
deployment and the reserve support the supply action.

This structural selection is not the complete approval algorithm. The saved
[verifier result](evidence/verification_example.json) records a direct reference-intent
call, without LLM extraction or amount validation. Its actual decision was
**INSUFFICIENT_EVIDENCE**, with rule **KNOWLEDGE.STALE**: the last successful Aave
Sepolia synchronization was on 22 October 2026, outside the configured 168-hour
freshness limit. No timestamps or freshness policy were changed to obtain approval.

Use the structural figure to explain the relationships and the decision record to
explain the additional freshness prerequisite. For historical positive and negative
controlled results, use [the paired report](../POST_CHANGE_REPORT.md) and its
[case-level evidence](../regression_results.json). Graph approval does not establish
sufficient funds, collateral, wallet authorization or successful on-chain execution.

Suggested figure captions:

> Selected protocol families, network deployments and chain relationships returned
> by a read-only query of the submission graph. The view contains eight nodes and
> eight relationships; it is not the complete database.

> Stored relationship paths for Aave V3 USDC supply on Ethereum Sepolia. The selected
> subgraph connects the deployment, authorized contract and function, supported action,
> reserve and underlying token. These structural relationships do not by themselves
> satisfy the verifier's knowledge-freshness prerequisite.

## Restore and inspect in Neo4j Desktop 2

1. Use a separate Desktop instance, preferably Neo4j **2026.05.0 Enterprise**, matching
   the export. The database uses that release's store format; older-version
   compatibility has not been established.
2. Stop the target instance. Make a copy of `database/neo4j.dump` outside this retained
   package and name the copy `thesis-graph-submission.dump`.
3. In the target instance menu, choose **Load database from file**, select the renamed
   copy and import it. Desktop derives the new database name from the filename.
   Choose a name that does not already exist; do not replace your working database.
4. Start the instance if needed. Open **Query**, connect using that instance's own
   credentials and select **thesis-graph-submission** explicitly. The dump does not
   contain the source instance's `system` database or login configuration.
5. Run `03_node_counts.cypher` and `04_relationship_counts.cypher` in Table view.
   Compare their results with the included CSV files.
6. Run `01_overview.cypher`, then `02_aave_supply.cypher`, in Graph view. These queries
   use domain data directly and do not require creating presentation selections.
7. Run `05_knowledge_state.cypher` and inspect the timestamps before interpreting
   any graph-path match as a current verification approval.

Desktop import instructions are based on the official
[database-management documentation](https://neo4j.com/docs/desktop/current/operations/database-management/).
The export was loaded into a separate temporary data directory and checked with
Neo4j's offline consistency checker. The Desktop import flow above was not itself
automated. See `database/export_metadata.json` for the precise completed checks.

## Reproduce the figures or capture a new inspection

From the repository root, with Python active, install the optional renderer dependency:

```text
python -m pip install -r evaluation/graph/submission/requirements-figures.txt
python -B -m evaluation.graph.submission.render_figures --output .cache/graph-figures
```

This renders the retained query results without contacting Neo4j. PNG figures are
provided at 2640 by 2200 pixels; SVG files preserve vector text and shapes.

To capture a new database inspection, configure the root `.env` as described in the
repository README, start the chosen database and use a **new** output directory:

```text
python -B -m evaluation.graph.submission.capture_graph --database thesis-graph-submission --output .cache/graph-inspection-new
```

The script refuses to overwrite an existing output directory. It runs read-only
queries and the relationship verifier, without synchronization or wallet calls.
New decisions may differ as the freshness window advances or graph contents change.

Verify the retained package together with the historical evaluation evidence:

```text
python -B -m evaluation.check_integrity
```

That repository-wide check also needs the pinned public inputs documented in the
root README. For a direct dump check in PowerShell, use
`Get-FileHash evaluation/graph/submission/database/neo4j.dump -Algorithm SHA256`
and compare it with the export metadata.
