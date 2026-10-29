"""Optional read-only Ethereum observations, anchored to a block and chain ID."""

from __future__ import annotations

from itertools import combinations
import json
import os
from urllib.request import Request, urlopen

from eth_hash.auto import keccak

from knowledge.model import Graph, interface_key
from knowledge.sources import canonical, digest

RPC_ENVS = {1: "MAINNET_RPC", 11155111: "SEPOLIA_RPC"}
IMPLEMENTATION_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"


class RpcError(RuntimeError):
    pass


class ReadOnlyRpc:
    ALLOWED = {"eth_chainId", "eth_getBlockByNumber", "eth_getCode", "eth_getStorageAt", "eth_call"}

    def __init__(self, url):
        self.url = url
        self.sequence = 0

    def call(self, method, params):
        if method not in self.ALLOWED:
            raise ValueError("Only read-only RPC methods are permitted")
        self.sequence += 1
        req = Request(self.url, data=canonical({"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params}).encode(), headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=20) as response:
                value = json.loads(response.read(4 * 1024 * 1024))
            if "error" in value:
                raise RpcError(f"{method}: RPC error code {value['error'].get('code', 'unknown')}")
            return value["result"]
        except RpcError:
            raise
        except Exception as exc:
            # RPC URLs and provider messages may contain credentials.
            raise RpcError(f"{method}: {type(exc).__name__}") from None


def calldata(signature: str, *words: str) -> str:
    return "0x" + keccak(signature.encode()).hex()[:8] + "".join(word.removeprefix("0x").zfill(64) for word in words)


def words(raw: str) -> list[int]:
    if not isinstance(raw, str) or not raw.startswith("0x") or (len(raw) - 2) % 64:
        raise ValueError("Invalid ABI return data")
    return [int(raw[i:i + 64], 16) for i in range(2, len(raw), 64)]


def address_result(raw: str) -> str:
    values = words(raw)
    if len(values) != 1 or values[0] >= 2 ** 160:
        raise ValueError("Invalid address return data")
    return f"0x{values[0]:040x}"


def observe_chain(graph: Graph, chain_id: int, rpc, pool_limit=80):
    if int(rpc.call("eth_chainId", []), 16) != chain_id:
        raise ValueError(f"RPC chain mismatch for chain {chain_id}; refusing observations")
    block = rpc.call("eth_getBlockByNumber", ["latest", False])
    block_tag, block_hash = block["number"], block["hash"]
    if not isinstance(block_hash, str) or len(block_hash) != 66:
        raise ValueError("Missing RPC block hash")
    source = f"rpc:{chain_id}:{block_hash}"
    explorer = "https://etherscan.io" if chain_id == 1 else "https://sepolia.etherscan.io"
    graph.node("Source", "source:" + source, source_key=source, kind="rpc_observation",
               url=f"{explorer}/block/{int(block_tag, 16)}", rpc_configuration=RPC_ENVS[chain_id],
               chain_id=chain_id, block_number=int(block_tag, 16), block_hash=block_hash,
               block_timestamp=int(block["timestamp"], 16), consistency="block hash rechecked after reads")
    errors = []

    def read(method, params, context):
        try:
            return rpc.call(method, params)
        except RpcError as exc:
            errors.append({"context": context, "error": str(exc)})
            return None

    def observation(target, kind, **properties):
        key = f"observation:{target}:{kind}"
        graph.node("Observation", key, source, kind=kind, chain_id=chain_id,
                   block_number=int(block_tag, 16), block_hash=block_hash,
                   evidence_sha256=digest(canonical(properties).encode()), **properties)
        graph.edge(target, "OBSERVED", key)

    contracts = [n for n in graph.nodes.values() if n["label"] == "Contract" and n["properties"]["chain_id"] == chain_id]
    important = {"POOL", "POOL_CONFIGURATOR", "POOL_ADDRESSES_PROVIDER", "WETH_GATEWAY", "ORACLE", "UMBRELLA", "UMBRELLA_REWARDS_CONTROLLER", "SwapRouter02", "SwapRouter", "UniswapV3Factory", "NonfungiblePositionManager", "QuoterV2"}
    selected = [n for n in contracts if n["properties"]["role"] in important or n["properties"]["role"].startswith("STK_")]
    for contract in selected:
        p = contract["properties"]
        code = read("eth_getCode", [p["address"], block_tag], contract["key"])
        if code is not None:
            present = bool(code.removeprefix("0x"))
            observation(contract["key"], "code", present=present, code_keccak256="0x" + keccak(bytes.fromhex(code[2:])).hex())
            p["code_status"] = "present_at_observed_block" if present else "absent_at_observed_block"
            if not present:
                graph.gap(contract["key"], "no_code", "Registry address has no code at the observed block.", source)
        slot = read("eth_getStorageAt", [p["address"], IMPLEMENTATION_SLOT, block_tag], contract["key"])
        if slot is not None:
            implementation = address_result(slot)
            observation(contract["key"], "eip1967_implementation", address=implementation,
                        interpretation="zero means this slot is unset; it does not prove a contract is not a proxy")
            reported = [e for e in graph.edges.values() if e["start"] == contract["key"] and e["type"] == "IMPLEMENTATION_REPORTED"]
            for edge in reported:
                expected = graph.nodes[edge["end"]]["properties"]["address"]
                if implementation != expected:
                    graph.gap(contract["key"], "implementation_mismatch", "Reported implementation differs from the EIP-1967 slot at the observed block; review deployment revision.", source)
                else:
                    edge["properties"]["onchain_verified"] = True
                    edge["properties"]["block_hash"] = block_hash
    graph.gap(f"chain:{chain_id}", "code_observation_scope", f"Code and proxy slots checked for {len(selected)} of {len(contracts)} registered roles. ABI/bytecode equivalence is not established.", source)

    pool = next((n for n in contracts if n["properties"]["role"] == "POOL"), None)
    reserves = [n for n in graph.nodes.values() if n["label"] == "Reserve" and n["properties"]["chain_id"] == chain_id]
    if pool:
        for reserve in reserves:
            raw = read("eth_call", [{"to": pool["properties"]["address"], "data": calldata("getConfiguration(address)", reserve["properties"]["underlying_address"])}, block_tag], reserve["key"])
            if raw is None:
                continue
            decoded = words(raw)
            if len(decoded) != 1:
                errors.append({"context": reserve["key"], "error": "invalid reserve configuration response"})
                continue
            value = decoded[0]
            observation(reserve["key"], "reserve_configuration", raw=raw,
                        ltv_bps=value & 65535, liquidation_threshold_bps=(value >> 16) & 65535,
                        active=bool(value & (1 << 56)), frozen=bool(value & (1 << 57)),
                        borrowing_enabled=bool(value & (1 << 58)), paused=bool(value & (1 << 60)))
            reserve["properties"]["configuration_status"] = "observed_at_block"

    for vault in [n for n in graph.nodes.values() if n["label"] == "StakingVault" and n["properties"]["chain_id"] == chain_id]:
        raw = read("eth_call", [{"to": vault["properties"]["address"], "data": calldata("asset()")}, block_tag], vault["key"])
        if raw:
            asset = address_result(raw)
            token = graph.node("Token", vault["key"] + ":asset", source, address=asset, chain_id=chain_id, role="umbrella_underlying")
            graph.edge(vault["key"], "UNDERLYING", token)
            vault["properties"]["asset_status"] = "observed_at_block"
        for method in ("getCooldown()", "getUnstakeWindow()"):
            raw = read("eth_call", [{"to": vault["properties"]["address"], "data": calldata(method)}, block_tag], vault["key"])
            if raw and len(words(raw)) == 1:
                observation(vault["key"], method, seconds=str(words(raw)[0]))

    factory = next((n for n in contracts if n["properties"]["role"] == "UniswapV3Factory"), None)
    router = next((n for n in contracts if n["properties"]["role"] == "SwapRouter02"), None)
    tokens = {n["properties"]["underlying_address"]: n["properties"]["symbol"] for n in reserves if n["properties"]["symbol"] in {"USDC", "USDT", "DAI", "WETH"}}
    if router:
        raw = read("eth_call", [{"to": router["properties"]["address"], "data": calldata("WETH9()")}, block_tag], router["key"])
        if raw:
            tokens[address_result(raw)] = "WETH (router)"
    attempted, found = 0, 0
    if factory:
        for token0, token1 in combinations(sorted(tokens), 2):
            for fee in (100, 500, 3000, 10000):
                if attempted >= pool_limit:
                    break
                attempted += 1
                raw = read("eth_call", [{"to": factory["properties"]["address"], "data": calldata("getPool(address,address,uint24)", token0, token1, hex(fee))}, block_tag], f"pool:{token0}:{token1}:{fee}")
                if raw is None:
                    continue
                address = address_result(raw)
                if int(address, 16) == 0:
                    continue
                found += 1
                deployment = f"deployment:uniswap-v3:{chain_id}"
                key = graph.node("Pool", f"{deployment}:pool:{address}", source, address=address,
                                 chain_id=chain_id, fee=fee, token0=token0, token1=token1,
                                 factory=factory["properties"]["address"], discovery="factory_getPool_at_block")
                graph.edge(deployment, "HAS_POOL", key)
                graph.edge(key, "CANDIDATE_INTERFACE", interface_key("IUniswapV3Pool"), verified=False)
                for role, token_address in (("TOKEN0", token0), ("TOKEN1", token1)):
                    token_key = f"{key}:{role}"
                    graph.node("Token", token_key, source, address=token_address, symbol=tokens[token_address], chain_id=chain_id, role="pool_asset")
                    graph.edge(key, role, token_key)
                for method in ("slot0()", "liquidity()", "tickSpacing()"):
                    raw = read("eth_call", [{"to": address, "data": calldata(method)}, block_tag], key)
                    if raw:
                        observation(key, method, raw=raw)
        graph.gap(f"deployment:uniswap-v3:{chain_id}", "pool_discovery_scope", f"Queried {attempted} token-pair/fee combinations from USDC, USDT, DAI and WETH registry assets plus router WETH; found {found} pools. This is not an exhaustive factory event scan.", source)
    if errors:
        graph.gap(f"chain:{chain_id}", "rpc_read_failures", canonical(errors), source)
    final_block = rpc.call("eth_getBlockByNumber", [block_tag, False])
    if not final_block or final_block["hash"] != block_hash:
        raise ValueError(f"Block changed during chain {chain_id} observations; refusing publication")


def add_observations(graph: Graph, *, enabled=False, pool_limit=80, rpc_factory=ReadOnlyRpc):
    if not 0 <= pool_limit <= 500:
        raise ValueError("Pool lookup limit must be between 0 and 500")
    for chain_id, env in RPC_ENVS.items():
        if not enabled or not os.getenv(env):
            graph.gap(f"chain:{chain_id}", "rpc_not_observed", f"{env} is not configured or --rpc was not requested; registry facts have no current chain-state confirmation.")
            continue
        observe_chain(graph, chain_id, rpc_factory(os.environ[env]), pool_limit=pool_limit)
    return graph
