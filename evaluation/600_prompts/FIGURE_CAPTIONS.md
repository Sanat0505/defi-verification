# Figure captions

1. **Agreement by request category.** Exact final-status and joint reference matches for six categories of 100 prompts each. All 600 attempts, including four operational errors, remain in the denominators. Joint agreement has the restricted field-and-disposition definition specified in the methods. File: `figures/01_category_agreement.png`.

2. **Pipeline outcome confusion matrix.** Rows show assistant-drafted reference outcomes and columns show observed outcomes for all 600 attempted prompts. Operational errors are a separate observed column; they are not correct non-approvals. File: `figures/02_full_confusion_matrix.png`.

3. **Binary approval confusion matrix.** Among 596 decisions, TP=181, FN=18, FP=1 and TN=396. Four quota errors remain outside the matrix: one positive-reference and three negative-reference prompts. Different non-approval statuses are collapsed, so this metric is less strict than exact-status agreement. File: `figures/03_binary_confusion_matrix.png`.

4. **Primary diagnoses for joint mismatches.** Mutually exclusive retrospective diagnoses for all 71 joint mismatches: 66 final-status mismatches and five field-only mismatches. These observations were not rerun after fixes; diagnoses are assistant analysis and remain reviewable. File: `figures/04_error_breakdown.png`.

5. **Wording-pair agreement with references.** Counts across 300 paired scenario instances according to whether each formulation matches the exact reference status. A and B are fixed formulation designations; execution order within pairs was randomized. These pairs are not independent model comparisons. File: `figures/05_paired_formulations.png`.

6. **Empirical graph-verification latency distributions.** All 340 direct reference-intent calls and the first occurrence of each of 112 distinct inputs, with every first and slow call retained. The horizontal dotted line is 95%; the vertical dashed line is 2,000 ms. The logarithmic horizontal axis includes the 12,327.911-ms maximum. Timings exclude LLM and wallet work. File: `figures/06_graph_latency.png`.

Each figure also has an SVG version. In LaTeX, PNG can be included with `graphicx` without SVG conversion. Example:

```latex
\begin{figure}[htbp]
  \centering
  \includegraphics[width=\linewidth]{figures/02_full_confusion_matrix.png}
  \caption{Pipeline outcome confusion matrix for all 600 attempted prompts.
  Rows represent draft references and columns represent observed outcomes;
  operational errors remain a separate column.}
  \label{fig:balanced600-confusion}
\end{figure}
```
