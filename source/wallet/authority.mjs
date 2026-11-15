/** Backend-only attestation command. No owner key, executor key, or send method. */
import { readFileSync } from "node:fs";
import { privateKeyToAccount } from "viem/accounts";
import { keccak256, stringToHex } from "viem";
import { authorizationHash } from "./authorization.mjs";
import { assertApprovedPlan } from "./approved-plan.mjs";
import { readAuthorizationConfig } from "./restricted-client.mjs";

try {
  const { approved, plan, verificationId, expiresAt } = JSON.parse(readFileSync(0, "utf8"));
  const now = Math.floor(Date.now() / 1000);
  if (approved.decision !== "APPROVED" || approved.chain_id !== 11155111 ||
      approved.intent.chain_id !== 11155111 || approved.intent.action !== approved.action ||
      typeof verificationId !== "string" || verificationId.length < 20 || expiresAt <= now)
    throw new Error("Live retained graph approval required");
  const config = await readAuthorizationConfig();
  if (String(approved.smart_account).toLowerCase() !== config.account.toLowerCase())
    throw new Error("Smart account changed since graph approval");
  assertApprovedPlan(approved, plan, config.account);
  const signer = privateKeyToAccount(process.env.GRAPH_AUTHORITY_PRIVATE_KEY);
  if (signer.address.toLowerCase() !== config.authority.toLowerCase()) throw new Error("Wrong authority key");
  const permit = { chainId: 11155111, account: config.account, validator: config.validator,
    executor: config.executor, epoch: config.epoch.toString(),
    approvalId: keccak256(stringToHex(verificationId)), callData: plan.callData,
    validAfter: now - 5, validUntil: Math.min(now + 120, Math.floor(expiresAt)) };
  permit.authoritySignature = await signer.signMessage({ message: { raw: authorizationHash(permit) } });
  console.log(JSON.stringify({ success: true, permit }));
} catch {
  // Provider errors can include credential-bearing URLs; do not echo them.
  console.log(JSON.stringify({ success: false, reason: "Graph authorization issuance failed; check approved plan and installed configuration" }));
  process.exitCode = 1;
}
