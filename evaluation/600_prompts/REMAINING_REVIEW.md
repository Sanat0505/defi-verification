# Remaining work before thesis submission

The 600-attempt execution, aggregate analysis, full confusion matrices, paired-formulation analysis, latency analysis, error review, six figures and chapter draft are complete. Original evidence is unchanged. No additional model quota is required to use these results.

## Researcher decisions still required

1. Review the 300 scenario references in `researcher_reference_review_300.json`. The file supplies both prompts, original intent, disposition, rationale, leakage flags and observed mismatch IDs. It is an evidence queue, not completed human adjudication. Record reviewer, date, decision and rationale separately. Reviewing after seeing results must be labelled retrospective; it cannot turn this run into a prospectively reviewed untouched test.
2. Prioritize BAL600-275-A/B (intermediate-token requirement), the 50 incomplete/ambiguous scenarios, and local admission-policy judgments. Check whether each pair expresses the same intended meaning. Also review matched cases: matching an incorrect draft label is not correctness.
3. Confirm that the chapter describes the implemented local Uniswap admission restriction accurately. It is not an official Aave dependency. Changing this scope would require a separate implementation/snapshot version and new or separately labelled evaluation, not relabelling the old evidence as if it used broader coverage.
4. Resolve the six near-text overlap flags and assess the proposed semantic clusters if making independence or generalization claims. Raw scenario count does not establish independence.
5. Review the controlled experiment references and strict traceability criteria. The existing results do not show exact missing-edge explanations or successful live transactions.
6. Integrate the draft into the thesis structure, replace historical “not yet evaluated” language only where referring to this completed follow-up, and preserve the qualification that the originally proposed independently reviewed held-out evaluation has not been established. The separate historical reports were intentionally not rewritten.

If a reference changes, preserve its original label, add a dated adjudication and report original and adjudicated scores separately. Do not overwrite raw results or quietly remove quota errors. Do not claim independent human review merely because execution was authorized.

## Optional implementation work after this evidence is preserved

These issues are documented, not fixed by the analysis:

- Preserve intermediate-token/multihop requirements even if extraction omits them; BAL600-275-A is the observed false approval.
- Recognize supported slippage phrases such as “must not exceed” without changing explicit limits or silently applying defaults.
- Distinguish missing information from unsupported conditions and preserve known fields during clarification.
- Return stable rule identifiers and specific missing-relationship evidence; generic rejection currently fails strict traceability criteria.
- Address separately documented wallet gaps if wallet guarantees become part of the claimed contribution.

Any fix should receive focused regression checks and a separately labelled post-change run. Such a run would not replace these original observations. Expanding to 5,000–8,000 prompts or switching extraction models is not necessary to finish the current chapter and would introduce a new study design.
