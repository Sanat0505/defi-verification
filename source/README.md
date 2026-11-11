# Application source

This folder contains the implemented system. Experiment runners, datasets and
saved results live in [evaluation/](../evaluation/README.md). Installation and
environment configuration are described in the [root README](../README.md).

| Folder | Purpose |
|---|---|
| `api/` | FastAPI endpoints and application startup |
| `core/` | Configuration, models, state and verification capabilities |
| `db/` | Knowledge acquisition, graph synchronization and verification |
| `llm/` | Intent extraction, normalization and request constraints |
| `services/` | Interpretation and verification pipeline |
| `wallet/` | Python adapter and Node.js wallet execution |
| `static/`, `templates/` | Browser interface |
| `scripts/` | Manual operational utilities |
| `tests/` | Application unit and mocked integration tests |

Run commands from the repository root with the virtual environment active:

```text
python -m uvicorn source.api.app:app --reload --host 127.0.0.1 --port 8000
```

Offline application checks:

```text
python -B -m pytest -q source/tests
node --check source/static/app.js
node --check source/wallet/wallet.mjs
node source/tests/frontend_slippage.cjs
```

The root `.env` supplies configuration. Install Node dependencies with
`npm --prefix source/wallet ci`. The default wallet policy is
`source/wallet/session-whitelist.json`; its contents are unchanged by the move.

Application Python imports use `source.*`. Launch Python utilities as modules
(for example, `python -m source.db.connection`) from the repository root. The
manual `source.scripts.swap_preflight` utility can update wallet policy; it is
not an offline test. See [graph presentation views](GRAPH_PRESENTATION_VIEWS.md)
for the Neo4j inspection queries.
