"""Load official Uniswap V3 Sepolia deployments and factory-created pools."""

import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from db.connection import get_session
from db.graph_builder import ensure_schema
from db.loaders.common import (
    RpcClient,
    decode_abi_string,
    fetch_json,
    normalize_address,
)


load_dotenv()

CHAIN_ID = 11155111
CHAIN_NAME = "Ethereum Sepolia"
PROTOCOL_KEY = "uniswap-v3-sepolia"
DEPLOYMENTS_URL = "https://developers.uniswap.org/deployments.json"
POOL_CREATED_TOPIC = (
    "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
)
# Creation block of the official Sepolia factory currently published in the
# deployment feed. Override UNISWAP_V3_START_BLOCK if Uniswap replaces it.
DEFAULT_FACTORY_START_BLOCK = 11124455
CANONICAL_SEPOLIA_WETH = "0xfff9976782d46cc05630d1f6ebab18b2324d6b14"

ROLE_BY_CONTRACT = {
    "uniswapv3factory": "factory",
    "swaprouter02": "swap_router",
    "swaprouter": "swap_router_legacy",
    "quoterv2": "quoter",
    "quoter": "quoter_legacy",
    "nonfungiblepositionmanager": "position_manager",
    "ticklens": "tick_lens",
    "v3migrator": "migrator",
}


def _role(contract_name: str) -> str:
    return ROLE_BY_CONTRACT.get(contract_name.lower(), contract_name.lower())


def _official_deployments():
    feed = fetch_json(DEPLOYMENTS_URL)
    records = []
    for record in feed.get("records", []):
        if (
            record.get("protocol") == "v3"
            and record.get("chainId") == CHAIN_ID
            and record.get("status") == "active"
            and record.get("address")
        ):
            records.append({
                "name": record["contract"],
                "role": _role(record["contract"]),
                "address": normalize_address(record["address"]),
                "tier": record.get("tier"),
                "source_repo": record.get("sourceRepo"),
                "source_ref": record.get("sourceRef"),
                "explorer_url": record.get("explorerUrl"),
            })
    if not any(record["role"] == "factory" for record in records):
        raise ValueError("Official Uniswap feed contains no active Sepolia V3 factory")
    return feed, records


def _find_deployment_block(rpc: RpcClient, address: str, latest: int) -> int:
    if rpc.code_at(address, latest) in ("0x", "0x0"):
        raise ValueError(f"No contract code at official factory {address}")
    return int(os.getenv("UNISWAP_V3_START_BLOCK", str(DEFAULT_FACTORY_START_BLOCK)))


def _pool_logs(rpc: RpcClient, factory: str):
    latest = rpc.latest_block()
    start = _find_deployment_block(rpc, factory, latest)
    chunk_size = int(os.getenv("UNISWAP_LOG_CHUNK_SIZE", "50000"))
    logs = []
    cursor = start
    while cursor <= latest:
        end = min(cursor + chunk_size - 1, latest)
        logs.extend(rpc.logs(factory, cursor, end, [POOL_CREATED_TOPIC]))
        cursor = end + 1
    return start, latest, logs


def _parse_pool(log):
    topics = log.get("topics", [])
    data = bytes.fromhex(log.get("data", "0x")[2:])
    if len(topics) != 4 or len(data) < 64:
        raise ValueError("Malformed PoolCreated log")
    token0 = normalize_address("0x" + topics[1][-40:])
    token1 = normalize_address("0x" + topics[2][-40:])
    fee = int(topics[3], 16)
    tick_spacing = int.from_bytes(data[:32], "big", signed=True)
    pool = normalize_address("0x" + data[32:64][-20:].hex())
    return {
        "address": pool,
        "token0": token0,
        "token1": token1,
        "fee": fee,
        "tick_spacing": tick_spacing,
        "created_block": int(log["blockNumber"], 16),
        "creation_tx": log.get("transactionHash"),
    }


def _token_metadata(rpc: RpcClient, address: str):
    symbol = None
    decimals = None
    try:
        symbol = decode_abi_string(rpc.eth_call(address, "0x95d89b41"))
    except Exception:
        pass
    try:
        raw = rpc.eth_call(address, "0x313ce567")
        if raw and raw != "0x":
            decimals = int(raw, 16)
    except Exception:
        pass
    return {"address": address, "symbol": symbol, "decimals": decimals}


def _load_deployments(session, records, feed, synced_at):
    session.run(
        """
        MERGE (chain:Chain {chain_id:$chain_id})
        SET chain.name=$chain_name, chain.testnet=true
        MERGE (protocol:Protocol {key:$key})
        SET protocol.name='Uniswap V3', protocol.version='3', protocol.verified=true,
            protocol.chain_id=$chain_id, protocol.source_url=$source,
            protocol.source_commit=$source_commit, protocol.last_synced_at=$synced_at
        MERGE (protocol)-[:DEPLOYED_ON]->(chain)
        WITH protocol
        UNWIND $records AS item
        MERGE (contract:Contract {chain_id:$chain_id, address:item.address})
        SET contract.name=item.name, contract.role=item.role, contract.tier=item.tier,
            contract.verified=true, contract.source='uniswap-deployments-feed',
            contract.source_repo=item.source_repo, contract.source_ref=item.source_ref,
            contract.explorer_url=item.explorer_url, contract.last_synced_at=$synced_at
        MERGE (protocol)-[:DEPLOYED_CONTRACT {role:item.role}]->(contract)
        """,
        chain_id=CHAIN_ID,
        chain_name=CHAIN_NAME,
        key=PROTOCOL_KEY,
        source=DEPLOYMENTS_URL,
        source_commit=(feed.get("source") or {}).get("commit"),
        synced_at=synced_at,
        records=records,
    ).consume()


def _load_pools(session, pools, tokens, factory, synced_at):
    session.run(
        """
        UNWIND $tokens AS item
        MERGE (token:Token {chain_id:$chain_id, address:item.address})
        SET token.symbol=coalesce(item.symbol, token.symbol, 'UNKNOWN'),
            token.decimals=coalesce(item.decimals, token.decimals),
            token.verified=CASE WHEN item.trusted THEN true ELSE coalesce(token.verified, false) END,
            token.source=coalesce(token.source, 'uniswap-v3-factory'),
            token.last_synced_at=$synced_at
        """,
        tokens=tokens,
        chain_id=CHAIN_ID,
        synced_at=synced_at,
    ).consume()
    session.run(
        """
        MATCH (protocol:Protocol {key:$key})
        MATCH (factory:Contract {chain_id:$chain_id, address:$factory})
        UNWIND $pools AS item
        MERGE (pool:Contract:Pool {chain_id:$chain_id, address:item.address})
        SET pool.protocol='Uniswap V3', pool.verified=true, pool.action='swap',
            pool.fee=item.fee, pool.tick_spacing=item.tick_spacing,
            pool.created_block=item.created_block, pool.creation_tx=item.creation_tx,
            pool.source='uniswap-v3-factory', pool.last_synced_at=$synced_at
        MERGE (protocol)-[:HAS_POOL]->(pool)
        MERGE (factory)-[:CREATED_POOL]->(pool)
        WITH pool, item
        MATCH (token0:Token {chain_id:$chain_id, address:item.token0})
        MATCH (token1:Token {chain_id:$chain_id, address:item.token1})
        MERGE (pool)-[:TOKEN0]->(token0)
        MERGE (pool)-[:TOKEN1]->(token1)
        MERGE (pool)-[:SUPPORTS_TOKEN]->(token0)
        MERGE (pool)-[:SUPPORTS_TOKEN]->(token1)
        MERGE (pool)-[:SWAPS_TOKEN]->(token0)
        MERGE (pool)-[:SWAPS_TOKEN]->(token1)
        """,
        key=PROTOCOL_KEY,
        chain_id=CHAIN_ID,
        factory=factory,
        pools=pools,
        synced_at=synced_at,
    ).consume()
    session.run(
        """
        MATCH (protocol:Protocol {key:$key})
        MERGE (action:Action {name:'swap'})
        MERGE (protocol)-[:SUPPORTS_ACTION]->(action)
        """,
        key=PROTOCOL_KEY,
    ).consume()


def load_uniswap_v3(ensure_constraints=True):
    if ensure_constraints:
        ensure_schema()
    feed, records = _official_deployments()
    factory = next(item["address"] for item in records if item["role"] == "factory")
    rpc = RpcClient(os.getenv("SEPOLIA_RPC"))
    actual_chain_id = rpc.chain_id()
    if actual_chain_id != CHAIN_ID:
        raise ValueError(
            f"SEPOLIA_RPC is connected to chain {actual_chain_id}; expected {CHAIN_ID}"
        )

    start, latest, raw_logs = _pool_logs(rpc, factory)
    pools = [_parse_pool(log) for log in raw_logs]
    token_addresses = sorted({
        address for pool in pools for address in (pool["token0"], pool["token1"])
    })
    # A factory-created pool proves that the pool is authentic Uniswap, not
    # that either ERC-20 is trustworthy. Only enrich/approve tokens already
    # verified by an authoritative loader, plus Uniswap's canonical WETH.
    with get_session() as session:
        trusted = {
            row["address"]
            for row in session.run(
                "MATCH (t:Token {chain_id:$chain_id, verified:true}) RETURN t.address AS address",
                chain_id=CHAIN_ID,
            )
            if row["address"]
        }
    trusted.add(CANONICAL_SEPOLIA_WETH)
    metadata = {
        address: _token_metadata(rpc, address)
        for address in token_addresses
        if address in trusted
    }
    tokens = []
    for address in token_addresses:
        token = metadata.get(address, {"address": address, "symbol": None, "decimals": None})
        token["trusted"] = address in trusted
        tokens.append(token)
    synced_at = datetime.now(timezone.utc).isoformat()

    with get_session() as session:
        _load_deployments(session, records, feed, synced_at)
        _load_pools(session, pools, tokens, factory, synced_at)
    return {
        "source": DEPLOYMENTS_URL,
        "factory": factory,
        "deployment_block": start,
        "latest_block": latest,
        "contracts": len(records),
        "pools": len(pools),
        "tokens": len(tokens),
    }


if __name__ == "__main__":
    print(json.dumps(load_uniswap_v3(), indent=2))
