/**
 * wallet.mjs — ZeroDev ERC-4337 wallet for Avalanche Fuji
 * Called from Python as a subprocess.
 *
 * OPTIMIZATION: Lazy-loads heavy dependencies (viem, ZeroDev) only for blockchain commands.
 * File I/O commands (add_whitelist, check_session) start instantly.
 *
 * Usage:
 *   node wallet.mjs create_wallet
 *   node wallet.mjs add_whitelist '{"address":"0x..."}'
 *   node wallet.mjs check_session '{"to":"0x...","value_eth":0.001}'
 *   node wallet.mjs send_userop '{"to":"0x...","value_eth":0.001,"action":"swap"}'
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

const ZERODEV_RPC =
  process.env.AVALANCHE_FUJI_RPC ||
  "https://rpc.zerodev.app/api/v3/fb533751-5238-4cfd-859e-91b22b89aa53/chain/43113";

const PRIVATE_KEY = process.env.PRIVATE_KEY;

const SESSION_LIMIT_ETH = 0.005;
const SESSION_DURATION_MS = 24 * 60 * 60 * 1000;

const WHITELIST_FILE = resolve(__dirname, "session-whitelist.json");

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
  } = await import("viem");
  const { privateKeyToAccount } = await import("viem/accounts");
  const { avalancheFuji } = await import("viem/chains");

  ENTRY_POINT = getEntryPoint("0.7");
  KERNEL_VER = KERNEL_V3_1;
  CHAIN = avalancheFuji;

  // Store in global scope for buildClients to use
  globalThis.__createKernelAccount = createKernelAccount;
  globalThis.__createKernelAccountClient = _createKernelAccountClient;
  globalThis.__createZeroDevPaymasterClient = createZeroDevPaymasterClient;
  globalThis.__http = http;
  globalThis.__createPublicClient = _createPublicClient;
  globalThis.__parseEther = _parseEther;
  globalThis.__signerToEcdsaValidator = signerToEcdsaValidator;
  globalThis.__privateKeyToAccount = privateKeyToAccount;
  globalThis.__avalancheFuji = avalancheFuji;

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

  if (valueEth <= 0) {
    return {
      ok: false,
      reason: "Amount must be greater than 0",
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

  const signer = globalThis.__privateKeyToAccount(PRIVATE_KEY);

  const publicClient = globalThis.__createPublicClient({
    chain: CHAIN,
    transport: globalThis.__http(ZERODEV_RPC),
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
  };
}

// ── Commands ──────────────────────────────────────────────

async function createWallet() {
  await loadZeroDevDependencies(); // Ensure deps are loaded

  const { account } = await buildClients();

  respond({
    success: true,
    smart_wallet_address: account.address,
    chain: "avalanche-fuji",
    chain_id: 43113,
    type: "ERC-4337 Kernel Account",
  });
}

async function sendUserOp(args) {
  await loadZeroDevDependencies(); // Ensure deps are loaded

  const start = Date.now();

  const to = args.to;
  const valueEth = Number(args.value_eth);
  const action = args.action || "unknown";

  const session = checkSession(to, valueEth);

  if (!session.ok) {
    respond({
      success: false,
      executed: false,
      blocked_by: "ERC-4337 session key",
      reason: session.reason,
      latency_ms: Date.now() - start,
    });
  }

  try {
    const { kernelClient, account } = await buildClients();

    const txHash = await kernelClient.sendTransaction({
      to,
      value: globalThis.__parseEther(String(valueEth)),
      data: "0x",
    });

    respond({
      success: true,
      executed: true,
      tx_hash: txHash,
      smart_wallet: account.address,
      verified_address: to,
      amount_eth: valueEth,
      action,
      chain: "avalanche-fuji",
      explorer: `https://testnet.snowtrace.io/tx/${txHash}`,
      latency_ms: Date.now() - start,
    });
  } catch (err) {
    respond({
      success: false,
      executed: false,
      blocked_by: "ERC-4337 bundler",
      reason: err?.message || String(err),
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

      case "send_userop":
        await sendUserOp(args);
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
