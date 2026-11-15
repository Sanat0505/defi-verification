# Thesis

[Read the thesis (PDF)](DEFI_VERIFICATION.pdf): *Securing AI Agents in Decentralized Finance through Graph-Based Intent Verification*.

The PDF was built from the [editable LaTeX project](source/thesis.tex). The chapters are in [content/](source/content/), the references in [bibliography.bib](source/bibliography.bib), and the editable diagrams and exported figures in [figures/](source/figures/). The [Digital Appendix chapter](source/appendix/digital_appendix.tex) describes the accompanying [prototype](../source/), [experiments](../evaluation/), and [Neo4j snapshot](../evaluation/graph/submission/).

## Rebuild the PDF

From this directory, run the following with Tectonic installed:

```sh
cd source
tectonic --format latex.fmt thesis.tex
```

This writes `source/thesis.pdf`. The first run needs access to Tectonic's TeX bundle unless it is already cached. The PDF in this folder was built using Tectonic 0.17.0. The source also includes the original Makefile for use with latexmk.

The project came from `DEFI_VERIFICATION.zip` (SHA-256: `94ea3fff2622080958c35ff5e61249b31db15d231bd5f4ff5ff201db2dc23b39`). The repository copy sets the xcolor options before packages load and updates the Digital Appendix description to match the files here.
