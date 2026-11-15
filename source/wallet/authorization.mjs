/** Shared byte encodings. No credentials, I/O, signing, or broadcasting. */
import {
  concatHex, encodeAbiParameters, encodeFunctionData, keccak256, parseAbi,
  parseAbiParameters, stringToHex, toHex, zeroAddress,
} from "viem";

export const CHAIN_ID = 11155111;
export const EXECUTE_SELECTOR = "0xe9ae5c53";
export const EXECUTE_ABI = parseAbi(["function execute(bytes32 mode, bytes executionCalldata) payable"]);
export const VALIDATOR_ABI = parseAbi([
  "function configs(address) view returns (address authority, address executor, uint256 epoch, uint256 maxGasCost)",
  "function used(address, bytes32) view returns (bool)",
  "function isInitialized(address) view returns (bool)",
]);
export const PERMIT_ABI = parseAbiParameters(
  "(bytes32 approvalId, uint48 validAfter, uint48 validUntil, bytes authoritySignature, bytes executorSignature)",
);
export const DOMAIN = keccak256(stringToHex("DeFiGraphAuthorization:v1"));

export function encodeCalls(calls) {
  if (!Array.isArray(calls) || calls.length < 1 || calls.length > 3) throw new Error("Invalid call count");
  const data = calls.length === 1
    ? concatHex([calls[0].to, toHex(BigInt(calls[0].value), { size: 32 }), calls[0].data])
    : encodeAbiParameters(parseAbiParameters("(address target,uint256 value,bytes callData)[]"),
      [calls.map(c => ({ target: c.to, value: BigInt(c.value), callData: c.data }))]);
  const mode = calls.length === 1 ? toHex(0, { size: 32 }) : `0x01${"00".repeat(31)}`;
  return encodeFunctionData({ abi: EXECUTE_ABI, functionName: "execute", args: [mode, data] });
}

export function authorizationHash(p) {
  return keccak256(encodeAbiParameters(
    parseAbiParameters("bytes32,uint256,address,address,address,uint256,bytes32,bytes32,uint48,uint48"),
    [DOMAIN, BigInt(p.chainId), p.validator, p.account, p.executor, BigInt(p.epoch),
      p.approvalId, keccak256(p.callData), p.validAfter, p.validUntil],
  ));
}

export function encodePermit(p, executorSignature) {
  return encodeAbiParameters(PERMIT_ABI, [{
    approvalId: p.approvalId, validAfter: p.validAfter, validUntil: p.validUntil,
    authoritySignature: p.authoritySignature, executorSignature,
  }]);
}

export function installationCall({ account, validator, authority, executor, maxGasCost }) {
  if ([account, validator, authority, executor].some(x => !/^0x[\da-f]{40}$/i.test(x) || x === zeroAddress))
    throw new Error("Installation requires nonzero addresses");
  if (authority.toLowerCase() === executor.toLowerCase() || BigInt(maxGasCost) <= 0n)
    throw new Error("Distinct roles and a positive gas budget are required");
  const validatorData = encodeAbiParameters(parseAbiParameters("address,address,uint256"),
    [authority, executor, BigInt(maxGasCost)]);
  // Kernel 0.3.1 installModule validator layout; address(0) means no hook.
  const initData = concatHex([zeroAddress,
    encodeAbiParameters(parseAbiParameters("bytes,bytes,bytes"), [validatorData, "0x", EXECUTE_SELECTOR])]);
  return { to: account, value: "0", data: encodeFunctionData({
    abi: parseAbi(["function installModule(uint256 moduleType,address module,bytes initData) payable"]),
    functionName: "installModule", args: [1n, validator, initData],
  }) };
}
