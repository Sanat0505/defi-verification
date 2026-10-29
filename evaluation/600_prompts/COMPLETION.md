# Completed balanced 600-prompt run

Completed 24 October 2026 at 10:14 Berlin time. All 600 attempts are recorded: 596 successful model responses and four retained daily-quota failures.

This is a user-accepted, development-informed follow-up with assistant-drafted references. It is not an independently reviewed untouched held-out benchmark.

| Category | Final-status matches | Prompts |
|---|---:|---:|
| incomplete_or_ambiguous | 57 | 100 |
| invalid_parameters_or_conditions | 97 | 100 |
| known_entities_invalid_relationship | 100 | 100 |
| supported_aave | 99 | 100 |
| supported_uniswap | 82 | 100 |
| unknown_or_unsupported | 99 | 100 |

Overall exact-status agreement: 534/600 (89%). Joint reference agreement: 529/600 (88.17%); see the restricted metric definition in analysis.json.

Binary decisions among 596 cases yielding decisions: TP 181, FP 1, FN 18, TN 396. The four errors remain outside this matrix but inside the 600-attempt accounting. One of the errors has an approval reference; three have non-approval references.

Reference graph: 340/340 decision and selected-evidence matches, 112 distinct inputs. 338/340 calls met two seconds (99.41%); 110/112 first distinct-input calls met two seconds (98.21%). Maximum 12,327.911 ms. All first and slow calls retained. This is conformance to the admitted snapshot, not independent protocol truth.

Code, configuration, graph content, original dataset labels and all earlier saved case segments passed integrity checks. No wallet calls, policy renewal, or transactions were part of this run.

Next: review error/reference ambiguities without overwriting the frozen results, prepare figures and paired-formulation analysis, then write the chapter. The original 400-prompt experiment remains separate; different dataset percentages do not establish a causal improvement.

Important files: SUMMARY.md, analysis.json, case_summary.csv, diagnostics.csv, graph_summary.csv, completion_integrity.json, approval_flags_for_review.json, error_review_priorities.json, results.json and dataset_snapshot.json.
