# Restricted authorization compatibility and implementation plan

Branch: `feature/restricted-erc4337-authorization`.

## Inspected baseline

Installed and locked: `@zerodev/sdk` 5.5.10, `@zerodev/ecdsa-validator`
5.4.9, viem 2.53.1. The wallet selects Kernel **0.3.1** and EntryPoint
**0.7**. `buildClients` loads `PRIVATE_KEY` into `plugins.sudo`; the local
JSON destination/value/expiry checks do not constrain that signer on-chain.
Direct `send_swap` and `send_aave` CLI calls bypass the API capability store.

The API retains the normalized amount, chain, graph addresses, selector,
function signature, routes, decimals, rate mode, referral code and slippage.
It atomically claims an expiring capability and re-verifies graph authority.
Swap route intersection currently permits newly introduced routes to reach
execution; the implementation must use only retained, still-valid routes.
The caller's wallet address is not the Kernel recipient in the baseline.

Swaps use SwapRouter02's seven-field `exactInputSingle` tuple (no deadline),
with the Kernel recipient and quote-derived minimum output. Supply and repay
may prepend ERC-20 approval reset and exact-amount approval calls. Withdraw
and borrow have one Pool call. All calls have zero native value.

## Selected mechanism

Use the installed SDK's `KernelValidator` / `plugins.regular` extension,
compatible with the pinned Kernel v3.1 `IValidator` ABI. A custom secondary
validator binds a backend authority signature to the **entire Kernel execute
calldata**, account, executor, chain, module, configuration epoch, approval ID,
and validity window. It also checks the restricted executor's UserOperation
signature and consumes the approval ID at most once.

The standard call policy supports targets, selectors and argument rules,
but a set of individually permitted calls is not an exact ordered batch
commitment. A custom validator avoids silently allowing duplicated,
reordered or additional otherwise-permitted calls. No SDK upgrade is needed.

The owner installs the validator on a separate, already-deployed development
account. The backend authority may attest approved batches but cannot sign
arbitrary UserOperations as owner. The worker receives only the restricted
executor key; it never loads `.env` or falls back to sudo. ERC-1271 and direct
caller authorization through this validator are disabled.

## Implementation and evidence

1. Preserve graph verification and datasets; tighten retained-result binding.
2. Prepare calls read-only from the retained operation, then independently
   check their ABI encoding before issuing a short-lived authorization.
3. Submit exactly those bytes with the regular validator. Disable legacy raw
   send commands. Fail closed until the owner installs/configures the module.
4. Test real Solidity validation and execution against pinned Kernel 0.3.1
   in an in-memory EVM, alongside SDK/ABI and mocked API tests. Never classify
   local simulations as Sepolia transactions or protocol-economic tests.
5. Update only relevant thesis passages from the supplied ZIP and report
   criterion-level evidence and deployment limitations. No testnet broadcasts
   or deployments are authorized by this task.

## Primary compatibility references

- Installed SDK sources: `accounts/utils/toKernelPluginManager.ts`,
  `types/kernel.ts`, `accounts/kernel/createKernelAccount.ts`.
- [Official SDK custom-validator interface](https://github.com/zerodevapp/sdk/blob/main/packages/core/types/kernel.ts)
  (the installed package, rather than current main, is the implementation reference).
- [Kernel v3.1, pinned commit 03f7f5c](https://github.com/zerodevapp/kernel/tree/03f7f5cf5871cda0070e4223f196f5b577f6cde2).
- [ZeroDev call-policy documentation](https://docs.zerodev.app/sdk/v5_3_x/permissions/policies/call)
  (conceptual comparison only; not assumed to document SDK 5.5.10 exactly).
