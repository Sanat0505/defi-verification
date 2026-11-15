import assert from "node:assert/strict";
import { before, after, test } from "node:test";
import ganache from "ganache";
import {
  createPublicClient, createWalletClient, custom, decodeErrorResult, encodeFunctionData, encodeAbiParameters,
  keccak256, parseAbiParameters, parseEther, stringToHex, toHex, zeroAddress, parseEventLogs,
} from "viem";
import { generatePrivateKey, privateKeyToAccount } from "viem/accounts";
import { toUserOperation } from "viem/account-abstraction";
import { sepolia } from "viem/chains";
import { createKernelAccount } from "@zerodev/sdk";
import { getEntryPoint, KERNEL_V3_1 } from "@zerodev/sdk/constants";
import { compile } from "./compile.mjs";
import { ABI, assertApprovedPlan, exactUnits } from "../approved-plan.mjs";
import { authorizationHash, encodeCalls, encodePermit, installationCall, EXECUTE_SELECTOR } from "../authorization.mjs";
import { toGraphValidator } from "../restricted-client.mjs";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

let artifacts, f;
const bytes32 = n => toHex(n, { size: 32 });
const addr = n => toHex(n, { size: 20 });
const makeCall = (to, name, args) => ({ to, value: "0", data: encodeFunctionData({ abi: ABI, functionName: name, args }) });

async function fixture(chainId = 11155111) {
  const provider = ganache.provider({ logging: { quiet: true }, chain: { chainId, hardfork: "shanghai" },
    miner: { blockGasLimit: 30000000 }, wallet: { totalAccounts: 3 } });
  const chain = { ...sepolia, id: chainId };
  const transport = custom(provider);
  const publicClient = createPublicClient({ transport, chain });
  const owner = privateKeyToAccount(Object.values(provider.getInitialAccounts())[0].secretKey);
  const executor = privateKeyToAccount(generatePrivateKey());
  const authority = privateKeyToAccount(generatePrivateKey());
  const wallet = createWalletClient({ transport, chain, account: owner });
  async function deploy(name, args = []) {
    const a = artifacts[name];
    const hash = await wallet.deployContract({ abi: a.abi, bytecode: `0x${a.evm.bytecode.object}`, args, gas: 14000000n });
    const receipt = await publicClient.waitForTransactionReceipt({ hash });
    assert.equal(receipt.status, "success", `deploy ${name}`);
    return receipt.contractAddress;
  }
  async function write(address, name, fn, args, value = 0n) {
    const hash = await wallet.writeContract({ address, abi: artifacts[name].abi, functionName: fn, args, value, gas: 12000000n });
    const receipt = await publicClient.waitForTransactionReceipt({ hash });
    assert.equal(receipt.status, "success", fn);
    return receipt;
  }
  const deployedEp = await deploy("EntryPoint");
  // Place the actual deployed code at the canonical address so the unmodified
  // production SDK adapter can also sign a real, locally validated UserOperation.
  const ep = getEntryPoint("0.7").address;
  await provider.request({ method: "evm_setAccountCode", params: [ep, await publicClient.getCode({ address: deployedEp })] });
  const root = await deploy("ECDSAValidator");
  const validator = await deploy("GraphBoundValidator");
  const impl = await deploy("Kernel", [ep]);
  const factory = await deploy("KernelFactory", [impl]);
  const token = await deploy("RecordingTarget");
  const protocol = await deploy("RecordingTarget");
  async function createAccount(salt = 0n) {
    const init = encodeFunctionData({ abi: artifacts.Kernel.abi, functionName: "initialize",
      args: [`0x01${root.slice(2)}`, zeroAddress, owner.address, "0x", []] });
    const account = await publicClient.readContract({ address: factory, abi: artifacts.KernelFactory.abi,
      functionName: "getAddress", args: [init, bytes32(salt)] });
    await write(factory, "KernelFactory", "createAccount", [init, bytes32(salt)]);
    const install = installationCall({ account, validator, authority: authority.address,
      executor: executor.address, maxGasCost: parseEther("0.05").toString() });
    // Actual owner hook authorizes installation directly on Kernel.
    const hash = await wallet.sendTransaction({ to: account, data: install.data, gas: 2000000n });
    assert.equal((await publicClient.waitForTransactionReceipt({ hash })).status, "success", "owner installation");
    await write(ep, "EntryPoint", "depositTo", [account], parseEther("2"));
    return account;
  }
  const account = await createAccount();
  const config = { account, validator, executor: executor.address, authority: authority.address, epoch: 1n, maxGasCost: parseEther("0.05") };
  let id = 0;
  async function permit(calls, changes = {}) {
    const now = Number((await publicClient.getBlock()).timestamp);
    const p = { chainId, ...config, epoch: "1", approvalId: keccak256(stringToHex(`approval-${++id}`)),
      callData: encodeCalls(calls), validAfter: now - 5, validUntil: now + 120, ...changes };
    p.authoritySignature = await authority.signMessage({ message: { raw: authorizationHash(p) } });
    return p;
  }
  async function operation(p, changes = {}, signer = executor) {
    const key = BigInt(`0x0001${validator.slice(2)}0000`);
    const nonce = await publicClient.readContract({ address: ep, abi: artifacts.EntryPoint.abi,
      functionName: "getNonce", args: [changes.sender || account, key] });
    const op = { sender: account, nonce, initCode: "0x", callData: p.callData,
      accountGasLimits: `0x${toHex(1000000n, { size: 16 }).slice(2)}${toHex(1000000n, { size: 16 }).slice(2)}`,
      preVerificationGas: 100000n,
      gasFees: `0x${toHex(1000000000n, { size: 16 }).slice(2)}${toHex(2000000000n, { size: 16 }).slice(2)}`,
      paymasterAndData: "0x", signature: "0x", ...changes };
    const hash = await publicClient.readContract({ address: ep, abi: artifacts.EntryPoint.abi,
      functionName: "getUserOpHash", args: [op] });
    op.signature = encodePermit(p, await signer.signMessage({ message: { raw: hash } }));
    return op;
  }
  async function simulate(op) {
    try {
      return await provider.request({ method: "eth_call", params: [{ to: ep, from: owner.address,
        data: encodeFunctionData({ abi: artifacts.EntryPoint.abi, functionName: "handleOps", args: [[op], owner.address] }),
        gas: toHex(12000000n) }, "latest"] });
    } catch (error) {
      if (typeof error.data === "string" && error.data !== "0x") {
        const decoded = decodeErrorResult({ abi: artifacts.EntryPoint.abi, data: error.data });
        throw new Error(`${decoded.errorName}: ${decoded.args?.join(" ")}`);
      }
      throw error;
    }
  }
  async function submit(op) {
    await simulate(op);
    const receipt = await write(ep, "EntryPoint", "handleOps", [[op], owner.address]);
    const events = parseEventLogs({ abi: artifacts.EntryPoint.abi, logs: receipt.logs, eventName: "UserOperationEvent" });
    assert.equal(events[0].args.success, true, "UserOperation execution");
    return receipt;
  }
  return { provider, publicClient, wallet, owner, executor, authority, ep, validator, account,
    config, token, protocol, permit, operation, simulate, submit, createAccount };
}

before(async () => { artifacts = compile(); f = await fixture(); });
after(async () => { if (f) await f.provider.disconnect(); });

function callsFor(action, ctx = f) {
  const { account, token, protocol } = ctx;
  const amount = 10000000n;
  const args = action === "swap" ? [{ tokenIn: token, tokenOut: addr(99), fee: 3000,
    recipient: account, amountIn: amount, amountOutMinimum: 990n, sqrtPriceLimitX96: 0n }]
    : action === "supply" ? [token, amount, account, 0]
    : action === "withdraw" ? [token, amount, account]
    : action === "borrow" ? [token, amount, 2n, 0, account]
    : [token, amount, 2n, account];
  const result = [makeCall(protocol, action === "swap" ? "exactInputSingle" : action, args)];
  if (["swap", "supply", "repay"].includes(action))
    result.unshift(makeCall(token, "approve", [protocol, 0n]), makeCall(token, "approve", [protocol, amount]));
  return result;
}

for (const action of ["swap", "supply", "withdraw", "borrow", "repay"]) {
  test(`actual EntryPoint + Kernel: authorized ${action} and every batch call execute`, async () => {
    const calls = callsFor(action);
    const p = await f.permit(calls);
    const receipt = await f.submit(await f.operation(p));
    const events = parseEventLogs({ abi: artifacts.RecordingTarget.abi, logs: receipt.logs, eventName: "Called" });
    assert.equal(events.length, calls.length);
    events.forEach((e, i) => {
      assert.equal(e.args.caller.toLowerCase(), f.account.toLowerCase());
      assert.equal(e.args.data, calls[i].data);
      assert.equal(e.args.value, 0n);
    });
  });
}

const mutations = {
  "wrong destination": c => { c[2].to = addr(88); },
  "wrong function selector": c => { c[2].data = `0xdeadbeef${c[2].data.slice(10)}`; },
  "modified input token": c => { c[2].data = replaceWord(c[2].data, 0, addr(88)); },
  "modified output token": c => { c[2].data = replaceWord(c[2].data, 1, addr(88)); },
  "modified fee tier": c => { c[2].data = replaceWord(c[2].data, 2, toHex(500)); },
  "modified recipient": c => { c[2].data = replaceWord(c[2].data, 3, addr(88)); },
  "modified amount": c => { c[2].data = replaceWord(c[2].data, 4, toHex(999)); },
  "lower minimum output": c => { c[2].data = replaceWord(c[2].data, 5, toHex(1)); },
  "modified price limit": c => { c[2].data = replaceWord(c[2].data, 6, toHex(1)); },
  "modified approval spender": c => { c[1].data = replaceWord(c[1].data, 0, addr(88)); },
  "unlimited approval": c => { c[1].data = replaceWord(c[1].data, 1, bytes32((1n << 256n) - 1n)); },
  "modified reset spender": c => { c[0].data = replaceWord(c[0].data, 0, addr(88)); },
  "unexpected additional call": c => { c.push(c[2]); },
  "removed approval call": c => { c.shift(); },
  "reordered calls": c => { c.reverse(); },
  "native ETH value": c => { c[2].value = "1"; },
};
function replaceWord(data, index, value) {
  return data.slice(0, 10 + index * 64) + value.slice(2).padStart(64, "0") + data.slice(10 + (index + 1) * 64);
}
// encodeCalls intentionally caps production batches at three; encode arbitrary
// attacker batches here so the CONTRACT, rather than that JS check, rejects them.
function attackerEncode(calls) {
  return encodeFunctionData({ abi: artifacts.Kernel.abi, functionName: "execute",
    args: [`0x01${"00".repeat(31)}`, encodeAbiParameters(parseAbiParameters("(address,uint256,bytes)[]"),
      [calls.map(c => [c.to, BigInt(c.value), c.data])])] });
}
for (const [name, mutate] of Object.entries(mutations)) {
  test(`contract rejects ${name} even with genuine restricted-key signature`, async () => {
    const calls = callsFor("swap");
    const p = await f.permit(calls);
    const changed = structuredClone(calls); mutate(changed);
    const op = await f.operation(p, { callData: attackerEncode(changed) });
    await assert.rejects(f.simulate(op), /AA24|signature error/);
  });
}

for (const action of ["supply", "withdraw", "borrow", "repay"]) {
  for (const [field, index] of [["asset", 0], ["amount", 1], ["recipient", action === "borrow" ? 4 : action === "repay" ? 3 : 2]]) {
    test(`contract rejects Aave ${action} modified ${field}`, async () => {
      const calls = callsFor(action), p = await f.permit(calls);
      calls.at(-1).data = replaceWord(calls.at(-1).data, index, addr(88));
      await assert.rejects(f.simulate(await f.operation(p, { callData: encodeCalls(calls) })), /AA24/);
    });
  }
}
for (const action of ["borrow", "repay"]) test(`contract rejects ${action} rate mode change`, async () => {
  const calls = callsFor(action), p = await f.permit(calls);
  calls.at(-1).data = replaceWord(calls.at(-1).data, 2, toHex(1));
  await assert.rejects(f.simulate(await f.operation(p, { callData: encodeCalls(calls) })), /AA24/);
});

test("EntryPoint rejects expired and not-yet-valid permissions", async () => {
  const now = Number((await f.publicClient.getBlock()).timestamp);
  for (const window of [{ validAfter: now - 100, validUntil: now - 1 }, { validAfter: now + 30, validUntil: now + 100 }]) {
    const p = await f.permit(callsFor("withdraw"), window);
    await assert.rejects(f.simulate(await f.operation(p)), /AA22/);
  }
});
test("contract rejects permission lifetime above 125 seconds", async () => {
  const p = await f.permit(callsFor("withdraw"), { validAfter: 1, validUntil: 9999999999 });
  await assert.rejects(f.simulate(await f.operation(p)), /AA24/);
});
test("one-use approval cannot be replayed with a fresh valid EntryPoint nonce", async () => {
  const p = await f.permit(callsFor("withdraw"));
  await f.submit(await f.operation(p));
  await assert.rejects(f.simulate(await f.operation(p)), /AA24/);
});
test("restricted key cannot forge graph approval", async () => {
  const p = await f.permit(callsFor("withdraw"));
  p.authoritySignature = await f.executor.signMessage({ message: { raw: authorizationHash(p) } });
  await assert.rejects(f.simulate(await f.operation(p)), /AA24/);
});
test("missing graph approval is rejected by real contract validation", async () => {
  const p = await f.permit(callsFor("withdraw")); p.authoritySignature = "0x";
  await assert.rejects(f.simulate(await f.operation(p)), /AA24/);
});
test("wrong executor signature fails", async () => {
  const p = await f.permit(callsFor("withdraw"));
  await assert.rejects(f.simulate(await f.operation(p, {}, f.authority)), /AA24/);
});
test("account/domain/epoch changes fail", async () => {
  for (const changes of [{ account: addr(66) }, { chainId: 1 }, { validator: addr(77) }, { epoch: "2" }]) {
    const p = await f.permit(callsFor("withdraw"), changes);
    await assert.rejects(f.simulate(await f.operation(p)), /AA24/);
  }
});
test("wrong smart account cannot reuse a valid authorization", async () => {
  const other = await f.createAccount(1n), p = await f.permit(callsFor("withdraw"));
  await assert.rejects(f.simulate(await f.operation(p, { sender: other })), /AA24/);
});
test("gas cost budget is enforced on-chain", async () => {
  const p = await f.permit(callsFor("withdraw"));
  const gasFees = `0x${toHex(1000000000n, { size: 16 }).slice(2)}${toHex(100000000000n, { size: 16 }).slice(2)}`;
  await assert.rejects(f.simulate(await f.operation(p, { gasFees })), /AA24/);
});
test("sudo nonce fallback cannot use the restricted key", async () => {
  const p = await f.permit(callsFor("withdraw"));
  const op = await f.operation(p, { nonce: 0n });
  const hash = await f.publicClient.readContract({ address: f.ep, abi: artifacts.EntryPoint.abi, functionName: "getUserOpHash", args: [op] });
  op.signature = await f.executor.signMessage({ message: { raw: hash } });
  await assert.rejects(f.simulate(op), /AA24/);
});
test("direct Kernel execute and module installation by restricted EOA fail", async () => {
  const callData = encodeCalls(callsFor("withdraw"));
  await assert.rejects(f.publicClient.call({ account: f.executor.address, to: f.account, data: callData }));
  const install = installationCall({ ...f.config, maxGasCost: "1" });
  await assert.rejects(f.publicClient.call({ account: f.executor.address, to: f.account, data: install.data }));
});
test("ERC-1271 unrestricted message authorization is disabled", async () => {
  const result = await f.publicClient.readContract({ address: f.validator, abi: artifacts.GraphBoundValidator.abi,
    functionName: "isValidSignatureWithSender", args: [f.executor.address, bytes32(1), "0x"] });
  assert.equal(result, "0xffffffff");
});
test("contract fails on another EVM network even with correctly signed domain", async () => {
  const other = await fixture(1);
  try {
    const p = await other.permit(callsFor("withdraw", other));
    await assert.rejects(other.simulate(await other.operation(p)), /AA24/);
  } finally { await other.provider.disconnect(); }
});

test("installed SDK uses regular-only nonce and exactly matching Kernel calldata", async () => {
  const p = await f.permit(callsFor("swap"));
  const regular = toGraphValidator({ signer: f.executor, permit: p, config: f.config });
  const entryPoint = { ...getEntryPoint("0.7"), address: f.ep };
  const account = await createKernelAccount(f.publicClient, { address: f.account, plugins: { regular }, entryPoint, kernelVersion: KERNEL_V3_1 });
  const plugins = account.kernelPluginManager;
  assert.equal(account.kernelPluginManager.activeValidatorMode, "regular");
  assert.equal(account.kernelPluginManager.sudoValidator, undefined);
  assert.equal(await account.encodeCalls(callsFor("swap").map(c => ({ ...c, value: BigInt(c.value) }))), p.callData);
  assert.equal((await plugins.getNonceKey(f.account)).toString(16), BigInt(`0x0001${f.validator.slice(2)}0000`).toString(16));
  await assert.rejects(regular.signMessage({ message: "anything" }));
  assert.ok((await regular.getEnableData()).startsWith("0x"));
  const op = await f.operation(p);
  op.signature = await account.signUserOperation(toUserOperation(op));
  await f.submit(op);
});

test("exact token units reject silent rounding", () => {
  assert.equal(exactUnits("10", 6), 10000000n);
  assert.throws(() => exactUnits("0.0000001", 6));
});

function approvedFor(action) {
  return { action, verified_address: f.protocol, verified_asset: f.token,
    verified_asset_decimals: 6, referral_code: 0, interest_rate_mode: 2, slippage_bps: 100,
    verified_selector: callsFor(action).at(-1).data.slice(0, 10), intent: { amount: "10" },
    routes: [{ pool_address: addr(7), router_address: f.protocol, token_in_address: f.token,
      token_out_address: addr(99), pool_fee: 3000, token_in_decimals: 6,
      function_selector: "0x04e45aaf",
      function_signature: "exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))" }] };
}
function planFor(calls) {
  return { account: f.account, chainId: 11155111, calls, callData: encodeCalls(calls),
    pool: addr(7), quotedAmountOut: "1000" };
}
for (const action of ["swap", "supply", "withdraw", "borrow", "repay"]) {
  test(`authority independently checks approved ${action} ABI and allowed approval variants`, () => {
    const calls = callsFor(action);
    assertApprovedPlan(approvedFor(action), planFor(calls), f.account);
    if (calls.length > 1) {
      assertApprovedPlan(approvedFor(action), planFor(calls.slice(1)), f.account);
      assertApprovedPlan(approvedFor(action), planFor(calls.slice(2)), f.account);
    }
  });
}
for (const [name, mutate] of Object.entries(mutations)) {
  // A reset is optional BEFORE issuance; removing it AFTER issuance is tested
  // above against the exact on-chain calldata commitment.
  if (name === "removed approval call") continue;
  test(`authority refuses to attest ${name}`, () => {
    const calls = callsFor("swap"); mutate(calls);
    assert.throws(() => assertApprovedPlan(approvedFor("swap"), planFor(calls), f.account));
  });
}
test("compiled validator artifact matches the tested contract", () => {
  const artifact = JSON.parse(readFileSync(new URL("../artifacts/GraphBoundValidator.json", import.meta.url)));
  assert.equal(artifact.evm.deployedBytecode.object, artifacts.GraphBoundValidator.evm.deployedBytecode.object);
});
for (const command of ["send_swap", "send_aave", "send_userop"]) {
  test(`raw ${command} cannot use an inherited owner credential`, () => {
    const result = spawnSync(process.execPath, [new URL("../wallet.mjs", import.meta.url).pathname.replace(/^\/([A-Z]:)/i, "$1"), command, "{}"],
      { encoding: "utf8", env: { ...process.env, PRIVATE_KEY: "owner-sentinel" } });
    const output = JSON.parse(result.stdout.trim());
    assert.equal(output.executed, false);
    assert.equal(output.success, false);
    assert.ok(!result.stdout.includes("owner-sentinel"));
  });
}
