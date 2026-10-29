# Balanced 600-prompt evaluation status

Checkpoint: 2026-10-24T08:14:49.876711+00:00. Status: **complete**.

**600/600 prompts attempted; 0 unattempted.**
Do not describe a partial checkpoint as a completed 600-prompt result.

- Exact pipeline status matches: 534/600 attempted prompts.
- Joint reference matches: 529/600 attempted prompts.
- Binary decisions: TP 181, FP 1, FN 18, TN 396.
- Operational errors: 4; evidence abstentions: 0.
- Independent reference-intent graph checks: 340/340; 112 distinct inputs observed.
- Graph decision matches: 340/340; within two seconds: 338/340.

The user accepted this dataset for execution. Item-level human reference review
is not documented. Labels remain assistant-drafted. This is a development-informed
balanced follow-up, not a demonstrated untouched, independently reviewed benchmark.
The 600 prompts form 300 paired scenario instances, not 600 independent trials.
Graph conformance does not establish wallet readiness or transaction success.

Binary metrics exclude operational errors and evidence abstentions and report
decision coverage. All attempted prompts remain in exact-status denominators.
Unattempted prompts are not counted as semantic failures or correct negatives.
Joint matches use the definition in analysis.json; unsupported-condition semantics
still require review beyond status-only agreement.

No wallet calls or transaction submission are part of this run. Original
400-prompt results remain separate. Model: openai/gpt-oss-20b; one pass.
