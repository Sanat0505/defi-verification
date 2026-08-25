/**
 * wallet.mjs — ZeroDev ERC-4337 wallet for Ethereum Sepolia
 * Called from Python as a subprocess.
 *
 * OPTIMIZATION: Lazy-loads heavy dependencies (viem, ZeroDev) only for blockchain commands.
 * File I/O commands (add_whitelist, check_session) start instantly.
 *
 * Usage:
 *   node wallet.mjs create_wallet
 *   node wallet.mjs add_whitelist '{"address":"0x..."}'
 *   node wallet.mjs check_session '{"to":"0x...","value_eth":0.001}'
 *   node wallet.mjs prepare_swap '{"amount":"0.001","routes":[...]}'
 *   node wallet.mjs send_swap '{"amount":"0.001","routes":[...]}'
 */

import dotenv from "dotenv";
import fs from "fs";
import { fileURLToPath } from "url";
import { dirname, resolve } from "path";
import { isAddress } from "viem"; // Lightweight util-only import

// ── Load .env from project root ───────────────────────────

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

dotenv.config({
  path: resolve(__dirname, "../.env"),
  quiet: true,
});

// ── Config ────────────────────────────────────────────────

const CHAIN_RPC = process.env.SEPOLIA_RPC;
const ZERODEV_PROJECT_ID = process.env.ZERODEV_PROJECT_ID;
const ZERODEV_RPC =
  process.env.ZERODEV_RPC ||
  (ZERODEV_PROJECT_ID
    ? `https://rpc.zerodev.app/api/v3/${ZERODEV_PROJECT_ID}/chain/11155111`
    : null);

const PRIVATE_KEY = process.env.PRIVATE_KEY;

const SESSION_LIMIT_ETH = 0.005;
const SESSION_DURATION_MS = 24 * 60 * 60 * 1000;
const APPROVED_SWAP_SIGNATURE =
  "exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))";
const APPROVED_SWAP_SELECTOR = "0x04e45aaf";

const WHITELIST_FILE = resolve(__dirname, "session-whitelist.json");

const ERC20_ABI = [
  {
    type: "function",
    name: "balanceOf",
    stateMutability: "view",
    inputs: [{ name: "account", type: "address" }],
    outputs: [{ name: "", type: "uint256" }],
  },
  {
    type: "function",
    name: "allowance",
    stateMutability: "view",
    inputs: [
      { name: "owner", type: "address" },
      { name: "spender", type: "address" },
    ],
    outputs: [{ name: "", type: "uint256" }],
  },
  {
    type: "function",
    name: "approve",
    stateMutability: "nonpayable",
    inputs: [
      { name: "spender", type: "address" },
      { name: "amount", type: "uint256" },
    ],
    outputs: [{ name: "", type: "bool" }],
  },
];

const QUOTER_V2_ABI = [
  {
    type: "function",
    name: "quoteExactInputSingle",
    stateMutability: "nonpayable",
    inputs: [
      {
        name: "params",
        type: "tuple",
        components: [
          { name: "tokenIn", type: "address" },
          { name: "tokenOut", type: "address" },
          { name: "amountIn", type: "uint256" },
          { name: "fee", type: "uint24" },
          { name: "sqrtPriceLimitX96", type: "uint160" },
        ],
      },
    ],
    outputs: [
      { name: "amountOut", type: "uint256" },
      { name: "sqrtPriceX96After", type: "uint160" },
      { name: "initializedTicksCrossed", type: "uint32" },
      { name: "gasEstimate", type: "uint256" },
    ],
  },
];

const SWAP_ROUTER_02_ABI = [
  {
    type: "function",
    name: "exactInputSingle",
    stateMutability: "payable",
    inputs: [
      {
        name: "params",
        type: "tuple",
        components: [
          { name: "tokenIn", type: "address" },
          { name: "tokenOut", type: "address" },
          { name: "fee", type: "uint24" },
          { name: "recipient", type: "address" },
          { name: "amountIn", type: "uint256" },
          { name: "amountOutMinimum", type: "uint256" },
          { name: "sqrtPriceLimitX96", type: "uint160" },
        ],
      },
    ],
    outputs: [{ name: "amountOut", type: "uint256" }],
  },
];

// ── JSON response helper ──────────────────────────────────

function respond(obj, exitCode = 0) {
  console.log(JSON.stringify(obj));
  process.exit(exitCode);
}

function fail(message, extra = {}) {
  respond(
    {
      success: false,
      error: message,
      ...extra,
    },
    1,
  );
}

// ── Lazy loader for heavy dependencies ────────────────────
// Only load viem, ZeroDev, etc. when blockchain operations needed

let zerodevImportsLoaded = false;
let ENTRY_POINT, KERNEL_VER, CHAIN;

async function loadZeroDevDependencies() {
  if (zerodevImportsLoaded) return;

  const {
    createKernelAccount,
    createKernelAccountClient: _createKernelAccountClient,
    createZeroDevPaymasterClient,
  } = await import("@zerodev/sdk");

  const { KERNEL_V3_1, getEntryPoint } = await import("@zerodev/sdk/constants");
  const { signerToEcdsaValidator } = await import("@zerodev/ecdsa-validator");
  const {
    http,
    createPublicClient: _createPublicClient,
    parseEther: _parseEther,
    parseUnits: _parseUnits,
    formatUnits: _formatUnits,
    encodeFunctionData: _encodeFunctionData,
  } = await import("viem");
  const { privateKeyToAccount } = await import("viem/accounts");
  const { sepolia } = await import("viem/chains");

  ENTRY_POINT = getEntryPoint("0.7");
  KERNEL_VER = KERNEL_V3_1;
  CHAIN = sepolia;

  // Store in global scope for buildClients to use
  globalThis.__createKernelAccount = createKernelAccount;
  globalThis.__createKernelAccountClient = _createKernelAccountClient;
  globalThis.__createZeroDevPaymasterClient = createZeroDevPaymasterClient;
  globalThis.__http = http;
  globalThis.__createPublicClient = _createPublicClient;
  globalThis.__parseEther = _parseEther;
  globalThis.__parseUnits = _parseUnits;
  globalThis.__formatUnits = _formatUnits;
  globalThis.__encodeFunctionData = _encodeFunctionData;
  globalThis.__signerToEcdsaValidator = signerToEcdsaValidator;
  globalThis.__privateKeyToAccount = privateKeyToAccount;
  zerodevImportsLoaded = true;
}

function loadWhitelist() {
  try {
    if (!fs.existsSync(WHITELIST_FILE)) {
      return {
        created_at: Date.now(),
        expires_at: Date.now() + SESSION_DURATION_MS,
        addresses: [],
      };
    }

    const raw = fs.readFileSync(WHITELIST_FILE, "utf8");
    const data = JSON.parse(raw);

    if (!data.expires_at || Date.now() > data.expires_at) {
      return {
        created_at: Date.now(),
        expires_at: Date.now() + SESSION_DURATION_MS,
        addresses: [],
      };
    }

    return {
      created_at: data.created_at || Date.now(),
      expires_at: data.expires_at,
      addresses: Array.isArray(data.addresses) ? data.addresses : [],
    };
  } catch {
    return {
      created_at: Date.now(),
      expires_at: Date.now() + SESSION_DURATION_MS,
      addresses: [],
    };
  }
}

function saveWhitelist(data) {
  fs.writeFileSync(WHITELIST_FILE, JSON.stringify(data, null, 2), "utf8");
}

function addToWhitelist(args) {
  const address = args.address;

  if (!address || !isAddress(address)) {
    respond({
      success: false,
      error: "Invalid address for whitelist",
    });
  }

  const data = loadWhitelist();
  const normalized = address.toLowerCase();

  if (!data.addresses.includes(normalized)) {
    data.addresses.push(normalized);
  }

  saveWhitelist(data);

  respond({
    success: true,
    whitelisted: address,
    expires_at: new Date(data.expires_at).toISOString(),
  });
}

// ── Session checking ──────────────────────────────────────

function checkSession(to, valueEth) {
  if (!to || !isAddress(to)) {
    return {
      ok: false,
      reason: "Invalid destination address",
    };
  }

  if (typeof valueEth !== "number" || Number.isNaN(valueEth)) {
    return {
      ok: false,
      reason: "Invalid value_eth",
    };
  }

  if (valueEth < 0) {
    return {
      ok: false,
      reason: "Native value cannot be negative",
    };
  }

  if (valueEth > SESSION_LIMIT_ETH) {
    return {
      ok: false,
      reason: `Amount ${valueEth} ETH exceeds session limit ${SESSION_LIMIT_ETH} ETH`,
    };
  }

  const data = loadWhitelist();

  if (Date.now() > data.expires_at) {
    return {
      ok: false,
      reason: "Session key expired",
    };
  }

  const normalized = to.toLowerCase();

  if (!data.addresses.includes(normalized)) {
    return {
      ok: false,
      reason: `Address ${to.slice(0, 10)}... not whitelisted by graph layer`,
    };
  }

  return {
    ok: true,
  };
}

function checkSessionCommand(args) {
  const result = checkSession(args.to, args.value_eth);

  respond({
    success: true,
    allowed: result.ok,
    reason: result.ok ? "Session check passed" : result.reason,
  });
}

// ── ZeroDev client builder ────────────────────────────────

async function buildClients() {
  await loadZeroDevDependencies(); // Ensure deps are loaded

  if (!PRIVATE_KEY) {
    throw new Error("PRIVATE_KEY not set in environment");
  }

  if (!PRIVATE_KEY.startsWith("0x")) {
    throw new Error("PRIVATE_KEY must start with 0x");
  }

  if (!CHAIN_RPC) {
    throw new Error("SEPOLIA_RPC not set in environment");
  }

  if (!ZERODEV_RPC) {
    throw new Error("Set ZERODEV_PROJECT_ID or ZERODEV_RPC in environment");
  }

  const signer = globalThis.__privateKeyToAccount(PRIVATE_KEY);

  const publicClient = globalThis.__createPublicClient({
    chain: CHAIN,
    transport: globalThis.__http(CHAIN_RPC),
  });

  const ecdsaValidator = await globalThis.__signerToEcdsaValidator(
    publicClient,
    {
      signer,
      entryPoint: ENTRY_POINT,
      kernelVersion: KERNEL_VER,
    },
  );

  const account = await globalThis.__createKernelAccount(publicClient, {
    plugins: {
      sudo: ecdsaValidator,
    },
    entryPoint: ENTRY_POINT,
    kernelVersion: KERNEL_VER,
  });

  const paymasterClient = globalThis.__createZeroDevPaymasterClient({
    chain: CHAIN,
    transport: globalThis.__http(ZERODEV_RPC),
  });

  const kernelClient = globalThis.__createKernelAccountClient({
    account,
    chain: CHAIN,
    client: publicClient,
    bundlerTransport: globalThis.__http(ZERODEV_RPC),
    paymaster: {
      getPaymasterData: async (userOperation) => {
        return paymasterClient.sponsorUserOperation({
          userOperation,
        });
      },
    },
  });

  return {
    account,
    kernelClient,
    publicClient,
  };
}

// ── Commands ──────────────────────────────────────────────

async function createWallet() {
  await loadZeroDevDependencies(); // Ensure deps are loaded

  const { account } = await buildClients();

  respond({
    success: true,
    smart_wallet_address: account.address,
    chain: "ethereum-sepolia",
    chain_id: 11155111,
    type: "ERC-4337 Kernel Account",
  });
}

function validateRoute(route) {
  if (route?.function_signature !== APPROVED_SWAP_SIGNATURE) {
    throw new Error("Knowledge graph did not authorize exactInputSingle");
  }
  if (String(route?.function_selector || "").toLowerCase() !== APPROVED_SWAP_SELECTOR) {
    throw new Error("Knowledge graph returned an unauthorized swap selector");
  }
  const addressFields = [
    "router_address",
    "quoter_address",
    "pool_address",
    "token_in_address",
    "token_out_address",
  ];
  for (const field of addressFields) {
    if (!isAddress(route?.[field] || "")) {
      throw new Error(`Knowledge graph returned an invalid ${field}`);
    }
  }

  const fee = Number(route.pool_fee);
  const inputDecimals = Number(route.token_in_decimals);
  const outputDecimals = Number(route.token_out_decimals);
  if (!Number.isInteger(fee) || fee <= 0 || fee > 1_000_000) {
    throw new Error("Knowledge graph returned an invalid Uniswap pool fee");
  }
  if (!Number.isInteger(inputDecimals) || inputDecimals < 0 || inputDecimals > 255) {
    throw new Error("Knowledge graph returned invalid input-token decimals");
  }
  if (!Number.isInteger(outputDecimals) || outputDecimals < 0 || outputDecimals > 255) {
    throw new Error("Knowledge graph returned invalid output-token decimals");
  }

  return {
    ...route,
    pool_fee: fee,
    token_in_decimals: inputDecimals,
    token_out_decimals: outputDecimals,
  };
}

function decodeRevertString(message) {
  const match = String(message || "").match(/0x08c379a0[0-9a-fA-F]+/);
  if (!match) return null;
  try {
    const encoded = match[0].slice(10);
    const length = Number.parseInt(encoded.slice(64, 128), 16);
    const value = encoded.slice(128, 128 + length * 2);
    return Buffer.from(value, "hex").toString("utf8");
  } catch {
    return null;
  }
}

function describeError(err) {
  const candidates = [err?.details, err?.shortMessage, err?.message, String(err)];
  for (const candidate of candidates) {
    const decoded = decodeRevertString(candidate);
    if (decoded) return `UserOperation simulation reverted: ${decoded}`;
  }
  const useful = candidates.find(
    (candidate) => candidate && candidate !== "HTTP request failed.",
  );
  if (!useful) return "Unknown wallet execution error";
  return String(useful).split("\nRequest body:")[0].slice(0, 800);
}

async function buildSwapPlan(args) {
  await loadZeroDevDependencies();

  const amountText = String(args.amount ?? "").trim();
  if (!/^\d+(\.\d+)?$/.test(amountText)) {
    throw new Error("Swap amount must be a positive decimal number");
  }

  const slippageBps = Number(args.slippage_bps ?? 100);
  if (!Number.isInteger(slippageBps) || slippageBps < 1 || slippageBps > 500) {
    throw new Error("Slippage must be between 1 and 500 basis points");
  }

  if (!Array.isArray(args.routes) || args.routes.length === 0) {
    throw new Error("Knowledge graph returned no executable Uniswap routes");
  }
  const routes = args.routes.map(validateRoute);
  const first = routes[0];
  for (const route of routes) {
    if (
      route.router_address.toLowerCase() !== first.router_address.toLowerCase() ||
      route.token_in_address.toLowerCase() !== first.token_in_address.toLowerCase() ||
      route.token_out_address.toLowerCase() !== first.token_out_address.toLowerCase()
    ) {
      throw new Error("Knowledge graph returned inconsistent swap routes");
    }
  }

  for (const destination of [first.router_address, first.token_in_address]) {
    const session = checkSession(destination, 0);
    if (!session.ok) {
      throw new Error(session.reason);
    }
  }

  let amountIn;
  try {
    amountIn = globalThis.__parseUnits(amountText, first.token_in_decimals);
  } catch {
    throw new Error(
      `${first.token_in_symbol} supports at most ${first.token_in_decimals} decimal places`,
    );
  }
  if (amountIn <= 0n) {
    throw new Error("Swap amount must be greater than zero");
  }

  const { account, kernelClient, publicClient } = await buildClients();
  const quotedRoutes = [];
  const quoteErrors = [];
  for (const route of routes) {
    try {
      const quote = await publicClient.simulateContract({
        account: account.address,
        address: route.quoter_address,
        abi: QUOTER_V2_ABI,
        functionName: "quoteExactInputSingle",
        args: [
          {
            tokenIn: route.token_in_address,
            tokenOut: route.token_out_address,
            amountIn,
            fee: route.pool_fee,
            sqrtPriceLimitX96: 0n,
          },
        ],
      });
      const amountOut = Array.isArray(quote.result)
        ? quote.result[0]
        : quote.result?.amountOut ?? quote.result;
      if (typeof amountOut === "bigint" && amountOut > 0n) {
        quotedRoutes.push({ route, amountOut });
      }
    } catch (err) {
      quoteErrors.push(`${route.pool_address}: ${describeError(err)}`);
    }
  }
  if (quotedRoutes.length === 0) {
    const detail = quoteErrors.length ? ` ${quoteErrors[0]}` : "";
    throw new Error(
      `No graph-verified Uniswap pool could quote this swap. The Sepolia pools may have no usable liquidity.${detail}`,
    );
  }

  quotedRoutes.sort((a, b) => (a.amountOut > b.amountOut ? -1 : a.amountOut < b.amountOut ? 1 : 0));
  const best = quotedRoutes[0];
  const amountOutMinimum = (best.amountOut * BigInt(10_000 - slippageBps)) / 10_000n;
  if (amountOutMinimum <= 0n) {
    throw new Error("Quoted output is too small after slippage protection");
  }

  const balance = await publicClient.readContract({
    address: first.token_in_address,
    abi: ERC20_ABI,
    functionName: "balanceOf",
    args: [account.address],
  });
  if (balance < amountIn) {
    throw new Error(
      `Smart wallet ${account.address} has ${globalThis.__formatUnits(balance, first.token_in_decimals)} ${first.token_in_symbol}; ` +
        `${amountText} ${first.token_in_symbol} is required. Fund the smart wallet, not only the connected MetaMask account.`,
    );
  }

  const allowance = await publicClient.readContract({
    address: first.token_in_address,
    abi: ERC20_ABI,
    functionName: "allowance",
    args: [account.address, first.router_address],
  });
  const calls = [];
  if (allowance < amountIn) {
    if (allowance > 0n) {
      calls.push({
        to: first.token_in_address,
        value: 0n,
        data: globalThis.__encodeFunctionData({
          abi: ERC20_ABI,
          functionName: "approve",
          args: [first.router_address, 0n],
        }),
      });
    }
    calls.push({
      to: first.token_in_address,
      value: 0n,
      data: globalThis.__encodeFunctionData({
        abi: ERC20_ABI,
        functionName: "approve",
        args: [first.router_address, amountIn],
      }),
    });
  }

  calls.push({
    to: first.router_address,
    value: 0n,
    data: globalThis.__encodeFunctionData({
      abi: SWAP_ROUTER_02_ABI,
      functionName: "exactInputSingle",
      args: [
        {
          tokenIn: first.token_in_address,
          tokenOut: first.token_out_address,
          fee: best.route.pool_fee,
          recipient: account.address,
          amountIn,
          amountOutMinimum,
          sqrtPriceLimitX96: 0n,
        },
      ],
    }),
  });

  return {
    account,
    kernelClient,
    calls,
    summary: {
      smart_wallet: account.address,
      router: first.router_address,
      quoter: best.route.quoter_address,
      pool: best.route.pool_address,
      pool_fee: best.route.pool_fee,
      token_in: first.token_in_symbol,
      token_out: first.token_out_symbol,
      amount_in: amountText,
      quoted_amount_out: globalThis.__formatUnits(best.amountOut, first.token_out_decimals),
      minimum_amount_out: globalThis.__formatUnits(amountOutMinimum, first.token_out_decimals),
      slippage_bps: slippageBps,
      approval_required: allowance < amountIn,
      calls: calls.length,
    },
  };
}

async function prepareSwap(args) {
  const start = Date.now();
  try {
    const plan = await buildSwapPlan(args);
    respond({
      success: true,
      prepared: true,
      executed: false,
      ...plan.summary,
      chain: "ethereum-sepolia",
      chain_id: 11155111,
      latency_ms: Date.now() - start,
    });
  } catch (err) {
    respond({
      success: false,
      prepared: false,
      executed: false,
      blocked_by: "swap preflight",
      reason: describeError(err),
      latency_ms: Date.now() - start,
    });
  }
}

async function sendSwap(args) {
  const start = Date.now();
  try {
    const plan = await buildSwapPlan(args);
    const txHash = await plan.kernelClient.sendTransaction({ calls: plan.calls });
    respond({
      success: true,
      executed: true,
      tx_hash: txHash,
      ...plan.summary,
      verified_address: plan.summary.router,
      action: "swap",
      chain: "ethereum-sepolia",
      chain_id: 11155111,
      explorer: `https://sepolia.etherscan.io/tx/${txHash}`,
      latency_ms: Date.now() - start,
    });
  } catch (err) {
    respond({
      success: false,
      executed: false,
      blocked_by: "swap execution",
      reason: describeError(err),
      latency_ms: Date.now() - start,
    });
  }
}

// ── Entry point ───────────────────────────────────────────

async function main() {
  const [, , command, rawArgs] = process.argv;

  let args = {};

  try {
    args = rawArgs ? JSON.parse(rawArgs) : {};
  } catch {
    fail("Invalid JSON args");
  }

  try {
    switch (command) {
      case "create_wallet":
        await createWallet();
        break;

      case "add_whitelist":
        addToWhitelist(args);
        break;

      case "check_session":
        checkSessionCommand(args);
        break;

      case "prepare_swap":
        await prepareSwap(args);
        break;

      case "send_swap":
        await sendSwap(args);
        break;

      case "send_userop":
        respond({
          success: false,
          executed: false,
          error: "send_userop was disabled because empty-calldata ETH transfers are not protocol swaps; use send_swap",
        });
        break;

      default:
        respond(
          {
            success: false,
            error: `Unknown command: ${command}`,
          },
          1,
        );
    }
  } catch (err) {
    respond(
      {
        success: false,
        error: err?.message || String(err),
      },
      1,
    );
  }
}

main();
