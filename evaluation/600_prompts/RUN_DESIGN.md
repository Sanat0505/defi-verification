# Proposed balanced one-pass evaluation

Status: preparation only, 22 October 2026. Final execution has not started.

## Amendment and scope

The earlier plan proposed 400 prompts, 200 families and three passes. The
deadline-driven follow-up proposes 600 prompts, 300 paired scenario instances
and one pass, with 100 prompts in each of six categories. One pass cannot measure
same-prompt repeatability. Pair agreement measures wording consistency only.
Record this change explicitly rather than silently overwriting the original
plan. The supervisor's prospective power assumptions do not transfer unchanged.

Use the current GPT-OSS 20B extraction model, system prompt and configuration.
Do not substitute another model for a quota-limited segment. Capture model ID,
response-reported model, settings, raw outputs, token usage, attempts, timestamps,
source-file hashes, dependency versions, dataset hashes and graph snapshots.

The initial dataset contains 247 proposed semantic clusters; this is a screening
result, not proof of 247 independent cases. Report 300 scenario instances and 600
formulations separately. Human review must adjudicate meaningful diversity and
prior-template overlap. Results describe this deliberately constructed test set,
not the population distribution of DeFi requests.

## Reference review and freeze

For each scenario review A and B for equivalent meaning; confirm action,
protocol, chain, asset direction, amount, omissions, uncertainty and conditions.
Confirm validation and final outcomes separately. Explicit slippage must be
preserved; omitted slippage remains absent in extraction and the preparation
default is outside this evaluation. Include understandable valid slippage
wording even when the unchanged implementation is known to mishandle it.

Official operation documentation does not define the prototype's 1-500 basis
point bound, single-network scope, graph admission rules, or validation labels.
Those are local policies and must be described accordingly. All graph references
are conditional on the exported admitted snapshot, freshness and coverage.

The source URLs checked during preparation are:

- https://developers.uniswap.org/docs/protocols/v3/guides/swapping/single-hop-swapping
- https://aave.com/docs/aave-v3/smart-contracts/pool
- https://developers.uniswap.org/docs/protocols/v3/deployments/v3-ethereum-deployments

These support protocol semantics/deployment context, not all individual labels.
Snapshot source URLs and addresses are saved in the graph preflight artifacts.

After review, retain this draft and create a separately versioned frozen dataset.
Record reviewer, timestamp, changes, excluded/replaced cases and final hashes.
The review sheet alone does not change JSON references. Resolve mismatches before
freezing. Do not repair references after observing model outcomes without
reporting the adjudication and preserving original results.

## Execution stages

A: One logical extraction call per prompt. Save raw model text and parsed output,
normalization/validation outcome, field comparisons and condition-preservation
review. Record parsing, schema, service and semantic errors separately.

B: For eligible complete reference intents, run the Neo4j verifier directly,
independently of the extraction result. The draft currently has 340 prompt-level
checks and 112 distinct graph keys. These numbers must be recomputed after review.
Compare decisions and evidence against reviewed exported facts, not against the
verifier's own predictions. No relationship mutations in the live graph.

C: Reuse each actual A resolution in the unchanged pipeline, including mistakes.
Do not call the model again or replace a failed extraction with the reference.
Keep every case's A and C records linked. No wallet calls or transaction submission.

Run order is saved in `data/planned_run_order.json`: deterministic seed 20261022,
interleaved six-category blocks, paired formulations adjacent, randomized A/B
order. A is the designated primary formulation even if B happens to execute first.
This spreads categories across quota windows and avoids always running all A
prompts on one day and all B prompts on another. It does not eliminate temporal
effects or graph-cache effects. Record those limitations.

Checkpoint after each case. Preserve actual failed attempts and completed cases
on resume. Stop at a daily-quota response rather than repeatedly consuming calls.
If later retries are permitted, define their analysis before running; preserve
the original attempt and report eventual recovery separately. Pending cases at a
deadline are unattempted, not false negatives or true negatives. Do not fill their
results from expected labels. Keep model, graph and dataset fixed across segments.

The previous token average suggests roughly 711,000 total tokens for 600
successful calls before retries; it is an estimate, not an account quota check.
The current account's allowance must be verified before scheduling execution.

## Analysis denominators

Report all scheduled, attempted, completed, failed and unattempted cases.
Keep the 400-prompt exploratory results in their original report. Do not pool
the two datasets as independent observations or claim a causal before/after gain.

Exact status: compare APPROVED, REJECTED, UNSUPPORTED, NEEDS_CLARIFICATION,
INSUFFICIENT_EVIDENCE and ERROR as distinct outcomes where applicable. Use a full
confusion matrix and category counts/rates. Operational errors count against
completion and overall exact agreement, not as correct semantic rejections.

Binary decision analysis: positive means approval. TP is an expected approval
that was approved; FN is an expected approval that received a semantic
non-approval; FP is an expected non-approval that was approved; TN is an expected
non-approval that received a semantic non-approval. Keep provider failures,
database outages and unavailable-evidence abstentions visible outside the 2x2
matrix. Show each excluded case and reason, and report decision coverage over
all attempted prompts. An outage surfaced as INSUFFICIENT_EVIDENCE is still an
operational failure. A missing-evidence abstention is not automatically a correct
negative merely because it withholds approval.

Report precision TP/(TP+FP), recall TP/(TP+FN), specificity TN/(TN+FP), false
positive rate FP/(FP+TN), false negative rate FN/(FN+TP), F1
2TP/(2TP+FP+FN), and binary accuracy (TP+TN)/(TP+TN+FP+FN). Zero denominators are
undefined, not perfect scores. Also report unresolved errors/abstentions by
reference-positive/negative class. A supplementary approval-versus-any-withheld
analysis may include them only under an explicit different operational definition.

An incorrect REJECTED instead of NEEDS_CLARIFICATION can be a binary TN while
failing exact status. Neither metric establishes correct semantic extraction.
Report field and condition preservation separately. A status-only match on an
unsupported request must not be called entirely correct intent understanding.
Free-text unsupported-condition labels require semantic review, not literal
string equality. Preserve all stated conditions, including those outside schema.

Report both all-formulation and primary-formulation results, paired consistency,
category breakdowns and an error table with the earliest evidenced failure stage.
Do not infer that a verifier is at fault merely because C is wrong when A supplied
the wrong intent. Do not treat a reference ambiguity as a confirmed software fault.

## Graph timing and uncertainty

R6 is unchanged: at least 95% of eligible graph decisions within 2,000 ms,
excluding LLM and wallet time. Keep first and slow calls. Report all calls and
first occurrences of distinct graph inputs separately, with counts, median,
p95, maximum, timeouts and infrastructure failures. Do not present warmed calls
as independent latency samples or claim a cold-cache measurement without one.

Report descriptive proportions first. Do not use naive 600-trial binomial
confidence intervals or claim the earlier sample-size power calculation applies.
Any clustered uncertainty analysis must justify reviewed independent grouping;
the heuristic semantic clusters are insufficient by themselves. No empirical
metric demonstrates transaction safety or live wallet protection.

## Supplementary evidence

The existing 72 relationship-mutation scenarios, 12 lifecycle scenarios and
wallet evidence remain separate controlled experiments with their original
limitations and snapshots. Do not imply they were rerun for this dataset. This
preparation does not modify their results or count them toward 600 prompts.
