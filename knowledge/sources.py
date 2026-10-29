"""Download pinned official inputs and verify an offline, non-executable bundle."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.request import Request, urlopen
import zipfile


DATA = Path(__file__).parent / "data"
MANIFEST = DATA / "sources.lock.json"
BUNDLE = DATA / "sources.zip"
REPO = "aave-dao/aave-address-book"
AAVE_ABIS = (
    "IPool", "IPoolConfigurator", "IPoolAddressesProvider", "IACLManager",
    "IAaveOracle", "IAToken", "IRewardsController", "IWrappedTokenGatewayV3",
    "IUiPoolDataProvider", "IDefaultInterestRateStrategy", "IStataTokenV2",
    "IStataTokenFactory", "IUmbrella", "IUmbrellaStakeToken",
    "IUmbrellaRewardsController",
)
AAVE_BOOKS = ("AaveV3Ethereum", "AaveV3Sepolia", "UmbrellaEthereum")
PACKAGES = {
    "@uniswap/v3-core": ("1.0.1", {
        "IUniswapV3Factory": "artifacts/contracts/interfaces/IUniswapV3Factory.sol/IUniswapV3Factory.json",
        "IUniswapV3Pool": "artifacts/contracts/interfaces/IUniswapV3Pool.sol/IUniswapV3Pool.json",
    }),
    "@uniswap/v3-periphery": ("1.4.4", {
        "ISwapRouter": "artifacts/contracts/interfaces/ISwapRouter.sol/ISwapRouter.json",
        "IQuoterV2": "artifacts/contracts/interfaces/IQuoterV2.sol/IQuoterV2.json",
        "INonfungiblePositionManager": "artifacts/contracts/interfaces/INonfungiblePositionManager.sol/INonfungiblePositionManager.json",
        "IV3Migrator": "artifacts/contracts/interfaces/IV3Migrator.sol/IV3Migrator.json",
        "ITickLens": "artifacts/contracts/interfaces/ITickLens.sol/ITickLens.json",
    }),
    "@uniswap/swap-router-contracts": ("1.3.1", {
        "SwapRouter02": "artifacts/contracts/SwapRouter02.sol/SwapRouter02.json",
    }),
}


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def download(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "defi-verification-knowledge/1.0"})
    with urlopen(req, timeout=60) as response:
        data = response.read(40 * 1024 * 1024 + 1)
    if len(data) > 40 * 1024 * 1024:
        raise ValueError("Source exceeds 40 MiB limit")
    return data


def refresh_sources() -> dict:
    """Explicit refresh only; normal builds replay the checked-in bundle."""
    commit = json.loads(download(f"https://api.github.com/repos/{REPO}/commits/main"))["sha"]
    captured_at = now()
    entries, payloads = [], {}

    def add(key, payload, url, kind, **metadata):
        entries.append({"key": key, "url": url, "kind": kind,
                        "sha256": digest(payload), "bytes": len(payload),
                        "retrieved_at": captured_at, **metadata})
        payloads[key] = payload

    paths = [(f"aave/book/{name}", f"src/{name}.sol", "address_book") for name in AAVE_BOOKS]
    paths += [(f"aave/abi/{name}", f"src/ts/abis/{name}.ts", "typescript_abi") for name in AAVE_ABIS]
    paths += [("aave/package", "package.json", "package_metadata"), ("aave/license", "LICENSE", "license")]

    def fetch_path(spec):
        key, path, kind = spec
        url = f"https://raw.githubusercontent.com/{REPO}/{commit}/{path}"
        return key, download(url), url, kind

    with ThreadPoolExecutor(max_workers=6) as pool:
        for key, payload, url, kind in pool.map(fetch_path, paths):
            add(key, payload, url, kind, revision=commit, repository=f"https://github.com/{REPO}")
    inventory_url = f"https://api.github.com/repos/{REPO}/contents/src?ref={commit}"
    add("aave/inventory", download(inventory_url), inventory_url, "registry_inventory", revision=commit)
    feed_url = "https://developers.uniswap.org/deployments.json"
    feed = download(feed_url)
    add("uniswap/deployments", feed, feed_url, "deployment_registry",
        revision=json.loads(feed).get("source", {}).get("commit", "content-pinned"))

    for package, (version, artifacts) in PACKAGES.items():
        metadata_url = f"https://registry.npmjs.org/{package}/{version}"
        metadata_bytes = download(metadata_url)
        metadata = json.loads(metadata_bytes)
        dist = metadata["dist"]
        tarball = download(dist["tarball"])
        algorithm, expected = dist["integrity"].split("-", 1)
        if algorithm != "sha512" or base64.b64encode(hashlib.sha512(tarball).digest()).decode() != expected:
            raise ValueError(f"Package integrity mismatch: {package}@{version}")
        add(f"npm/{package}/metadata", metadata_bytes, metadata_url, "package_metadata", revision=version)
        # Read selected members in memory. Never extract or execute package code.
        with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
            for name, path in artifacts.items():
                member = archive.getmember(f"package/{path}")
                if not member.isfile() or member.size > 4 * 1024 * 1024:
                    raise ValueError(f"Invalid artifact member: {path}")
                payload = archive.extractfile(member).read()
                add(f"uniswap/abi/{name}", payload, f"https://unpkg.com/{package}@{version}/{path}",
                    "json_artifact", revision=version, package=package,
                    package_integrity=dist["integrity"], package_member=path,
                    package_tarball_sha256=digest(tarball))
            licenses = [m for m in archive.getmembers() if m.name.lower() in {"package/license", "package/license.md", "package/license.txt"}]
            for member in licenses:
                add(f"npm/{package}/license", archive.extractfile(member).read(),
                    f"https://unpkg.com/{package}@{version}/{member.name[8:]}", "license", revision=version)

    entries.sort(key=lambda item: item["key"])
    manifest = {"format_version": 1, "created_at": captured_at, "sources": entries}
    # Write both complete files only after every download and integrity check succeeds.
    DATA.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BUNDLE.with_suffix(".zip.tmp"), "w", zipfile.ZIP_DEFLATED) as archive:
        for key, value in sorted(payloads.items()):
            archive.writestr(key, value)
    MANIFEST.with_suffix(".json.tmp").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    BUNDLE.with_suffix(".zip.tmp").replace(BUNDLE)
    MANIFEST.with_suffix(".json.tmp").replace(MANIFEST)
    return manifest


class SourceBundle:
    def __init__(self, manifest: Path = MANIFEST, bundle: Path = BUNDLE):
        document = json.loads(manifest.read_text(encoding="utf-8"))
        if document.get("format_version") != 1:
            raise ValueError("Unknown source bundle version")
        self.entries = {entry["key"]: entry for entry in document["sources"]}
        if len(self.entries) != len(document["sources"]):
            raise ValueError("Duplicate source keys")
        self.payloads = {}
        with zipfile.ZipFile(bundle) as archive:
            if sorted(archive.namelist()) != sorted(self.entries):
                raise ValueError("Source bundle members differ from the manifest")
            for key, entry in self.entries.items():
                member = archive.getinfo(key)
                if member.file_size != entry["bytes"] or member.file_size > 4 * 1024 * 1024:
                    raise ValueError(f"Invalid source size: {key}")
                payload = archive.read(key)
                if digest(payload) != entry["sha256"]:
                    raise ValueError(f"Source hash mismatch: {key}")
                self.payloads[key] = payload

    def text(self, key: str) -> str:
        return self.payloads[key].decode("utf-8")

    def json(self, key: str):
        return json.loads(self.text(key))
