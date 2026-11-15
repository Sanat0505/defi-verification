# R4 thesis source provenance and review

Source: the user-supplied `DEFI_VERIFICATION.zip`.
SHA-256: `4b237676c0a5d506aceef551b6e31af4d42130290dcf27da4c67356ba990ae97`.

The complete project is preserved here. Only `content/concept.tex`,
`content/implementation.tex`, `content/evaluation.tex`, `content/conclusion.tex`
and `figures/controlled_execution_flow.tex` receive R4 content changes.
`R4_SOURCE_CHANGES.patch` gives exact differences from the supplied archive.
The original supplied PDF and ZIP are preserved unchanged as `DEFI_VERIFICATION.pdf` and `DEFI_VERIFICATION.zip` in this directory. The PDF predates the R4 source revisions.

The supplied preamble imports `xcolor` with inconsistent options. `r4-build.tex`
passes the combined options before loading the unchanged main source. For a
standard TeX installation, run `latexmk -pdf r4-build.tex` in this directory.
The local Tectonic build uses `--format latex.fmt` because the existing `latex/`
directory otherwise shadows the default format name on Windows.

Validation completed on 15 November 2026:

- The wrapper compiled successfully with portable Tectonic 0.17.0 into a
  147-page PDF. Bibliography and cross-reference passes completed.
- Rendered and visually inspected physical PDF pages 71, 85--87, 89, 95--96,
  104--109 and 112--113, including the updated diagram, implementation,
  methodology, results, R4 assessment/table, limitations and conclusion.
  The changed passages and diagram are legible without clipping or overlap.
- The supplied project still emits typesetting warnings, including overfull
  lines in unrelated appendix passages. Those sections were not rewritten.
  This review is scoped to the requested R4 changes, not a fresh copyedit of
  the entire thesis.
- An archive comparison confirms that only the five named source files
  changed (ignoring CRLF/LF differences in text). Other supplied files remain
  unchanged. See `../docs/restricted-authorization/evidence/thesis-source-review.json`.
- The revised PDF was built and reviewed locally. This branch preserves the
  original supplied PDF; rebuild `r4-build.tex` to produce the R4-revised PDF.
  The extracted sources here include the R4 revisions, build wrapper, provenance,
  exact change patch and images in `figures/`. The supplied ZIP remains unchanged.
