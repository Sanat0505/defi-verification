// Unit-test the actual result-rendering function; no DOM, server or wallet calls.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../static/app.js"), "utf8");
const start = source.indexOf("function renderVerification(data)");
const end = source.indexOf("async function executeTransaction(", start);
assert(start >= 0 && end > start);
const renderSource = source.slice(start, end);

function render(data) {
  let output = "";
  vm.runInNewContext(renderSource + "\nrenderVerification(payload);", {
    payload: data,
    // Fixture strings are controlled; HTML escaping is a separate UI concern.
    esc: String,
    addAIMsg: (html) => { output += html; },
    showErrToast: (message) => { throw new Error(message); },
  });
  return output;
}

const approved = {decision: "APPROVED", executable: true, verification_id: "fixture-only",
  intent: {protocol: "Uniswap V3", action: "swap", amount: "10", token_in: "USDC", token_out: "WETH"}};
for (const [bps, sourceName, expected] of [
  [25, "user", "0.25% (your limit)"],
  [100, "configured_default", "1.00% (configured default)"],
  [1, "user", "0.01% (your limit)"],
]) {
  const html = render({...approved, execution_parameters: {slippage_bps: bps, slippage_source: sourceName}});
  assert(html.includes(expected));
  assert(html.includes("Maximum slippage"));
  assert(html.includes("Execute Transaction"));
}
assert(!render(approved).includes("Maximum slippage"));
const blocked = render({decision: "UNSUPPORTED", message: "Unsupported deadline"});
assert(blocked.includes("Unsupported deadline"));
assert(!blocked.includes("Execute Transaction"));
console.log("5 result-rendering fixtures passed (no browser, network or wallet).");
