# Restricted ERC-4337 authorization implementation report

Date: 15 November 2026. Branch: `feature/restricted-erc4337-authorization`.

## Outcome and scope

Restricted authorization is implemented and demonstrated locally through the
**actual Kernel 0.3.1 and EntryPoint 0.7 contracts**, including operations signed
using the installed SDK adapter. **213 Python tests and 74 JavaScript tests pass.**
All four R4 criteria are supported within this evaluated local scope, justifying
**★★★ for the revised implementation**. The historical demonstration's ★☆☆
assessment remains a statement about that earlier implementation.

**Not activated on Sepolia:** no public-chain transaction, contract deployment,
permission installation, live bundler simulation, or testnet settlement was
performed. Execution fails closed until a separately controlled development
account and the reviewed validator are installed and configured. Public-bundler
acceptance and production readiness are not established by these results.

## 1. Original architecture and limitations

`wallet.mjs` constructed a Kernel account with `plugins.sudo` using `PRIVATE_KEY`.
The local JSON whitelist checked destinations, native value, and time; it was
renewable by the backend and did not restrict signatures at the account level.
Direct `send_swap` and `send_aave` commands could bypass the API's capability store.

The API already retained structured approvals, claimed them atomically once,
checked expiry and non-approval, and repeated graph verification. However, swap
re-verification required only route overlap and then passed **all renewed routes**
to execution. Quoter addresses and token decimals were absent from that comparison.
The browser wallet address was format-checked, not authenticated as account owner.

## 2. Compatibility and selected mechanism

| Component | Inspected/tested version |
|---|---|
| `@zerodev/sdk` | 5.5.10, unchanged |
| `@zerodev/ecdsa-validator` | 5.4.9, unchanged; not used to sign automated execution |
| viem | 2.53.1, unchanged |
| Kernel | 0.3.1; upstream commit `03f7f5cf5871cda0070e4223f196f5b577f6cde2` |
| EntryPoint contracts | `@account-abstraction/contracts` 0.7.0 |
| Solidity / local EVM | solc 0.8.24, optimizer 200, via IR, Shanghai; Ganache 7.9.2 |
| Validation extension | Custom ERC-7579 `IValidator` as SDK `plugins.regular` |

The installed SDK sources and public exports were inspected. Integration uses
`createKernelAccount({address, plugins: {regular}, ...})`; it does not import the
unexported `toKernelPluginManager` helper. The plugin supplies public initialization
data because this SDK computes it even for a deployed account. It cannot produce
an owner enable signature or sign generic messages/transactions.

An exact ordered-batch commitment was selected instead of treating a set of
individually allowed contract calls as equivalent to an approved operation.
The custom validator covers every byte of Kernel's execution calldata, including
the execution mode, call count, order, destinations, values, and arguments.
No newer permission SDK API is assumed or required.

Primary references:

- [Pinned Kernel interfaces and validation implementation](https://github.com/zerodevapp/kernel/tree/03f7f5cf5871cda0070e4223f196f5b577f6cde2/src).
- [Official SDK repository](https://github.com/zerodevapp/sdk); installed 5.5.10 source is the precise compatibility reference.
- [ZeroDev call-policy documentation](https://docs.zerodev.app/sdk/v5_3_x/permissions/policies/call), used for mechanism comparison, not as an exact 5.5.10 API specification.
- [EntryPoint 0.7 contracts](https://github.com/eth-infinitism/account-abstraction/tree/releases/v0.7/contracts).
- [Pinned Solady sources](https://github.com/Vectorized/solady/tree/9deb9ed36a27261a8745db5b7cd7f4cdc3b1cd4e).
- [Pinned ExcessivelySafeCall sources](https://github.com/nomad-xyz/ExcessivelySafeCall/tree/81cd99ce3e69117d665d7601c330ea03b97acce0).

Vendored sources retain their original SPDX identifiers, copyright notices and
license files. `source/wallet/test/vendor/manifest.json` records upstream commits
and source hashes checked by the compiler. EntryPoint retains its GPL-3.0 license;
the custom validator is MIT licensed.

The pre-implementation inspection and decisions are recorded in
`R4_COMPATIBILITY_PLAN.md`.

## 3. New authorization architecture

1. The existing graph workflow issues a server-retained approval, now also binding
   the configured smart account and the original expiry.
2. Execution claims the capability once, validates the retained intent, and
   re-verifies graph authority. Only retained routes with unchanged security fields
   remain eligible. No contract data is reconstructed from natural language.
3. Read-only preparation builds the full call batch from those parameters. Quote,
   balance and allowance reads remain part of the trusted preparation process.
4. A separate authority subprocess independently compares canonical ABI encodings
   against the retained operation. It signs a short-lived commitment to the exact
   batch. Its environment contains the graph-authority key but no executor/owner key.
5. The worker receives the permit and only the restricted executor key. It does not
   load `.env`, re-quote, rebuild calls, install modules, or fall back to sudo.
6. Kernel routes validation to `GraphBoundValidator`. The validator requires both
   the authority's operation signature and the executor's UserOperation signature.
   EntryPoint enforces the returned validity bounds. The validator consumes the
   approval ID once. Successful receipt waiting precedes `executed: true`.

The owner installs/revokes the module and retains unrestricted administration.
The graph authority can approve supported operations but is not the root signer.
The configured owner, graph authority and executor must be different addresses.
The runtime checks chain ID, Kernel account ID, EntryPoint address, installed
selector, role configuration and exact validator runtime bytecode against the
checked-in compiled artifact. It requires an already-deployed account.

These are signing-role and process-environment boundaries, **not an OS sandbox**.
Protecting the host and graph-authority credential remains essential. A compromised
authority can attest malicious batches; a compromised executor alone cannot.

## 4. Exact enforced restrictions

| Restriction | Enforcement |
|---|---|
| Account | Retained configured account; signature domain includes account; validator requires caller = UserOperation sender |
| Network | Contract requires chain ID 11155111; authority digest and executor UserOperation signature also bind chain |
| Validator/configuration | Digest includes module address, executor and monotonically incremented installation epoch |
| Destinations/functions | Exact full Kernel calldata hash; issuer only accepts supported canonical ABI encodings |
| Batch shape | Exact count, order, every destination/value/calldata byte; additions, removals, duplication and reordering invalidate the permit |
| Execution mode | Issuer encodes ordinary CALL / revert-on-failure mode; no delegatecall or try-mode permit |
| Native value | Every prepared call is exactly zero; changing it breaks the commitment |
| ERC-20 approvals | Exact token, spender and operation amount; optional zero reset; no new unlimited allowance |
| Validity | Expiry is min(original approval expiry, issuance + 120 seconds); 5-second start tolerance; contract limits total window to 125 seconds; EntryPoint checks time |
| Usage | One accepted validation per account/approval ID, even with a new EntryPoint nonce; consumed IDs survive module uninstallation |
| Gas | Owner-configured maximum total declared UserOperation gas × max fee, including paymaster verification/post-operation gas |
| Alternate paths | No generic ERC-1271 signatures or direct caller hook; only Kernel execute selector; raw send commands disabled; no sudo key in execution |

For **Uniswap**, the exact commitment covers router, `exactInputSingle`, input and
output tokens, fee tier, amount, Kernel recipient, quote-derived minimum output,
zero price limit, and every preceding approval. The seven-field SwapRouter02 ABI
has no deadline; the UserOperation's authorization window supplies a validity bound.
The graph pool and quoter remain retained preparation evidence; the pool is selected
by the router's token-pair/fee semantics, rather than a separate pool-address argument.

For **Aave**, it covers Pool, supply/withdraw/borrow/repay selector, underlying asset,
exact amount, Kernel recipient/on-behalf-of address, referral code when present,
variable rate mode 2 where applicable, and each necessary approval.

Exact base-unit conversion rejects excess decimal precision instead of silently
rounding. Slippage becomes an exact minimum-output value before attestation.
Changing any permitted execution bytes requires a new retained approval and grant.
Existing allowances outside this workflow are not revoked; use a fresh development
account. Across distinct approvals there is no cumulative session spending budget.

## 5. Installation and configuration (not performed on Sepolia)

1. Keep the existing demonstration account intact. Prepare a separate Kernel 0.3.1
   account with EntryPoint 0.7 and a separately controlled ECDSA root owner.
2. Review/build `source/wallet/contracts/GraphBoundValidator.sol`. Its ABI, creation
   bytecode and runtime bytecode are in `source/wallet/artifacts/GraphBoundValidator.json`.
   Deployment is an owner action requiring explicit authorization; no deployment
   or broadcast script is automatically run by the backend.
3. Choose distinct graph-authority and executor addresses and a maximum gas cost
   in wei. Prepare a local JSON file with `account`, `validator`, `authority`,
   `executor`, and decimal-string `maxGasCost` (for example `50000000000000000`
   means a maximum declared gas cost of 0.05 ETH, **not** permission to transfer ETH).
4. Prepare, inspect, and retain the owner installation call without sending:

   ```powershell
   cd source/wallet
   Get-Content -Raw installation-config.json | node wallet.mjs prepare_installation --stdin
   ```

   It encodes Kernel `installModule(1, validator, initData)`, an ordinary no-hook
   secondary validator, and **only** selector `execute(bytes32,bytes)`.
   The owner executes that call through their administrative wallet only after
   authorizing deployment/installation. Do not install it as the root validator.
5. Configure `RESTRICTED_ACCOUNT_ADDRESS`, `RESTRICTED_VALIDATOR_ADDRESS`,
   `GRAPH_AUTHORITY_PRIVATE_KEY`, `RESTRICTED_EXECUTOR_PRIVATE_KEY`, `SEPOLIA_RPC`,
   and ZeroDev configuration through protected environment settings. The owner's
   private key must remain outside the backend. Do not put secrets in installation
   JSON, command-line arguments, tracked files, or logs.
6. Re-verify an operation through `/api/verify`, then submit its capability ID
   through `/api/execute`. Missing, revoked, wrong-version or mismatched deployment
   configuration fails closed. Reinstallation increments the epoch, invalidating
   outstanding old-epoch permits; uninstallation removes authorization.

The returned installation call is concrete and inspectable, but cannot be fully
instantiated until development account, module and role addresses are chosen.
No deployment/installation approval is implied by this report.

## 6. Validation results and evidence classification

| Evidence category | Actual result | Scope |
|---|---|---|
| Python source regressions | 160 passed | Includes 20 new mocked backend/role/binding tests |
| Python evaluation regressions | 53 passed | Existing offline checks; historical files not regenerated |
| JavaScript suite | 74 passed | Local contracts, SDK integration, canonical ABI checks, disabled CLI |
| Testnet simulations | Not run | Public bundler policy remains untested |
| Testnet transactions/deployments | None | No testnet success claim |

Saved run outputs are under `docs/restricted-authorization/evidence/`.
The original 28 wallet-policy/hand-over results and all graph datasets/results are
unchanged. The evaluator's mocked execution adapter was updated to the new function
signature; its historical recorded results were not rewritten.

**Positive:** all five supported call patterns executed through real EntryPoint
`handleOps` and Kernel validation/execution. Destination events assert every call's
calldata, account caller, zero value and order. An additional SDK test signs the
UserOperation using the production regular-validator adapter and executes it through
the real local EntryPoint. Authority checks accept valid approval/no-approval/reset
variants before issuance. Backend tests confirm claim → re-verification → authorization.

**Negative:** genuine executor signatures do not authorize changed destinations,
selectors, swap tokens/fee/amount/recipient/minimum/price limit, approval spenders,
unlimited approvals, reset-spender changes, native value, or extra/removed/reordered
calls. Aave asset/amount/recipient and rate-mode changes fail. Missing/forged authority
signatures, wrong executor, account/domain/epoch mismatches, wrong network, overlong
validity, expired/not-yet-valid permits, reuse under a fresh nonce, and gas-budget
violations fail. Tests assert actual EntryPoint AA24 signature rejection or AA22
time-window rejection, not merely an arbitrary test exception. Owner-root nonce
fallback and direct Kernel execution/installation by the executor also fail.

Mocked API tests separately cover rejected/unresolved graph results, changed graph
authority, expiry, reuse and wrong/unbound accounts. A restricted key can submit an
**already-issued exact valid permit** outside the API, which is still authorized
execution; without the graph-authority grant, direct submission cannot bypass policy.

**Local test boundaries:** Ganache runs entirely in memory. The actual deployed
EntryPoint runtime is placed at its canonical address so the unchanged SDK adapter
can sign against it. Kernel, factory, root validator and custom validator are real
contracts; only DeFi targets record calls instead of implementing protocol economics.
No permission validator is mocked. Tests do not reproduce bundler mempool validation,
paymaster service behavior, RPC outages, collateral checks or liquidity.

## 7. R4 criteria and justified rating

| Exact criterion | Assessment and concrete evidence |
|---|---|
| **C1:** An explicit approval or rejection is produced before blockchain execution. | Supported: existing `process_prompt`, retained decision; pipeline/API regression tests. |
| **C2:** Rejected or unresolved actions are automatically prevented from continuing toward execution. | Supported: capability checks, graph re-verification, `test_changed_or_unresolved_graph_never_authorizes`; real-contract missing/forged-grant rejection. |
| **C3:** Approved actions execute only within restrictions that enforce the applicable verified execution conditions. | Supported locally: real five-action executions, complete-call commitment, contract mutation, time, use, gas, chain and account tests. |
| **C4:** The executed operation remains bound to the approved security-relevant parameters. Changes require revalidation before execution. | Supported locally: retained route intersection, account/expiry binding, independent ABI comparison, frozen calldata submission and executor-signed mutation rejection. |

All four are demonstrated in the stated scope, including mandatory C2 and C3:
**★★★**. This does not certify production security or establish the behavior of an
uninstalled Sepolia deployment. Deployment-level assurance remains incomplete.

## 8. Remaining limitations

- Custom validator is not independently audited. No public-bundler/ERC-7562 trace
  acceptance test, staking assessment, sponsored simulation or live installation
  was performed. Returned validation time bounds avoid using TIMESTAMP in the
  validator, but that alone is not a bundler-compatibility demonstration.
- Trusted graph authority, backend, planner, admitted graph knowledge and RPC quotes
  remain assumptions. The validator verifies an attestation, not Neo4j contents or
  natural-language correctness. Graph/state changes during the short grant window
  cannot be atomically coupled to on-chain execution.
- The browser address is not authenticated as the Kernel owner. The account is a
  backend-configured development account bound at verification, not an arbitrary
  account selected by the caller.
- Approval storage remains process-local. A lost response or reverted execution
  can consume authorization; there is no automatic retry or persistent reconciliation.
  A valid grant is consumed at validation, including if subsequent execution reverts.
- Exact per-operation token amounts and a one-use limit are enforced; aggregate
  budgets over separately approved operations and revocation of existing token
  allowances are not implemented.
- Owner administration remains privileged by design. Credential filtering is not
  filesystem/process isolation against a compromised host.
- Ganache's optional native transport was unavailable under Node 24; tests used its
  JavaScript fallback. npm reported dependency advisories in the development test
  toolchain; no claim of an audited dependency stack is made. These packages are
  development dependencies, not prerequisites for runtime signing.

## 9. Changed files

- Execution binding: `source/api/app.py`, `source/services/pipeline.py`,
  `source/core/models.py`, `source/core/state.py`.
- Wallet: `source/wallet/wallet.mjs`, `erc4337.py`, `authorization.mjs`,
  `approved-plan.mjs`, `authority.mjs`, `restricted-client.mjs`,
  `contracts/GraphBoundValidator.sol`, compiled artifact, package manifests.
- Tests: `source/tests/test_restricted_authorization.py`, updated Aave/slippage
  mocks, `source/wallet/test/authorization.test.mjs`, local recording target,
  compiler and pinned upstream test dependencies with hash manifest.
- Reproduction: `evaluation/wallet_runner.py` (mock adapter only), `.env.example`,
  `.gitattributes`, root/source README branch notices, this report, compatibility
  plan, branch documentation/evidence.
- Thesis: complete supplied project imported under `thesis/`; only the five source
  files listed below differ substantively from the supplied ZIP. The original
  Downloads PDF and ZIP were not overwritten.

## 10. Thesis changes and before/after excerpts

Exact unified before/after LaTeX is in `thesis/R4_SOURCE_CHANGES.patch`, compared
against the supplied ZIP, not against a historical template. Sections changed:

| Section | Minimal change |
|---|---|
| 3.6 Controlled Smart-Wallet Execution | Short exact-batch permission explanation |
| 4.6 Controlled Smart-Wallet Execution | Retained-route binding; three signing roles; actual validator; installation, restrictions and receipt behavior |
| 4.7 Implementation summary | Correct execution-binding limitation |
| Figure 4.6 source | Attestation, restricted validation and receipt labels |
| 5.2.3 | Separate November local authorization procedure |
| 5.3.4 | Actual new test outcomes, explicitly separate from historical 28 tests |
| 5.4 | Remaining execution limitations |
| 5.5 R4 and comparison table | Criterion-level assessment; only prototype R4 cell becomes three stars |
| 5.6 | Local-test, trust and deployment threats to validity |
| 5.7 | Revised authorization scope in summary |
| 6 | Correct only wallet finding, limitation and future-work statements |

Representative R4 excerpt before:

```latex
Although
ERC-4337 and ZeroDev Kernel provide mechanisms for restricting execution,
their complete enforcement was not demonstrated by the prototype.
Consequently, R4 receives \evOne{} under the criteria defined in
Chapter~\ref{chap:stateoftheart}.
```

After:

```latex
All four criteria, including mandatory C2 and C3, are therefore supported
within this locally evaluated scope, yielding \evThree{}. This revises the
earlier \evOne{} assessment of the demonstration implementation; it does
not establish Sepolia deployment, public-bundler acceptance, or production
security.
```

Binding excerpt before:

```latex
Swap preparation
receives all routes returned by the renewed verification
and may select a route other than the one that matched
the original approval.
```

After:

```latex
After read-only preparation, the backend independently
checks the complete encoded batch against the retained operation. It then
authorizes those exact bytes; submission neither selects another route nor
recalculates the quote.
```

No R1, R2, R3, R5 or R6 ratings/results, frozen datasets, graph algorithms,
Neo4j schemas, or synchronization logic were changed.

## 11. Reproduction

From the repository root, with the project's Python dependencies and Node installed:

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest source/tests evaluation/tests -q -p no:cacheprovider
cd source/wallet
npm ci
npm run build:validator
npm test
```

All authorization tests are offline after dependency installation; no credentials
or public RPC endpoints are needed. Node 24.18.0 and Python 3.13.1 were used here.
`NODE_CMD` can select the Node executable for Python's subprocess wrapper. The
compiler verifies vendored upstream hashes, and the tests check that the committed
validator bytecode matches the tested source. The build cache is disposable and
keyed by sources, compiler script, dependency lock and upstream manifest.

The thesis source is in `thesis/`, with its original Makefile. Build with the
user's normal LaTeX toolchain (`latexmk -pdf r4-build.tex` from that directory).
The wrapper resolves conflicting xcolor options in the supplied preamble without
rewriting it. A 147-page PDF was compiled, and the changed sections were rendered
and visually inspected. Unrelated source typesetting warnings remain outside scope.
Thesis build/visual verification status is recorded in `thesis/R4_SOURCE_REVIEW.md`.
