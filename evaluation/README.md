# Completed evaluations

For the native Neo4j submission export, inspection queries and graph figures, see
the [graph directory guide](graph/README.md). The submission snapshot is separate
from the historical experiments described below.

Start with the completed reports below. Files in these six directories are retained
evidence; active Python runners remain at this directory's top level. Installation,
configuration and application usage are in the [root README](../README.md).

Application code lives in [source/](../source/README.md). Active runners import
that implementation through `source.*`; they do not maintain a second copy.
Tests for runners, datasets and evidence are in [tests/](tests/), while application
tests are in [source/tests/](../source/tests/). Run this folder's tests from the
repository root with `python -B -m pytest -q evaluation/tests`.

The files under `sources/` and the source ZIPs are historical evidence. Their
original imports and paths are preserved. The paired traceability runner resolves
the frozen verifier's old imports temporarily when loading it; new runs record
the current `source/` paths and hashes. Do not resume a historical run with the
reorganized implementation.

| Evaluation | Canonical report | Dataset / references | Authoritative observations and metrics |
|---|---|---|---|
| 400 prompts | [SUMMARY.md](400_prompts/SUMMARY.md) | [Frozen 400 prompts](400_prompts/dataset_snapshot.json) | [results.json](400_prompts/results.json), [analysis.json](400_prompts/analysis.json) |
| 600 prompts | [SUMMARY.md](600_prompts/SUMMARY.md), [completion](600_prompts/COMPLETION.md) | [Frozen 600 prompts](600_prompts/dataset_snapshot.json), [run order](600_prompts/run_order_snapshot.json) | [results.json](600_prompts/results.json), [analysis.json](600_prompts/analysis.json) |
| Graph relationships and knowledge maintenance | [Final paired report](graph/POST_CHANGE_REPORT.md) | [Controlled references](graph/controlled_references.json), [independent references](graph/independent_graph_references.json) | [regression_results.json](graph/regression_results.json), [924-call journal](graph/calls.jsonl), [analysis](graph/analysis.json) |
| Supplementary wallet fixtures | [Wallet report](wallet/wallet-evaluation-20261019T140020Z.md) | [31 scenarios](datasets/wallet_cases.json) | [JSON](wallet/wallet-evaluation-20261019T140020Z.json), [CSV](wallet/wallet-evaluation-20261019T140020Z.csv) |

The prompt studies combine LLM interpretation/validation, pipeline decisions and
independent graph checks: 220 reference checks for the 400 run; 340 for the 600 run.
References are draft labels and paired prompts are not independent trials.
[Detailed 600 analysis](600_prompts/CHAPTER_5_DRAFT.md), [error review](600_prompts/ERROR_REVIEW.md),
[all-case audit](600_prompts/all_600_case_audit.json) and [paired analysis](600_prompts/paired_300_analysis.json)
are supporting views, not additional experiments. Each prompt folder also retains
raw model/graph journals, snapshots, environment and exact source ZIP.

The graph folder also holds the original
[72 relationship and 36 lifecycle observations](graph/controlled_D_E.json),
[original references](graph/original_controlled_references.json),
[setup](graph/controlled_setup_failure.json) and [cleanup recovery](graph/controlled_cleanup_failure.json),
plus the later [diagnostic review](graph/review_2026-10-27.json) and
[knowledge audit](graph/knowledge_audit.json). The final paired study is separate
from the original controlled study and both prompt experiments. Wallet results
cover 28 implemented checks and three declared gaps; no transaction was broadcast.

## Inspect and verify without rerunning experiments

Open the Markdown, JSON or CSV files directly. With dependencies and pinned inputs
installed as described in the root README:

```text
python -B -m evaluation.check_integrity
python -B -m evaluation.sourced_runner --validate-only
python -B -m pytest -q
```

[MANIFEST.sha256](MANIFEST.sha256) covers 128 retained evidence files. The checker
also verifies three source ZIPs, their 145 recorded source members, and four pinned
public inputs. [sources/](sources/) preserves source identities, licenses, original
graph/wallet runtime details and frozen before/after implementations.

Historical paths inside frozen JSON and reports identify the original run layout;
they have not been rewritten. Superseded runs, duplicate packages, original package
manifests and the obsolete mixed report are retained only in the external recovery
backup. On the cleanup machine this is
`C:\Users\lenovo\.codex\visualizations\2026\10\28\01a18356-2e98-7b70-bcc7-642eb58517ea\evaluation-stage1-stage2\repaired-working-tree.zip`,
with its checksum, original-path manifest and Git bundle alongside it. It is not
needed for routine inspection or current tests. Obtain it from the project maintainer
when reproducing an original historical package in its original layout.

## Intentional reproduction

Run from the repository root. New outputs default to ignored
`.cache/evaluation-runs/` directories. Never point output or resume options at
retained evidence. These live commands have checked CLI options but were **not
executed against external services during cleanup**.

A three-case smoke run requires Groq, Neo4j and fresh admitted knowledge:

```text
python -m evaluation.runner --limit 3 --repeats 1 --output-dir .cache/evaluation-runs/smoke
```

Full prompt runs are explicit, potentially costly operations:

```text
python -m evaluation.exploratory_400_runner --dataset evaluation/400_prompts/dataset_snapshot.json --output-root .cache/evaluation-runs/400_prompts --allow-unreviewed
python -m evaluation.balanced_600_runner --dataset evaluation/600_prompts/dataset_snapshot.json --output-root .cache/evaluation-runs/600_prompts --allow-unreviewed
```

`--allow-unreviewed` acknowledges draft references; it does not establish human
review. Both runners enforce graph/reference prerequisites. The 600 runner also
checks frozen ordering, authorization and the construction-snapshot hash. A changed
graph can correctly block reproduction. Resume requires matching code, inputs and
graph state; do not combine historical checkpoints with changed code. Fresh model
responses can differ. Neither prompt runner signs or broadcasts.

| Other entry point | Requirements and effects |
|---|---|
| `python -m evaluation.graph_runner --repeats 1` | Live Neo4j reference checks; no LLM, database mutation or broadcast |
| `python -m evaluation.wallet_runner` | Offline Node/Python fixtures; temporary test policy and mocked external outcomes; no broadcast |
| `python -m evaluation.controlled_graph --snapshot evaluation/graph/snapshot-20261019T135654936964Z.json` | Controlled relationship/lifecycle study; owned fixtures in the separately provisioned `thesis-eval-20261019` database |
| `python -m evaluation.traceability_runner` | Paired before/current-verifier study; separately provisioned `thesis-eval-20261024` database and live graph reads |

Controlled harnesses require named-database support, access to the production
`neo4j` database for fingerprints, and isolated fixture databases with appropriate
permissions. They retain ownership guards and refuse to overwrite completed outputs.
They are manual experiments, not offline tests. A future paired run compares the
saved before-verifier with the current implementation; use the external original-layout
backup for exact historical code reproduction.

Optional offline analysis scripts accept a **separate run folder**:
`python -m evaluation.analyse_exploratory_400 <run-folder>` and
`python -m evaluation.analyse_balanced_600 <run-folder>`. They write derived files;
do not run them on preserved evidence. Install
[requirements-analysis.txt](sources/requirements-analysis.txt) when plotting is needed.
