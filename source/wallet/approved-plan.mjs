/** Independent ABI comparison before the backend authority attests a prepared batch. */
import { encodeFunctionData, parseAbi, parseUnits } from "viem";
import { encodeCalls } from "./authorization.mjs";

export const ABI = parseAbi([
  "function approve(address spender,uint256 amount) returns (bool)",
  "function exactInputSingle((address tokenIn,address tokenOut,uint24 fee,address recipient,uint256 amountIn,uint256 amountOutMinimum,uint160 sqrtPriceLimitX96) params) payable returns (uint256)",
  "function supply(address asset,uint256 amount,address onBehalfOf,uint16 referralCode)",
  "function withdraw(address asset,uint256 amount,address to) returns (uint256)",
  "function borrow(address asset,uint256 amount,uint256 interestRateMode,uint16 referralCode,address onBehalfOf)",
  "function repay(address asset,uint256 amount,uint256 interestRateMode,address onBehalfOf) returns (uint256)",
]);

export function exactUnits(amount, decimals) {
  if (!Number.isInteger(decimals) || decimals < 0 || decimals > 255 ||
      !/^\d+(\.\d+)?$/.test(String(amount)) || (String(amount).split(".")[1]?.length || 0) > decimals)
    throw new Error("Amount is not exactly representable in token base units");
  const result = parseUnits(String(amount), decimals);
  if (result <= 0n) throw new Error("Amount must be positive");
  return result;
}
const call = (to, name, args) => ({ to, value: "0", data: encodeFunctionData({ abi: ABI, functionName: name, args }) });
const equal = (a, b) => String(a).toLowerCase() === String(b).toLowerCase();

export function assertApprovedPlan(approved, plan, account) {
  if (!equal(plan.account, account) || plan.chainId !== 11155111) throw new Error("Wrong account or network");
  let token, spender, amount, protocolCall, approvals;
  if (approved.action === "swap") {
    const r = approved.routes.find(route => equal(route.pool_address, plan.pool));
    if (!r || !equal(r.router_address, approved.verified_address) ||
        r.function_selector !== "0x04e45aaf" ||
        r.function_signature !== "exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))")
      throw new Error("Route was not retained by graph verification");
    if (!Number.isInteger(approved.slippage_bps) || approved.slippage_bps < 1 || approved.slippage_bps > 500)
      throw new Error("Unapproved slippage");
    token = r.token_in_address; spender = r.router_address;
    amount = exactUnits(approved.intent.amount, r.token_in_decimals);
    const quote = BigInt(plan.quotedAmountOut);
    const minimum = quote * BigInt(10000 - approved.slippage_bps) / 10000n;
    if (quote <= 0n || minimum <= 0n) throw new Error("Invalid quote/minimum output");
    protocolCall = call(spender, "exactInputSingle", [{ tokenIn: token, tokenOut: r.token_out_address,
      fee: r.pool_fee, recipient: account, amountIn: amount, amountOutMinimum: minimum, sqrtPriceLimitX96: 0n }]);
    approvals = true;
  } else {
    token = approved.verified_asset; spender = approved.verified_address;
    amount = exactUnits(approved.intent.amount, approved.verified_asset_decimals);
    const action = approved.action;
    if (!["supply", "withdraw", "borrow", "repay"].includes(action)) throw new Error("Unsupported action");
    if (["borrow", "repay"].includes(action) && approved.interest_rate_mode !== 2)
      throw new Error("Unapproved interest-rate mode");
    const referral = approved.referral_code;
    const args = action === "supply" ? [token, amount, account, referral]
      : action === "withdraw" ? [token, amount, account]
      : action === "borrow" ? [token, amount, 2n, referral, account]
      : [token, amount, 2n, account];
    protocolCall = call(spender, action, args);
    if (!equal(protocolCall.data.slice(0, 10), approved.verified_selector)) throw new Error("Unapproved selector");
    approvals = ["supply", "repay"].includes(action);
  }
  const options = [[protocolCall]];
  if (approvals) {
    options.push([call(token, "approve", [spender, amount]), protocolCall]);
    options.push([call(token, "approve", [spender, 0n]), call(token, "approve", [spender, amount]), protocolCall]);
  }
  // Canonical full encoding rejects every added/reordered/mutated byte and native value.
  if (!options.some(calls => equal(encodeCalls(calls), plan.callData)) ||
      !equal(encodeCalls(plan.calls), plan.callData)) throw new Error("Prepared batch differs from approved operation");
  return true;
}
