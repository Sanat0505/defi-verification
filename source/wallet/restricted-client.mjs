import { createPublicClient, encodeAbiParameters, http, keccak256, parseAbi, parseAbiParameters, zeroAddress } from "viem";
import { readFileSync } from "node:fs";
import { privateKeyToAccount } from "viem/accounts";
import { getUserOperationHash } from "viem/account-abstraction";
import { sepolia } from "viem/chains";
import { createKernelAccount, createKernelAccountClient, createZeroDevPaymasterClient } from "@zerodev/sdk";
import { getEntryPoint, KERNEL_V3_1 } from "@zerodev/sdk/constants";
import { authorizationHash, CHAIN_ID, encodePermit, EXECUTE_SELECTOR, VALIDATOR_ABI } from "./authorization.mjs";
import { recoverMessageAddress } from "viem";

const entryPoint = getEntryPoint("0.7");
const same = (a, b) => String(a).toLowerCase() === String(b).toLowerCase();
export function walletAddress() {
  const address = process.env.RESTRICTED_ACCOUNT_ADDRESS;
  if (!/^0x[\da-f]{40}$/i.test(address || "") || same(address, zeroAddress))
    throw new Error("RESTRICTED_ACCOUNT_ADDRESS must identify the development Kernel account");
  return address;
}

export async function readAuthorizationConfig() {
  const account = walletAddress();
  const validator = process.env.RESTRICTED_VALIDATOR_ADDRESS;
  if (!/^0x[\da-f]{40}$/i.test(validator || "") || same(validator, zeroAddress)) throw new Error("Validator required");
  if (!process.env.SEPOLIA_RPC) throw new Error("Sepolia RPC required");
  const publicClient = createPublicClient({ chain: sepolia, transport: http(process.env.SEPOLIA_RPC) });
  if (await publicClient.getChainId() !== CHAIN_ID) throw new Error("Wrong RPC network");
  if (!await publicClient.getCode({ address: account })) throw new Error("Account must already be deployed");
  const artifact = JSON.parse(readFileSync(new URL("./artifacts/GraphBoundValidator.json", import.meta.url), "utf8"));
  const code = await publicClient.getCode({ address: validator });
  if (!code || keccak256(code) !== keccak256(`0x${artifact.evm.deployedBytecode.object}`))
    throw new Error("Validator bytecode differs from reviewed artifact");
  const kernelAbi = parseAbi([
    "function accountId() view returns (string)",
    "function rootValidator() view returns (bytes21)",
    "function entrypoint() view returns (address)",
  ]);
  if (await publicClient.readContract({ address: account, abi: kernelAbi, functionName: "accountId" }) !== "kernel.advanced.v0.3.1" ||
      !same(await publicClient.readContract({ address: account, abi: kernelAbi, functionName: "entrypoint" }), entryPoint.address))
    throw new Error("Expected Kernel 0.3.1 / EntryPoint 0.7");
  const [authority, executor, epoch, maxGasCost] = await publicClient.readContract({
    address: validator, abi: VALIDATOR_ABI, functionName: "configs", args: [account],
  });
  if (same(authority, zeroAddress) || same(authority, executor) || maxGasCost <= 0n) throw new Error("Validator not configured");
  const root = await publicClient.readContract({ address: account, abi: kernelAbi, functionName: "rootValidator" });
  if (!root.startsWith("0x01")) throw new Error("Expected separately controlled ECDSA owner validator");
  const owner = await publicClient.readContract({ address: `0x${root.slice(4)}`,
    abi: parseAbi(["function ecdsaValidatorStorage(address) view returns (address owner)"]),
    functionName: "ecdsaValidatorStorage", args: [account] });
  if (same(owner, zeroAddress) || same(owner, executor) || same(owner, authority)) throw new Error("Owner and execution roles must be distinct");
  const installed = await publicClient.readContract({ address: account,
    abi: parseAbi(["function isAllowedSelector(bytes21,bytes4) view returns (bool)"]),
    functionName: "isAllowedSelector", args: [`0x01${validator.slice(2)}`, EXECUTE_SELECTOR] });
  if (!installed) throw new Error("Validator is not authorized for Kernel execute");
  return { account, validator, authority, executor, epoch, maxGasCost, publicClient };
}

export function toGraphValidator({ signer, permit, config }) {
  if (!same(signer.address, config.executor)) throw new Error("Wrong restricted executor key");
  const deny = async () => { throw new Error("Restricted validator only signs authorized UserOperations"); };
  const check = op => {
    if (!same(op.sender, config.account) || !same(op.callData, permit.callData) || op.factory ||
        (op.chainId !== undefined && op.chainId !== CHAIN_ID)) throw new Error("Unauthorized UserOperation");
  };
  return {
    address: config.validator, type: "local", source: "GraphBoundValidator", publicKey: signer.publicKey,
    supportedKernelVersions: "0.3.1", validatorType: "SECONDARY",
    getIdentifier: () => config.validator, getNonceKey: async () => 0n,
    // SDK 5.5.10 computes counterfactual init data even for an existing account.
    // Public configuration data grants no install authority; there is no sudo signer.
    getEnableData: async () => encodeAbiParameters(parseAbiParameters("address,address,uint256"),
      [config.authority, config.executor, config.maxGasCost]),
    isEnabled: async () => true,
    signMessage: deny, signTypedData: deny, signTransaction: deny,
    async getStubSignature(op) {
      check(op);
      return encodePermit(permit, `0x${"ff".repeat(32)}${"7a".repeat(32)}1b`);
    },
    async signUserOperation(op) {
      check(op);
      const hash = getUserOperationHash({ userOperation: { ...op, signature: "0x" },
        entryPointAddress: entryPoint.address, entryPointVersion: "0.7", chainId: CHAIN_ID });
      return encodePermit(permit, await signer.signMessage({ message: { raw: hash } }));
    },
  };
}

export async function sendAuthorized(permit) {
  const config = await readAuthorizationConfig();
  const now = Math.floor(Date.now() / 1000);
  if (permit.chainId !== CHAIN_ID || !same(permit.account, config.account) ||
      !same(permit.validator, config.validator) || !same(permit.executor, config.executor) ||
      BigInt(permit.epoch) !== config.epoch || now < permit.validAfter || now >= permit.validUntil)
    throw new Error("Permission context/validity mismatch");
  if (!same(await recoverMessageAddress({ message: { raw: authorizationHash(permit) },
    signature: permit.authoritySignature }), config.authority)) throw new Error("Invalid authority signature");
  const signer = privateKeyToAccount(process.env.RESTRICTED_EXECUTOR_PRIVATE_KEY);
  const regular = toGraphValidator({ signer, permit, config });
  const account = await createKernelAccount(config.publicClient, {
    address: config.account, plugins: { regular }, entryPoint, kernelVersion: KERNEL_V3_1,
  });
  const rpc = process.env.ZERODEV_RPC || (process.env.ZERODEV_PROJECT_ID &&
    `https://rpc.zerodev.app/api/v3/${process.env.ZERODEV_PROJECT_ID}/chain/${CHAIN_ID}`);
  if (!rpc) throw new Error("Bundler RPC required");
  const paymaster = createZeroDevPaymasterClient({ chain: sepolia, transport: http(rpc) });
  const client = createKernelAccountClient({ account, chain: sepolia, client: config.publicClient,
    bundlerTransport: http(rpc), paymaster: { getPaymasterData: userOperation => paymaster.sponsorUserOperation({ userOperation }) } });
  // Submit the frozen bytes, never rebuild or re-quote here.
  const hash = await client.sendUserOperation({ callData: permit.callData });
  const receipt = await client.waitForUserOperationReceipt({ hash });
  if (!receipt.success) throw new Error("Authorized UserOperation reverted");
  return { success: true, executed: true, tx_hash: receipt.receipt.transactionHash,
    userop_hash: hash, smart_wallet: config.account, chain_id: CHAIN_ID };
}
