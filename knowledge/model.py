"""Deterministic graph construction from integrity-checked protocol sources."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
import re

from eth_hash.auto import keccak
import json5

from db.loaders.aave_loader import CORE_ADDRESS_PATTERN, DECIMALS_PATTERN, _parse_address_book
from db.loaders.common import normalize_address
from knowledge.catalog import (
    AAVE_INTERFACES, ADAPTERS, MODULES, OPERATIONS, UNISWAP_INTERFACES,
    module_for, permission,
)
from knowledge.sources import SourceBundle, canonical, digest


SCHEMA_VERSION = "expanded-knowledge-1"
CHAINS = {1: "Ethereum Mainnet", 11155111: "Ethereum Sepolia"}
LABELS = {"Source", "Module", "Interface", "Function", "Parameter", "Event", "Error",
          "Operation", "Chain", "Deployment", "Contract", "Reserve", "Token",
          "StakingVault", "CoverageGap", "Observation", "Pool"}
RELATIONS = {"HAS_INTERFACE", "DECLARES", "HAS_PARAMETER", "HAS_COMPONENT",
             "HAS_OPERATION", "USES_FUNCTION", "EVIDENCED_BY", "HAS_DEPLOYMENT",
             "ON_CHAIN", "REGISTERS", "CANDIDATE_INTERFACE", "IMPLEMENTATION_REPORTED",
             "HAS_RESERVE", "UNDERLYING", "A_TOKEN", "V_TOKEN", "S_TOKEN",
             "STATIC_A_TOKEN", "STATA_TOKEN", "ORACLE", "INTEREST_RATE_STRATEGY",
             "HAS_STAKING_VAULT", "HAS_GAP", "OBSERVED", "HAS_POOL", "TOKEN0", "TOKEN1"}


def abi_type(parameter: dict) -> str:
    value = parameter["type"]
    if value.startswith("tuple"):
        if "components" not in parameter:
            raise ValueError("Tuple parameter is missing components")
        return "(" + ",".join(abi_type(p) for p in parameter["components"]) + ")" + value[5:]
    return value


def signature(entry: dict) -> str:
    return entry["name"] + "(" + ",".join(abi_type(p) for p in entry.get("inputs", [])) + ")"


def parse_abi(text: str, kind: str) -> list:
    if kind == "typescript_abi":
        match = re.fullmatch(r"\s*//[^\n]*\nexport const \w+\s*=\s*(\[.*\])\s+as const;?\s*", text, re.S)
        if not match:
            raise ValueError("Unexpected generated ABI format")
        abi = json5.loads(match.group(1), allow_duplicate_keys=False)
    else:
        abi = json.loads(text)["abi"]
    if not isinstance(abi, list) or not any(item.get("type") == "function" for item in abi):
        raise ValueError("Empty or invalid ABI")
    identities = [item["type"] + ":" + signature(item) for item in abi if item["type"] in {"function", "event", "error"}]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate ABI entries")
    return abi


@dataclass
class Graph:
    nodes: dict[str, dict] = field(default_factory=dict)
    edges: dict[str, dict] = field(default_factory=dict)

    def node(self, label: str, key: str, source: str | None = None, **properties) -> str:
        if label not in LABELS:
            raise ValueError(f"Unknown node type: {label}")
        value = {"label": label, "key": key, "properties": properties}
        if key in self.nodes and self.nodes[key] != value:
            raise ValueError(f"Conflicting fact: {key}")
        self.nodes[key] = value
        if source:
            self.edge(key, "EVIDENCED_BY", f"source:{source}")
        return key

    def edge(self, start: str, relation: str, end: str, **properties):
        if relation not in RELATIONS:
            raise ValueError(f"Unknown relation: {relation}")
        key = digest(canonical([start, relation, end]).encode())
        value = {"key": key, "start": start, "type": relation, "end": end, "properties": properties}
        if key in self.edges and self.edges[key] != value:
            raise ValueError("Conflicting relationship")
        self.edges[key] = value

    def gap(self, scope: str, code: str, detail: str, source: str | None = None):
        key = f"gap:{scope}:{code}"
        module = scope.split(":")[1] if ":" in scope and scope.split(":")[1] in MODULES else None
        self.node("CoverageGap", key, source, scope=scope, code=code, detail=detail,
                  status="open", implies_unsupported=False, module=module)
        if scope in self.nodes:
            self.edge(scope, "HAS_GAP", key)

    def validate(self):
        evidenced = {e["start"] for e in self.edges.values() if e["type"] == "EVIDENCED_BY"}
        for edge in self.edges.values():
            if edge["start"] not in self.nodes or edge["end"] not in self.nodes:
                raise ValueError(f"Dangling relationship: {edge}")
        for node in self.nodes.values():
            props = node["properties"]
            if props.get("execution_authorized") is not None:
                raise ValueError("Knowledge facts must not grant execution authority")
            if node["label"] in {"Function", "Interface", "Contract", "Reserve", "StakingVault"}:
                if node["key"] not in evidenced:
                    raise ValueError(f"Unsourced fact: {node['key']}")

    def document(self):
        self.validate()
        return {"schema_version": SCHEMA_VERSION,
                "nodes": sorted(self.nodes.values(), key=lambda n: n["key"]),
                "edges": sorted(self.edges.values(), key=lambda e: e["key"])}

    @property
    def snapshot_id(self) -> str:
        return digest(canonical(self.document()).encode())

    def report(self) -> dict:
        functions = [n["properties"] for n in self.nodes.values() if n["label"] == "Function"]
        return {"schema_version": SCHEMA_VERSION, "snapshot_id": self.snapshot_id,
                "counts": dict(sorted(Counter(n["label"] for n in self.nodes.values()).items())),
                "relationships": len(self.edges),
                "functions_by_module": dict(Counter(f["module"] for f in functions)),
                "function_permissions": dict(Counter(f["permission"] for f in functions)),
                "implemented_adapter_functions": sum(f["prototype_adapter_implemented"] for f in functions),
                "observed_blocks": [n["properties"] for n in self.nodes.values() if n["label"] == "Source" and n["properties"].get("kind") == "rpc_observation"],
                "wallet_eligibility": "not_evaluated",
                "gaps": [n["properties"] for n in sorted(self.nodes.values(), key=lambda n: n["key"]) if n["label"] == "CoverageGap"]}


def interface_key(name: str) -> str:
    return f"interface:{module_for(name)}:{name}"


def add_parameters(graph: Graph, parent: str, parameters: list, direction: str, source: str):
    for position, parameter in enumerate(parameters):
        key = f"{parent}:{direction}:{position}"
        graph.node("Parameter", key, source, name=parameter.get("name", ""), position=position,
                   direction=direction, abi_type=abi_type(parameter),
                   internal_type=parameter.get("internalType", ""), indexed=parameter.get("indexed", False))
        graph.edge(parent, "HAS_COMPONENT" if direction == "component" else "HAS_PARAMETER", key)
        add_parameters(graph, key, parameter.get("components", []), "component", source)


def add_interfaces(graph: Graph, bundle: SourceBundle):
    function_index = {}
    for source, metadata in bundle.entries.items():
        if metadata["kind"] not in {"typescript_abi", "json_artifact"}:
            continue
        name = source.rsplit("/", 1)[1]
        module = module_for(name)
        abi = parse_abi(bundle.text(source), metadata["kind"])
        key = graph.node("Interface", interface_key(name), source, name=name, module=module,
                         revision=metadata["revision"], abi_entries=len(abi),
                         function_count=sum(item["type"] == "function" for item in abi),
                         coverage="complete_for_pinned_artifact", deployment_compatibility="not_verified")
        graph.edge(f"module:{module}", "HAS_INTERFACE", key)
        for entry in abi:
            if entry["type"] not in {"function", "event", "error"}:
                continue
            sig = signature(entry)
            member_key = f"{key}:{entry['type']}:{sig}"
            properties = {"name": entry["name"], "signature": sig, "interface": name, "module": module,
                          "abi_json": canonical(entry)}
            hashed = keccak(sig.encode()).hex()
            if entry["type"] == "function":
                properties.update(selector="0x" + hashed[:8], state_mutability=entry["stateMutability"],
                                  permission=permission(name, entry),
                                  prototype_adapter_implemented=(name, sig) in ADAPTERS,
                                  adapter_scope="Sepolia; existing verifier and wallet policy required" if (name, sig) in ADAPTERS else "none",
                                  wallet_eligibility="not_evaluated")
                if name == "SwapRouter02" and entry["name"] in {"swapExactTokensForTokens", "swapTokensForExactTokens"}:
                    properties["protocol_scope"] = "Uniswap V2 routes in the shared SwapRouter02 interface"
                function_index.setdefault((name, entry["name"]), []).append(member_key)
            elif entry["type"] == "event":
                properties.update(topic0="0x" + hashed, anonymous=entry.get("anonymous", False))
            else:
                properties["selector"] = "0x" + hashed[:8]
            graph.node(entry["type"].title(), member_key, source, **properties)
            graph.edge(key, "DECLARES", member_key)
            add_parameters(graph, member_key, entry.get("inputs", []), "input", source)
            add_parameters(graph, member_key, entry.get("outputs", []), "output", source)

    for interface, action, methods, description, prerequisites in OPERATIONS:
        module = module_for(interface)
        functions = [key for method in methods for key in function_index.get((interface, method), [])]
        if not functions:
            raise ValueError(f"Operation has no ABI evidence: {interface}/{action}")
        source = ("uniswap" if module == "uniswap-v3" else "aave") + f"/abi/{interface}"
        key = graph.node("Operation", f"operation:{module}:{interface}:{action}", source,
                         action=action, module=module, interface=interface, description=description,
                         prerequisites=prerequisites, documentation=MODULES[module]["documentation"],
                         semantic_review="curated; prerequisites are not exhaustive or live",
                         prototype_support="some_variants" if any(graph.nodes[k]["properties"]["prototype_adapter_implemented"] for k in functions) else "knowledge_only",
                         wallet_eligibility="not_evaluated")
        graph.edge(f"module:{module}", "HAS_OPERATION", key)
        for function in functions:
            graph.edge(key, "USES_FUNCTION", function)


def add_deployment(graph: Graph, module: str, chain_id: int, source: str):
    key = f"deployment:{module}:{chain_id}"
    graph.node("Deployment", key, source, module=module, chain_id=chain_id,
               evidence_status="official_registry", live_eligibility="not_evaluated")
    graph.edge(f"module:{module}", "HAS_DEPLOYMENT", key)
    graph.edge(key, "ON_CHAIN", f"chain:{chain_id}")
    return key


def add_contract(graph: Graph, deployment: str, chain_id: int, role: str, address: str,
                 source: str, interface: str | None = None):
    # Registry role is part of identity: one address can legitimately have several roles.
    address = normalize_address(address)
    key = f"{deployment}:contract:{role}"
    graph.node("Contract", key, source, address=address, chain_id=chain_id, role=role,
               module=graph.nodes[deployment]["properties"]["module"], evidence_status="official_registry",
               abi_compatibility="not_verified", code_status="not_observed")
    graph.edge(deployment, "REGISTERS", key)
    if interface:
        graph.edge(key, "CANDIDATE_INTERFACE", interface_key(interface), basis="registry_role", verified=False)
    return key


def add_aave(graph: Graph, bundle: SourceBundle):
    for chain_id, book in ((1, "AaveV3Ethereum"), (11155111, "AaveV3Sepolia")):
        source = f"aave/book/{book}"
        core, assets = _parse_address_book(bundle.text(source))
        stata_tokens = dict(re.findall(r"address\s+internal\s+constant\s+([A-Za-z0-9_]+)_STATA_TOKEN\s*=\s*(0x[0-9a-fA-F]{40})\s*;", bundle.text(source)))
        for asset in assets:
            if asset["symbol"] in stata_tokens:
                asset["stata_token"] = stata_tokens[asset["symbol"]].lower()
        deployment = add_deployment(graph, "aave-v3", chain_id, source)
        contracts = {}
        for contract in core:
            role = contract["name"]
            contracts[role] = add_contract(graph, deployment, chain_id, role, contract["address"], source, AAVE_INTERFACES.get(role))
        for role, key in contracts.items():
            if role.endswith("_IMPL") and role[:-5] in contracts:
                graph.edge(contracts[role[:-5]], "IMPLEMENTATION_REPORTED", key, evidence="address_book", onchain_verified=False)
        missing_interfaces = sorted(role for role in contracts if role not in AAVE_INTERFACES and not role.endswith("_IMPL"))
        graph.gap(deployment, "additional_contract_interfaces", "Addresses are inventoried; interfaces are not mapped for: " + ", ".join(missing_interfaces), source)
        for asset in assets:
            reserve = graph.node("Reserve", f"{deployment}:reserve:{asset['underlying']}", source,
                                 symbol=asset["symbol"], chain_id=chain_id,
                                 underlying_address=asset["underlying"], decimals=asset.get("decimals"),
                                 configuration_status="not_observed", evidence_status="address_book_listing")
            graph.edge(deployment, "HAS_RESERVE", reserve)
            for kind, address in asset.items():
                if not isinstance(address, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
                    continue
                token_key = f"{reserve}:{kind}"
                label = "Contract" if kind in {"oracle", "interest_rate_strategy"} else "Token"
                graph.node(label, token_key, source, address=normalize_address(address), chain_id=chain_id,
                           module="aave-v3", evidence_status="official_registry", abi_compatibility="not_verified", code_status="not_observed",
                           symbol=asset["symbol"], role=kind, decimals=asset.get("decimals") if kind in {"underlying", "a_token", "v_token", "s_token"} else None)
                graph.edge(reserve, kind.upper(), token_key)
                if kind == "a_token":
                    graph.edge(token_key, "CANDIDATE_INTERFACE", interface_key("IAToken"), verified=False)
                elif kind == "stata_token":
                    graph.edge(token_key, "CANDIDATE_INTERFACE", interface_key("IStataTokenV2"), verified=False)
                elif kind == "interest_rate_strategy":
                    graph.edge(token_key, "CANDIDATE_INTERFACE", interface_key("IDefaultInterestRateStrategy"), verified=False)

    source = "aave/book/UmbrellaEthereum"
    text = bundle.text(source)
    deployment = add_deployment(graph, "aave-umbrella", 1, source)
    core, assets = text.split("library UmbrellaEthereumAssets", 1)
    contracts = {}
    for role, address in CORE_ADDRESS_PATTERN.findall(core):
        contracts[role] = add_contract(graph, deployment, 1, role, address, source, AAVE_INTERFACES.get(role))
    for role, key in contracts.items():
        if role.endswith("_IMPL") and role[:-5] in contracts:
            graph.edge(contracts[role[:-5]], "IMPLEMENTATION_REPORTED", key, evidence="address_book", onchain_verified=False)
    decimals = {name: int(value) for name, value in DECIMALS_PATTERN.findall(assets)}
    for role, address in CORE_ADDRESS_PATTERN.findall(assets):
        contract = add_contract(graph, deployment, 1, role, address, source, "IUmbrellaStakeToken")
        key = graph.node("StakingVault", f"{deployment}:vault:{role}", source, name=role,
                         address=normalize_address(address), chain_id=1, decimals=decimals.get(role),
                         asset_status="requires_asset_call", cooldown_status="requires_live_read", slashing_exposure=True)
        graph.edge(deployment, "HAS_STAKING_VAULT", key)
        graph.edge(key, "REGISTERS", contract)
        if "UMBRELLA_STAKE_TOKEN_IMPL" in contracts:
            graph.edge(contract, "IMPLEMENTATION_REPORTED", contracts["UMBRELLA_STAKE_TOKEN_IMPL"], evidence="shared_registry_implementation; per_proxy_read_required", onchain_verified=False)
    graph.gap(deployment, "helper_interfaces", "Batch helper, configuration engine and ancillary contract ABIs are not yet imported.", source)
    inventory = [entry["name"] for entry in bundle.json("aave/inventory")]
    if "UmbrellaSepolia.sol" in inventory:
        raise ValueError("Ethereum Sepolia Umbrella now appears in the registry; review the coverage configuration")
    graph.gap("module:aave-umbrella", "ethereum_sepolia_not_listed", "No UmbrellaSepolia.sol in the pinned official inventory. UmbrellaBaseSepolia.sol is a different chain. This is not proof of nonexistence.", "aave/inventory")
    other = [name for name in inventory if (name.startswith("AaveV") or name.startswith("Umbrella")) and name.endswith(".sol") and name not in {"AaveV3Ethereum.sol", "AaveV3Sepolia.sol", "UmbrellaEthereum.sol", "AaveV3.sol"}]
    graph.gap("module:aave-v3", "other_markets_and_versions", "Not imported in this release: " + ", ".join(other), "aave/inventory")


def add_uniswap(graph: Graph, bundle: SourceBundle):
    source = "uniswap/deployments"
    records = bundle.json(source)["records"]
    for chain_id in CHAINS:
        deployment = add_deployment(graph, "uniswap-v3", chain_id, source)
        selected = [r for r in records if r["protocol"] == "v3" and r["chainId"] == chain_id]
        if not selected:
            raise ValueError(f"No V3 deployments found for chain {chain_id}")
        for record in selected:
            key = add_contract(graph, deployment, chain_id, record["contract"], record["address"], source,
                               UNISWAP_INTERFACES.get(record["contract"]))
            graph.nodes[key]["properties"].update(registry_status=record.get("status", "unknown"),
                                                 source_ref=record.get("sourceRef", "unknown"),
                                                 explorer_url=record.get("explorerUrl", ""))
        missing = sorted({r["contract"] for r in selected} - UNISWAP_INTERFACES.keys())
        graph.gap(deployment, "additional_contract_interfaces", "Registry addresses included; ABIs not yet imported for: " + ", ".join(missing), source)
        graph.gap(deployment, "pool_universe", "Pool ABI is complete for its pinned release. Pool instances require factory discovery; this release only performs bounded pair lookups with --rpc.", source)
    other_versions = sorted({r["protocol"] for r in records} - {"v3"})
    other_chains = sorted({r["chainId"] for r in records if r["protocol"] == "v3"} - CHAINS.keys())
    graph.gap("module:uniswap-v3", "other_versions_networks", f"Registry versions outside this release: {other_versions}; other V3 chain IDs: {other_chains}.", source)


def build_graph(bundle: SourceBundle | None = None) -> Graph:
    bundle = bundle or SourceBundle()
    graph = Graph()
    for key, metadata in bundle.entries.items():
        graph.node("Source", f"source:{key}", **{k: v for k, v in metadata.items() if k != "key"}, source_key=key)
    for module, properties in MODULES.items():
        graph.node("Module", f"module:{module}", **properties, wallet_eligibility="not_evaluated")
    for chain_id, name in CHAINS.items():
        graph.node("Chain", f"chain:{chain_id}", chain_id=chain_id, name=name, testnet=chain_id != 1)
    add_interfaces(graph, bundle)
    add_aave(graph, bundle)
    add_uniswap(graph, bundle)
    for module in MODULES:
        scope = f"module:{module}"
        graph.gap(scope, "deployment_abi_compatibility", "Pinned interfaces may differ from deployed implementation revisions; registry role associations are candidates, not selector authorization.")
        graph.gap(scope, "live_wallet_eligibility", "Wallet balances, allowances, debt, health factor, market state and execution policy are not evaluated by this catalog.")
    graph.validate()
    return graph
