# Graph evidence and digital appendix

For an inspectable copy of the constructed Neo4j graph, start with
[submission/README.md](submission/README.md). It includes the submission database
dump, read-only Cypher queries, graph figures, counts and a recorded verifier result.

The existing files in this directory retain their original roles:

| Material | Entry point |
|---|---|
| Final paired verification and traceability study | [POST_CHANGE_REPORT.md](POST_CHANGE_REPORT.md) |
| Paired case-level observations | [regression_results.json](regression_results.json) |
| Raw graph-call journal | [calls.jsonl](calls.jsonl) |
| Original controlled relationship and lifecycle study | [controlled_D_E.json](controlled_D_E.json) |
| Independent graph references | [independent_graph_references.json](independent_graph_references.json) |
| Historical graph observations | [snapshot-20261019T135654936964Z.json](snapshot-20261019T135654936964Z.json) |

The new submission export is dated separately. It does not replace these historical
observations and is not claimed to be the exact database used for earlier experiments.
Historical JSON snapshots summarize selected facts; they are not native database dumps.
