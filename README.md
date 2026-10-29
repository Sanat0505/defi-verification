# DeFi relationship verification

## Project Overview

This Master's thesis prototype converts natural-language DeFi requests into
structured intents and verifies their execution relationships against authoritative
knowledge admitted to a Neo4j property graph. Runtime scope is **Ethereum Sepolia
(11155111)**: Uniswap V3 ERC-20 swaps and Aave V3 `supply`, `withdraw`, `borrow`, and
`repay`. Approval establishes consistency with admitted knowledge, not transaction
success, profitability, or financial safety.

Wallet-to-wallet transfers are outside this scope. A transfer sends tokens to a
recipient address; Aave supply deposits them into a lending pool and creates a
supply position. The prototype has no recipient verification or standalone token
transfer execution path, so it must not reinterpret a wallet transfer as supply.

The [expanded protocol knowledge catalog](knowledge/README.md) runs in a separate
`defi-knowledge-expanded` database. It describes Aave V3, Umbrella and Uniswap V3
interfaces, operations, deployments, reserve assets and source provenance beyond
the executable subset above. Open `/knowledge` or follow **Protocol knowledge**
in the app navigation. Coverage gaps and unimplemented adapters are explicit;
catalog knowledge never issues an execution capability.

## System Architecture

| Component | Responsibility |
|---|---|
| [api/](api/) | FastAPI endpoints and the browser application |
| [llm/](llm/) | Groq extraction, deterministic normalization, validation and request constraints |
| [core/](core/) | Typed models, configuration, clarification state and verification capabilities |
| [db/](db/) | Source acquisition, synchronization, graph verification and diagnostics |
| [knowledge/](knowledge/README.md) | Isolated expanded protocol catalog, pinned sources, coverage and read-only browsing |
| [services/](services/) | Interpretation, clarification and verification pipeline |
| [wallet/](wallet/) | Python adapter and Node.js ERC-4337/ZeroDev execution |
| [static/](static/), [templates/](templates/) | Frontend demonstration interface; no frontend build step |
| [evaluation/](evaluation/README.md) | Completed experiments, frozen inputs, provenance and runners |

`POST /api/verify` interprets and validates a request, then checks an action-specific
graph path. Approval creates a server-held operation and an expiring
`verification_id`. `POST /api/execute` consumes that capability once, revalidates
the saved intent and current graph authority, updates the destination policy, and
hands the approved operation to the wallet. It never reinterprets the prompt.
Knowledge synchronization runs separately from request handling.

## Prerequisites

The verified local configuration is **Python 3.13.1**, **Node.js 24.18.0** and
**npm 10.5.0**. Other runtime versions have not been validated here. Python package
ranges are in [requirements.txt](requirements.txt); npm uses
[wallet/package-lock.json](wallet/package-lock.json).

The saved graph experiments used Neo4j Desktop with **Neo4j Server 2026.05.0
Enterprise**. This is a verified configuration, not a minimum-version claim. The
Python Neo4j driver is a separate dependency. Normal verification uses the configured
user's default database; controlled mutation studies additionally require separate
named databases and appropriate permissions.

Install Git and obtain access to the university GitLab repository. Internet access
is needed for installation, official knowledge feeds, Groq, and RPC services.
Sepolia RPC supports on-chain discovery and execution. A browser is needed for the
frontend; MetaMask and the external ethers script support its wallet connection.
Saved reports and offline tests require no private key, ZeroDev account, running
Neo4j server, or model calls.

## Installation

Clone into `defi-verification` and run subsequent commands from that directory:

```text
git clone git@gitlab.hrz.tu-chemnitz.de:vsr/edu/advising/ma-sanatkumar-kakadiya.git defi-verification
cd defi-verification
```

Windows PowerShell:

```powershell
py -3.13 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
npm --prefix wallet ci
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

If activation is blocked, use `.\venv\Scripts\python.exe` instead of `python` in
subsequent commands. Changing the system execution policy is unnecessary.

Linux/macOS with Python 3.13 installed:

```bash
python3.13 -m venv venv
source venv/bin/activate
python -m pip install -r requirements-dev.txt
npm --prefix wallet ci
test -f .env || cp .env.example .env
```

For runtime-only installation, substitute `requirements.txt` for
`requirements-dev.txt`. Keep the virtual environment and `wallet/node_modules`
installed locally; both are ignored by Git. Optional plotting dependencies:

```text
python -m pip install -r evaluation/sources/requirements-analysis.txt
```

In Neo4j Desktop, create or select a local instance, set its password, and start it.
Ensure its default database is running. Configure `.env` using the instance's
connection details. A typical local configuration uses
`NEO4J_URI=bolt://localhost:7687` and `NEO4J_USER=neo4j`; replace the password
placeholder. For a remote instance, use its supplied URI and credentials.

Wait until the instance has finished starting, then check the connection:

```text
python -m db.connection
```

Expect `Connected to Neo4j!`. A connection-refused error on port `7687` means
the Bolt endpoint is not accepting connections yet; opening Neo4j Desktop or
starting its process does not mean the database is ready. Check the instance's
`neo4j.log` for `Bolt enabled on localhost:7687` and `Started.`. If it uses a
different Bolt address, copy that address into `NEO4J_URI` and restart the API.

After configuring Groq and Sepolia RPC, synchronize the supported deployments:

```text
python -m db.sync --source aave-v3:11155111 --source uniswap-v3:11155111
python -m db.validate_graph_v2
python -m evaluation.snapshot_check
```

Synchronization fetches official Aave address-book and Uniswap deployment data,
performs discovery, and writes admitted knowledge. Require `ok: true` from sync,
`valid: true` from validation, and `freshness_prerequisite_met: true` from the
snapshot check. Structural validation can pass an empty graph; it is not a readiness
check. Freshness alone does not establish a particular requested path.

These service-dependent commands have checked entry points but were **not run
against live services during cleanup**. Start the application as described below.

## Environment Configuration

Use [.env.example](.env.example); replace placeholders and leave unused optional
credentials unset. Never commit real credentials or private keys.

| Variable | Requirement and purpose |
|---|---|
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | Required for live graph synchronization and verification |
| `GROQ_API_KEY` | Required for natural-language extraction |
| `LLM_MODEL` | Default `openai/gpt-oss-20b`; model availability depends on the Groq account |
| `SEPOLIA_RPC` | Required for Sepolia discovery and wallet reads/execution |
| `MAINNET_RPC` | Optional for the Sepolia application; required for complete Mainnet Uniswap discovery when syncing Mainnet |
| `PRIVATE_KEY` | Execution only: backend signer used to derive the ERC-4337 smart account |
| `ZERODEV_PROJECT_ID` or `ZERODEV_RPC` | Execution only: project-derived or explicit bundler/paymaster endpoint |
| `SUPPORTED_CHAIN_ID`, `SUPPORTED_NETWORK` | Keep `11155111` and `Ethereum Sepolia`; changing these does not add chain support |
| `KNOWLEDGE_MAX_AGE_HOURS` | Freshness limit; default `168` |
| `SWAP_SLIPPAGE_BPS` | Omitted-slippage default `100`; allowed `1–500` basis points |
| `VERIFICATION_TTL_SECONDS`, `CONVERSATION_TTL_SECONDS` | Capability/clarification lifetimes; defaults `600` / `1800` seconds |
| `API_TIMEOUT_SECONDS`, `LOG_LEVEL` | Defaults `45` seconds and `INFO` |
| `UNISWAP_LOG_CHUNK_SIZE` | Optional factory-event discovery tuning |

Verification against a populated graph requires Neo4j and Groq, but no private
wallet credentials. Saved-report inspection requires neither service. Execution
additionally needs a usable ZeroDev project, a funded smart account or applicable
sponsorship, balances/allowances, and the relevant Aave position or swap liquidity.
The backend signer is distinct from the browser wallet address. The policy file
defaults to `wallet/session-whitelist.json`; `WALLET_WHITELIST_FILE` can override
its path. Do not edit authorization policy merely to make a test pass.

## Running the Application

With the virtual environment active, run from the repository root:

```text
python -m uvicorn api.app:app --reload --host 127.0.0.1 --port 8000
```

Open [http://localhost:8000](http://localhost:8000). The backend serves the frontend
and static files; [API documentation](http://localhost:8000/docs) is at `/docs`.
Before accepting requests, the API runs a read-only Neo4j query with the driver's
transient-error retries. Wait for `Neo4j is ready` and `Application startup complete`
in the terminal. If the database stays unavailable or credentials are invalid,
startup fails with connection-check instructions. This check establishes database
access; it does not establish graph freshness or coverage.
`/api/health` confirms the HTTP application is running; it does not test service
connectivity or wallet readiness.

Example verification requests:

- “Swap 0.001 USDC to WETH on Uniswap V3 on Ethereum Sepolia.”
- “Supply 10 USDC to Aave V3 on Ethereum Sepolia.”
- “Borrow 1 USDT from Aave V3 on Ethereum Sepolia.”

These demonstrate supported syntax, not promised approvals. Approval requires valid
normalized parameters, fresh verified deployment knowledge, and an admitted
action-specific path. Uniswap eligibility requires both pool tokens to be active
Aave reserve assets or canonical WETH on that chain.

| Verification decision | Meaning |
|---|---|
| `APPROVED` | An authoritative path exists for the validated operation under the knowledge policy |
| `REJECTED` | Invalid parameters, or sufficiently complete knowledge establishes a missing relationship |
| `UNSUPPORTED` | Protocol, action, network or condition is outside scope |
| `NEEDS_CLARIFICATION` | Required information is missing or ambiguous |
| `INSUFFICIENT_EVIDENCE` | Knowledge is unavailable, stale, unsynchronized or inadequate to establish absence |
| `ERROR` | Extraction or configuration prevented processing |

Submit clarification in the same conversation, or choose **New operation** to reset
it. Connecting MetaMask and selecting **Execute Transaction** is a separate action
that can submit a real Sepolia transaction. Execution responses use `EXECUTED` or
`FAILED`; graph approval alone does not establish wallet readiness.

## Testing

For a fresh checkout, retrieve the four pinned public research inputs once before
the complete offline suite. This downloads files and verifies their recorded hashes;
it requires internet access but no model, graph or wallet credentials:

```text
python -m evaluation.source_import --source uniswap --source compound --source cow --source license --manifest .cache/evaluation-runs/source-manifest.json
```

Inputs remain under `.cache/intent-tx-18k/`. With dependencies and inputs present,
these checks are offline:

```text
python -B -m pytest -q
node --check static/app.js
node --check wallet/wallet.mjs
node tests/frontend_slippage.cjs
python -B -m evaluation.check_integrity
python -B -m evaluation.sourced_runner --validate-only
python -m pip check
npm --prefix wallet ls --depth=0
```

Pytest includes unit tests, mocked integration tests, wallet-boundary fixtures and
the two controlled-graph harness tests. External model, database and submission
boundaries are mocked. The graph-focused subset is:

```text
python -B -m pytest -q tests/test_graph_v2_unit.py tests/test_graph_evaluation.py tests/test_sync_pipeline.py tests/test_verification_trace.py tests/test_controlled_graph.py
```

`python -m evaluation.graph_runner --repeats 1` requires live Neo4j and fresh
knowledge, makes no LLM calls, and neither mutates the database nor broadcasts.
Controlled mutation harnesses have separate isolated-database requirements in the
[evaluation guide](evaluation/README.md). Manual scripts such as
`scripts/swap_preflight.py` can change authorization policy and are not offline tests.

## Evaluation and Reproducibility

| Completed experiment | Report | Frozen dataset | Observations / metrics |
|---|---|---|---|
| Exploratory 400 prompts | [Summary](evaluation/400_prompts/SUMMARY.md) | [Dataset](evaluation/400_prompts/dataset_snapshot.json) | [Results](evaluation/400_prompts/results.json) / [analysis](evaluation/400_prompts/analysis.json) |
| Balanced 600 prompts | [Summary](evaluation/600_prompts/SUMMARY.md) | [Dataset](evaluation/600_prompts/dataset_snapshot.json) | [Results](evaluation/600_prompts/results.json) / [analysis](evaluation/600_prompts/analysis.json) |

Both evaluate extraction/validation, end-to-end verification decisions, and
independent reference-intent graph checks. References remain assistant-drafted.
The 400 prompts form 200 paired scenarios; the 600 form 300. They are not
independently reviewed held-out benchmarks or independent samples.

Open the linked files without calling the model. The
[600-prompt analysis](evaluation/600_prompts/CHAPTER_5_DRAFT.md) and
[error review](evaluation/600_prompts/ERROR_REVIEW.md) provide detailed interpretation.
The [evaluation guide](evaluation/README.md) links graph/wallet results, journals,
provenance and intentional reproduction commands. Integrity checking does not
rewrite saved results.

For a small service-dependent smoke run:

```text
python -m evaluation.runner --limit 3 --repeats 1 --output-dir .cache/evaluation-runs/smoke
```

This calls Groq and Neo4j and writes separate outputs. The 400/600 runners have no
`--limit` option. Fresh model calls can incur costs and yield different responses.
Full experiments and live service checks were not rerun during cleanup; the linked
results are the preserved completed experiments.

## Security and Limitations

This is a local testnet research prototype, not a production financial service.
Keep the server local. Approval means conformance to admitted knowledge, not
independent certification of source truth, financial safety or transaction success.
Coverage and freshness constrain negative decisions; failed acquisition retains
the last successful knowledge and does not make it newly fresh.

Execution rechecks authority, freezes explicit swap slippage, and uses Aave's
variable-rate mode (`2`) for borrow/repay. Balances, allowances, liquidity, collateral,
debt, sponsorship and chain state can still prevent execution. Signer binding to
the browser address, per-token spending budgets and receipt reconciliation remain
declared wallet gaps. Capabilities and conversations are process-local; restart or
reload clears them, so use one application worker for this demonstration.

Verification-only evaluations do not sign or broadcast blockchain transactions.
Wallet evaluation successes are controlled fixtures, not proof of successful
on-chain execution. Keep frozen datasets, decisions and metrics unchanged; new
experiments belong in separate output directories.
