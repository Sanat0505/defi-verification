import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import solc from "solc";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vendor = path.join(root, "test/vendor");
const importing = process.argv.includes("--import-pinned-kernel");
const kernel = path.resolve(root, "../../.cache/restricted-auth/kernel");
const hashes = {};

function read(name) {
  let file;
  if (name.startsWith("kernel/")) file = importing ? path.join(kernel, name.slice(7)) : path.join(vendor, name);
  else if (name.startsWith("solady/")) file = importing ? path.join(kernel, "lib/solady/src", name.slice(7)) : path.join(vendor, name);
  else if (name.startsWith("ExcessivelySafeCall/")) file = importing ? path.join(kernel, "lib/ExcessivelySafeCall/src", name.slice(20)) : path.join(vendor, name);
  else if (name.startsWith("@")) file = path.join(root, "node_modules", name);
  else file = path.join(root, name);
  const contents = fs.readFileSync(file, "utf8");
  if (name.startsWith("kernel/") || name.startsWith("solady/") || name.startsWith("ExcessivelySafeCall/")) {
    if (importing) {
      const dest = path.join(vendor, name);
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.writeFileSync(dest, contents);
    }
    hashes[name] = createHash("sha256").update(contents).digest("hex");
  }
  return { contents };
}

export function compile() {
  const cacheFile = path.join(root, ".cache/compiled-tests.json");
  let fingerprint;
  if (!importing) {
    const manifest = JSON.parse(fs.readFileSync(path.join(vendor, "manifest.json")));
    for (const [name, expected] of Object.entries(manifest.sha256)) {
      const actual = createHash("sha256").update(fs.readFileSync(path.join(vendor, name))).digest("hex");
      if (actual !== expected) throw new Error(`Modified pinned source: ${name}`);
    }
    fingerprint = createHash("sha256").update([
      "contracts/GraphBoundValidator.sol", "test/RecordingTarget.sol", "test/vendor/manifest.json", "package-lock.json", "test/compile.mjs",
    ].map(n => fs.readFileSync(path.join(root, n), "utf8")).join("\n")).digest("hex");
    if (fs.existsSync(cacheFile)) {
      const cached = JSON.parse(fs.readFileSync(cacheFile));
      if (cached.fingerprint === fingerprint) return cached.artifacts;
    }
  }
  const roots = ["contracts/GraphBoundValidator.sol", "test/RecordingTarget.sol",
    "kernel/src/Kernel.sol", "kernel/src/factory/KernelFactory.sol", "kernel/src/validator/ECDSAValidator.sol",
    "@account-abstraction/contracts/core/EntryPoint.sol"];
  const input = { language: "Solidity", sources: Object.fromEntries(roots.map(n => [n, { content: read(n).contents }])),
    settings: { optimizer: { enabled: true, runs: 200 }, viaIR: true, evmVersion: "shanghai",
      outputSelection: { "*": { "*": ["abi", "evm.bytecode.object", "evm.deployedBytecode.object"] } } } };
  const result = JSON.parse(solc.compile(JSON.stringify(input), { import: name => {
    try { return read(name); } catch { return { error: `Missing pinned dependency: ${name}` }; }
  } }));
  const errors = result.errors?.filter(e => e.severity === "error") || [];
  if (errors.length) throw new Error(errors.map(e => e.formattedMessage).join("\n"));
  if (!importing) {
    const expected = JSON.parse(fs.readFileSync(path.join(vendor, "manifest.json")));
    for (const [name, hash] of Object.entries(hashes)) {
      if (expected.sha256[name] !== hash) throw new Error(`Modified pinned source: ${name}`);
    }
  } else {
    fs.writeFileSync(path.join(vendor, "manifest.json"), JSON.stringify({
      kernelCommit: "03f7f5cf5871cda0070e4223f196f5b577f6cde2",
      soladyCommit: "9deb9ed36a27261a8745db5b7cd7f4cdc3b1cd4e", sha256: hashes,
      excessivelySafeCallCommit: "81cd99ce3e69117d665d7601c330ea03b97acce0",
    }, null, 2) + "\n");
  }
  const artifacts = Object.assign({}, ...Object.values(result.contracts));
  if (!importing) {
    fs.mkdirSync(path.dirname(cacheFile), { recursive: true });
    fs.writeFileSync(cacheFile, JSON.stringify({ fingerprint, artifacts }));
  }
  return artifacts;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const artifacts = compile();
  fs.mkdirSync(path.join(root, "artifacts"), { recursive: true });
  fs.writeFileSync(path.join(root, "artifacts/GraphBoundValidator.json"),
    JSON.stringify({ compiler: solc.version(), optimizerRuns: 200, viaIR: true, evmVersion: "shanghai",
      ...artifacts.GraphBoundValidator }, null, 2) + "\n");
  console.log("Compiled GraphBoundValidator and pinned Kernel/EntryPoint contracts");
}
