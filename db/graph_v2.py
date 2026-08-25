"""Canonical v2 thesis graph: protocol families, deployments, and views.

This model is intentionally built alongside the legacy graph. It does not
delete existing nodes, and all visualization queries can target the v2 labels.
"""

import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from db.connection import get_session
from db.loaders.aave_loader import _parse_address_book
from db.loaders.common import RpcClient, decode_abi_string, fetch_json, fetch_text
from db.loaders.uniswap_loader import POOL_CREATED_TOPIC, _parse_pool, _role


load_dotenv()

GRAPH_VERSION = "official-v2"
AAVE_SOURCES = {
    1: "https://raw.githubusercontent.com/aave-dao/aave-address-book/refs/heads/main/src/AaveV3Ethereum.sol",
    11155111: "https://raw.githubusercontent.com/aave-dao/aave-address-book/refs/heads/main/src/AaveV3Sepolia.sol",
}
UNISWAP_DEPLOYMENTS_URL = "https://developers.uniswap.org/deployments.json"
NETWORKS = {
    1: {
        "name": "Ethereum Mainnet",
        "testnet": False,
        "rpc_env": "MAINNET_RPC",
        "factory_start_block": 12369621,
        "weth": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    },
    11155111: {
        "name": "Ethereum Sepolia",
        "testnet": True,
        "rpc_env": "SEPOLIA_RPC",
        "factory_start_block": 11124455,
        "weth": "0xfff9976782d46cc05630d1f6ebab18b2324d6b14",
    },
}

FEATURED_ASSET_SYMBOLS = {
    "AAVE", "DAI", "GHO", "LINK", "USDC", "USDT", "WBTC", "WETH"
}
FEATURED_SWAP_PAIRS = {
    frozenset(pair)
    for pair in (
        ("USDC", "WETH"),
        ("USDT", "WETH"),
        ("DAI", "WETH"),
        ("GHO", "WETH"),
        ("WBTC", "WETH"),
        ("LINK", "WETH"),
        ("AAVE", "WETH"),
    )
}

# Function selectors are part of the authorization path. A verified contract
# address alone is not enough: the graph must also authorize the intended
# function on the contract role that executes it.
PROTOCOL_FUNCTIONS = {
    "aave-v3": (
        {
            "contract_role": "pool", "action": "supply", "purpose": "execute",
            "name": "supply", "signature": "supply(address,uint256,address,uint16)",
            "selector": "0x617ba037",
            "source_url": "https://github.com/aave/aave-v3-core/blob/master/contracts/interfaces/IPool.sol",
        },
        {
            "contract_role": "pool", "action": "withdraw", "purpose": "execute",
            "name": "withdraw", "signature": "withdraw(address,uint256,address)",
            "selector": "0x69328dec",
            "source_url": "https://github.com/aave/aave-v3-core/blob/master/contracts/interfaces/IPool.sol",
        },
        {
            "contract_role": "pool", "action": "borrow", "purpose": "execute",
            "name": "borrow", "signature": "borrow(address,uint256,uint256,uint16,address)",
            "selector": "0xa415bcad",
            "source_url": "https://github.com/aave/aave-v3-core/blob/master/contracts/interfaces/IPool.sol",
        },
        {
            "contract_role": "pool", "action": "repay", "purpose": "execute",
            "name": "repay", "signature": "repay(address,uint256,uint256,address)",
            "selector": "0x573ade81",
            "source_url": "https://github.com/aave/aave-v3-core/blob/master/contracts/interfaces/IPool.sol",
        },
    ),
    "uniswap-v3": (
        {
            "contract_role": "swap_router", "action": "swap", "purpose": "execute",
            "name": "exactInputSingle",
            "signature": "exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))",
            "selector": "0x04e45aaf",
            "source_url": "https://github.com/Uniswap/swap-router-contracts/blob/main/contracts/interfaces/IV3SwapRouter.sol",
        },
        {
            "contract_role": "quoter", "action": "swap", "purpose": "preflight",
            "name": "quoteExactInputSingle",
            "signature": "quoteExactInputSingle((address,address,uint256,uint24,uint160))",
            "selector": "0xc6a5026a",
            "source_url": "https://github.com/Uniswap/v3-periphery/blob/main/contracts/interfaces/IQuoterV2.sol",
        },
    ),
}

# A small, real Mainnet projection remains available even when MAINNET_RPC is
# not configured. Full Mainnet discovery is enabled automatically when it is.
CURATED_MAINNET_POOLS = (
    {
        "address": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
        "token0": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "token1": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        "fee": 500,
        "tick_spacing": 10,
        "created_block": None,
        "creation_tx": None,
        "featured": True,
        "verified": True,
        "source": "curated-mainnet-seed",
    },
    {
        "address": "0xc2e9f25be6257c210d7adf0d4cd6e3e881ba25f8",
        "token0": "0x6b175474e89094c44da98b954eedeac495271d0f",
        "token1": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        "fee": 3000,
        "tick_spacing": 60,
        "created_block": None,
        "creation_tx": None,
        "featured": True,
        "verified": True,
        "source": "curated-mainnet-seed",
    },
)

V2_CONSTRAINTS = (
    "CREATE CONSTRAINT protocol_family_key IF NOT EXISTS FOR (n:ProtocolFamily) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT protocol_deployment_key IF NOT EXISTS FOR (n:ProtocolDeployment) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT reserve_key IF NOT EXISTS FOR (n:Reserve) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT graph_view_key IF NOT EXISTS FOR (n:GraphView) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT fixture_node_key IF NOT EXISTS FOR (n:FixtureNode) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT function_key IF NOT EXISTS FOR (n:Function) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT fee_tier_key IF NOT EXISTS FOR (n:FeeTier) REQUIRE n.key IS UNIQUE",
)


def ensure_v2_schema():
    with get_session() as session:
        for statement in V2_CONSTRAINTS:
            session.run(statement).consume()


def _cleanup_orphan_asset_support_nodes():
    """Remove unlabeled nodes created by the pre-v2.1 SUPPORTS_ASSET scope bug."""
    with get_session() as session:
        record = session.run(
            """
            MATCH (orphan)-[:SUPPORTS_ASSET]->(:Token)
            WHERE labels(orphan)=[]
              AND NOT EXISTS { MATCH ()-[]->(orphan) }
              AND NOT EXISTS {
                MATCH (orphan)-[other]->()
                WHERE type(other) <> 'SUPPORTS_ASSET'
              }
            WITH DISTINCT orphan
            DETACH DELETE orphan
            RETURN count(*) AS removed
            """
        ).single()
    return record["removed"] if record else 0


def _now():
    return datetime.now(timezone.utc).isoformat()


def _deployment_key(protocol_key, chain_id):
    return f"{protocol_key}:{chain_id}"


def _upsert_deployment(session, protocol_key, protocol_name, chain_id, source_url):
    network = NETWORKS[chain_id]
    key = _deployment_key(protocol_key, chain_id)
    session.run(
        """
        MERGE (chain:Chain {chain_id:$chain_id})
        SET chain.name=$chain_name, chain.testnet=$testnet
        MERGE (family:ProtocolFamily {key:$protocol_key})
        SET family.name=$protocol_name, family.version='3', family.graph_version=$graph_version
        MERGE (deployment:ProtocolDeployment {key:$deployment_key})
        SET deployment.name=$protocol_name + ' — ' + $chain_name,
            deployment.protocol_key=$protocol_key, deployment.chain_id=$chain_id,
            deployment.network=$chain_name, deployment.verified=true,
            deployment.source_url=$source_url, deployment.graph_version=$graph_version,
            deployment.last_synced_at=$synced_at
        MERGE (family)-[:HAS_DEPLOYMENT]->(deployment)
        MERGE (chain)-[:HOSTS]->(deployment)
        MERGE (deployment)-[:DEPLOYED_ON]->(chain)
        """,
        chain_id=chain_id,
        chain_name=network["name"],
        testnet=network["testnet"],
        protocol_key=protocol_key,
        protocol_name=protocol_name,
        deployment_key=key,
        source_url=source_url,
        graph_version=GRAPH_VERSION,
        synced_at=_now(),
    ).consume()
    return key


def _add_actions(session, deployment_key, actions):
    session.run(
        """
        MATCH (deployment:ProtocolDeployment {key:$deployment_key})
        UNWIND $actions AS name
        MERGE (action:Action {name:name})
        MERGE (deployment)-[:SUPPORTS_ACTION]->(action)
        """,
        deployment_key=deployment_key,
        actions=list(actions),
    ).consume()


def _add_functions(session, deployment_key, protocol_key):
    """Attach the approved ABI surface to each active execution contract."""
    functions = []
    for item in PROTOCOL_FUNCTIONS[protocol_key]:
        functions.append({**item, "key": f"{protocol_key}:{item['signature']}"})
    session.run(
        """
        MATCH (deployment:ProtocolDeployment {key:$deployment_key})
              -[deployed:DEPLOYED_CONTRACT]->(contract:Contract {verified:true})
        WHERE deployed.active=true
        UNWIND $functions AS item
        WITH deployment, deployed, contract, item
        WHERE deployed.role=item.contract_role
        MATCH (deployment)-[:SUPPORTS_ACTION]->(action:Action {name:item.action})
        MERGE (fn:Function {key:item.key})
        SET fn.name=item.name, fn.signature=item.signature,
            fn.selector=item.selector, fn.purpose=item.purpose,
            fn.verified=true, fn.source_url=item.source_url,
            fn.graph_version=$graph_version
        MERGE (contract)-[:EXPOSES_FUNCTION]->(fn)
        MERGE (fn)-[:IMPLEMENTS_ACTION]->(action)
        """,
        deployment_key=deployment_key,
        functions=functions,
        graph_version=GRAPH_VERSION,
    ).consume()


def load_aave_v2(chain_id):
    source_url = AAVE_SOURCES[chain_id]
    contracts, assets = _parse_address_book(fetch_text(source_url))
    deployment_key = _deployment_key("aave-v3", chain_id)
    synced_at = _now()
    with get_session() as session:
        _upsert_deployment(session, "aave-v3", "Aave V3", chain_id, source_url)
        _add_actions(session, deployment_key, ("supply", "withdraw", "borrow", "repay"))
        session.run(
            """
            MATCH (deployment:ProtocolDeployment {key:$deployment_key})
            OPTIONAL MATCH (deployment)-[contract_rel:DEPLOYED_CONTRACT]->()
            SET contract_rel.active=false
            WITH deployment
            OPTIONAL MATCH (deployment)-[reserve_rel:HAS_RESERVE]->(reserve:Reserve)
            SET reserve_rel.active=false, reserve.active=false
            """,
            deployment_key=deployment_key,
        ).consume()
        session.run(
            """
            MATCH (deployment:ProtocolDeployment {key:$deployment_key})
            UNWIND $contracts AS item
            MERGE (contract:Contract {chain_id:$chain_id, address:item.address})
            SET contract.name=coalesce(contract.name, item.name),
                contract.role=coalesce(contract.role, item.role), contract.verified=true,
                contract.source='aave-address-book', contract.graph_version=$graph_version,
                contract.last_synced_at=$synced_at
            MERGE (deployment)-[rel:DEPLOYED_CONTRACT {role:item.role}]->(contract)
            SET rel.active=true, rel.last_synced_at=$synced_at
            """,
            deployment_key=deployment_key,
            chain_id=chain_id,
            contracts=contracts,
            graph_version=GRAPH_VERSION,
            synced_at=synced_at,
        ).consume()

        for asset in assets:
            reserve_key = f"aave-v3:{chain_id}:{asset['underlying']}"
            reserve_actions = ["supply", "withdraw"]
            if asset.get("v_token"):
                reserve_actions.extend(("borrow", "repay"))
            session.run(
                """
                MATCH (deployment:ProtocolDeployment {key:$deployment_key})
                MERGE (token:Token {chain_id:$chain_id, address:$underlying})
                SET token.symbol=$symbol, token.decimals=$decimals, token.verified=true,
                    token.source='aave-address-book', token.graph_version=$graph_version,
                    token.trust_source='aave-address-book',
                    token.verification_eligible=true, token.last_synced_at=$synced_at
                MERGE (reserve:Reserve {key:$reserve_key})
                SET reserve.symbol=$symbol, reserve.chain_id=$chain_id,
                    reserve.verified=true, reserve.source='aave-address-book',
                    reserve.graph_version=$graph_version, reserve.featured=$featured,
                    reserve.last_synced_at=$synced_at
                SET reserve.active=true
                MERGE (deployment)-[reserve_rel:HAS_RESERVE]->(reserve)
                SET reserve_rel.active=true, reserve_rel.last_synced_at=$synced_at
                MERGE (deployment)-[:SUPPORTS_ASSET]->(token)
                MERGE (reserve)-[:UNDERLYING_ASSET]->(token)
                WITH reserve
                UNWIND $actions AS action_name
                MERGE (action:Action {name:action_name})
                MERGE (reserve)-[:SUPPORTS_ACTION]->(action)
                """,
                deployment_key=deployment_key,
                chain_id=chain_id,
                reserve_key=reserve_key,
                actions=reserve_actions,
                featured=asset["symbol"] in FEATURED_ASSET_SYMBOLS,
                graph_version=GRAPH_VERSION,
                synced_at=synced_at,
                **asset,
            ).consume()
            session.run(
                """
                MATCH (deployment:ProtocolDeployment {key:$deployment_key})
                      -[pool_rel:DEPLOYED_CONTRACT {role:'pool'}]->(pool:Contract)
                MATCH (reserve:Reserve {key:$reserve_key})-[:UNDERLYING_ASSET]->(token:Token)
                WHERE pool_rel.active=true
                MERGE (pool)-[:SUPPORTS_TOKEN]->(token)
                """,
                deployment_key=deployment_key,
                reserve_key=reserve_key,
            ).consume()

            links = (
                ("a_token", "aToken", "HAS_A_TOKEN", "REPRESENTS_ASSET"),
                ("v_token", "variableDebtToken", "HAS_VARIABLE_DEBT_TOKEN", "DEBT_FOR"),
                ("s_token", "stableDebtToken", "HAS_STABLE_DEBT_TOKEN", "DEBT_FOR"),
                ("oracle", "oracle", "USES_ORACLE", "PRICES"),
                ("static_a_token", "staticAToken", "HAS_STATIC_A_TOKEN", "REPRESENTS_ASSET"),
                (
                    "interest_rate_strategy", "interestRateStrategy",
                    "USES_INTEREST_RATE_STRATEGY", "CONFIGURES_RATES_FOR"
                ),
            )
            for field, role, relationship, token_relationship in links:
                address = asset.get(field)
                if not address:
                    continue
                session.run(
                    f"""
                    MATCH (deployment:ProtocolDeployment {{key:$deployment_key}})
                    MATCH (reserve:Reserve {{key:$reserve_key}})-[:UNDERLYING_ASSET]->(token:Token)
                    MERGE (contract:Contract {{chain_id:$chain_id, address:$address}})
                    SET contract.name=$symbol + ' ' + $role, contract.role=$role,
                        contract.verified=true, contract.source='aave-address-book',
                        contract.graph_version=$graph_version,
                        contract.last_synced_at=$synced_at
                    MERGE (reserve)-[:{relationship}]->(contract)
                    MERGE (contract)-[:{token_relationship}]->(token)
                    MERGE (deployment)-[contract_rel:DEPLOYED_CONTRACT {{role:$role}}]->(contract)
                    SET contract_rel.active=true, contract_rel.last_synced_at=$synced_at
                    """,
                    reserve_key=reserve_key,
                    deployment_key=deployment_key,
                    chain_id=chain_id,
                    address=address,
                    symbol=asset["symbol"],
                    role=role,
                    graph_version=GRAPH_VERSION,
                    synced_at=synced_at,
                ).consume()
        _add_functions(session, deployment_key, "aave-v3")
        session.run(
            """
            MATCH (deployment:ProtocolDeployment {key:$deployment_key})
            SET deployment.asset_coverage='official-address-book-complete',
                deployment.asset_count=$asset_count
            """,
            deployment_key=deployment_key,
            asset_count=len(assets),
        ).consume()
    return {"chain_id": chain_id, "contracts": len(contracts), "reserves": len(assets)}


def _uniswap_records(feed, chain_id):
    records = []
    for record in feed.get("records", []):
        if (
            record.get("protocol") == "v3"
            and record.get("chainId") == chain_id
            and record.get("status") == "active"
            and record.get("address")
        ):
            records.append({
                "name": record["contract"],
                "role": _role(record["contract"]),
                "address": record["address"].lower(),
                "tier": record.get("tier"),
                "source_repo": record.get("sourceRepo"),
                "source_ref": record.get("sourceRef"),
                "explorer_url": record.get("explorerUrl"),
            })
    return records


def _scan_factory(rpc, factory, start_block):
    latest = rpc.latest_block()
    chunk_size = int(os.getenv("UNISWAP_LOG_CHUNK_SIZE", "50000"))
    pools = []
    cursor = start_block
    while cursor <= latest:
        end = min(cursor + chunk_size - 1, latest)
        logs = rpc.logs(factory, cursor, end, [POOL_CREATED_TOPIC])
        pools.extend(_parse_pool(log) for log in logs)
        cursor = end + 1
    return latest, pools


def _erc20_metadata(rpc, address):
    symbol = None
    decimals = None
    try:
        symbol = decode_abi_string(rpc.eth_call(address, "0x95d89b41"))
    except Exception:
        pass
    try:
        raw = rpc.eth_call(address, "0x313ce567")
        decimals = int(raw, 16) if raw and raw != "0x" else None
    except Exception:
        pass
    return symbol, decimals


def _filter_trusted_pools(pools, trusted_addresses):
    """Keep only pools whose two endpoints have independent provenance."""
    return [
        pool for pool in pools
        if pool["token0"] in trusted_addresses and pool["token1"] in trusted_addresses
    ]


def _upsert_uniswap_pools(session, deployment_key, chain_id, factory, pools, rpc=None):
    synced_at = _now()
    discovered_pools = list(pools)
    trusted = {
        row["address"]
        for row in session.run(
            """
            MATCH (:ProtocolDeployment {key:$aave_key})-[rel:HAS_RESERVE]->
                  (:Reserve {verified:true, active:true})-[:UNDERLYING_ASSET]->
                  (t:Token {chain_id:$chain_id, verified:true})
            WHERE rel.active=true
            RETURN DISTINCT t.address AS address
            """,
            chain_id=chain_id,
            aave_key=_deployment_key("aave-v3", chain_id),
        )
        if row["address"]
    }
    trusted.add(NETWORKS[chain_id]["weth"])
    accepted_pools = _filter_trusted_pools(discovered_pools, trusted)
    pools = [
        {
            **pool,
            "trusted": pool["token0"] in trusted and pool["token1"] in trusted,
        }
        for pool in discovered_pools
    ]
    token_addresses = sorted({
        address for pool in discovered_pools
        for address in (pool["token0"], pool["token1"])
    })
    tokens = []
    for address in token_addresses:
        symbol = decimals = None
        if rpc and address in trusted:
            symbol, decimals = _erc20_metadata(rpc, address)
        tokens.append({
            "address": address,
            "symbol": symbol,
            "decimals": decimals,
            "source": (
                "canonical-weth" if address == NETWORKS[chain_id]["weth"]
                else "aave-address-book" if address in trusted
                else "uniswap-v3-factory-discovery"
            ),
            "trusted": address in trusted,
        })
    session.run(
        """
        UNWIND $tokens AS item
        MERGE (token:Token {chain_id:$chain_id, address:item.address})
        SET token.symbol=coalesce(item.symbol, token.symbol, 'UNKNOWN'),
            token.decimals=coalesce(item.decimals, token.decimals),
            token.verified=CASE WHEN item.trusted THEN true ELSE coalesce(token.verified,false) END,
            token.trust_source=CASE WHEN item.trusted THEN item.source ELSE token.trust_source END,
            token.discovery_source=CASE WHEN item.trusted THEN token.discovery_source ELSE item.source END,
            token.verification_eligible=item.trusted,
            token.graph_version=$graph_version, token.last_synced_at=$synced_at
        """,
        tokens=tokens,
        chain_id=chain_id,
        graph_version=GRAPH_VERSION,
        synced_at=synced_at,
    ).consume()
    session.run(
        """
        MATCH (deployment:ProtocolDeployment {key:$deployment_key})
        MATCH (factory:Contract {chain_id:$chain_id, address:$factory})
        UNWIND $pools AS item
        MERGE (pool:Contract:Pool {chain_id:$chain_id, address:item.address})
        SET pool.protocol='Uniswap V3', pool.verified=item.trusted,
            pool.verification_eligible=item.trusted, pool.fee=item.fee,
            pool.tick_spacing=item.tick_spacing, pool.created_block=item.created_block,
            pool.creation_tx=item.creation_tx,
            pool.source=coalesce(item.source, 'uniswap-v3-factory'),
            pool.graph_version=$graph_version,
            pool.featured=coalesce(item.featured, pool.featured, false),
            pool.last_synced_at=$synced_at
        SET pool.active=true, pool.trust_policy='both-assets-officially-verified'
        MERGE (deployment)-[pool_rel:HAS_POOL]->(pool)
        SET pool_rel.active=true, pool_rel.last_synced_at=$synced_at
        MERGE (factory)-[:CREATED_POOL]->(pool)
        WITH deployment, pool, item
        MATCH (token0:Token {chain_id:$chain_id, address:item.token0})
        MATCH (token1:Token {chain_id:$chain_id, address:item.token1})
        MERGE (pool)-[:TOKEN0]->(token0)
        MERGE (pool)-[:TOKEN1]->(token1)
        MERGE (pool)-[:SUPPORTS_TOKEN]->(token0)
        MERGE (pool)-[:SUPPORTS_TOKEN]->(token1)
        MERGE (deployment)-[:DISCOVERED_ASSET]->(token0)
        MERGE (deployment)-[:DISCOVERED_ASSET]->(token1)
        WITH deployment, pool, item
        MERGE (fee:FeeTier {key:toString($chain_id) + ':' + toString(item.fee)})
        SET fee.fee=item.fee, fee.percent=item.fee / 10000.0,
            fee.tick_spacing=item.tick_spacing, fee.graph_version=$graph_version
        MERGE (pool)-[:USES_FEE_TIER]->(fee)
        WITH pool
        MATCH (action:Action {name:'swap'})
        MERGE (pool)-[:SUPPORTS_ACTION]->(action)
        """,
        deployment_key=deployment_key,
        chain_id=chain_id,
        factory=factory,
        pools=list(pools),
        graph_version=GRAPH_VERSION,
        synced_at=synced_at,
    ).consume()
    session.run(
        """
        MATCH (deployment:ProtocolDeployment {key:$deployment_key})
        UNWIND $trusted_tokens AS address
        MATCH (token:Token {chain_id:$chain_id, address:address})
        MERGE (deployment)-[:SUPPORTS_ASSET]->(token)
        """,
        deployment_key=deployment_key,
        chain_id=chain_id,
        trusted_tokens=sorted({
            address for pool in accepted_pools
            for address in (pool["token0"], pool["token1"])
        }),
    ).consume()
    return {
        "discovered": len(discovered_pools),
        "accepted": len(accepted_pools),
        "rejected_untrusted": len(discovered_pools) - len(accepted_pools),
        "discovered_assets": len(token_addresses),
        "trusted_assets": len({
            address for pool in accepted_pools
            for address in (pool["token0"], pool["token1"])
        }),
    }


def load_uniswap_v2(chain_id, feed=None):
    feed = feed or fetch_json(UNISWAP_DEPLOYMENTS_URL)
    records = _uniswap_records(feed, chain_id)
    if not records:
        raise ValueError(f"No active Uniswap V3 deployments for chain {chain_id}")
    factory = next(item["address"] for item in records if item["role"] == "factory")
    deployment_key = _deployment_key("uniswap-v3", chain_id)
    with get_session() as session:
        _upsert_deployment(
            session, "uniswap-v3", "Uniswap V3", chain_id, UNISWAP_DEPLOYMENTS_URL
        )
        _add_actions(session, deployment_key, ("swap",))
        session.run(
            """
            MATCH (deployment:ProtocolDeployment {key:$deployment_key})
            OPTIONAL MATCH (deployment)-[contract_rel:DEPLOYED_CONTRACT]->()
            SET contract_rel.active=false
            WITH deployment
            OPTIONAL MATCH (deployment)-[pool_rel:HAS_POOL]->(pool:Pool)
            SET pool_rel.active=false, pool.active=false, pool.featured=false
            """,
            deployment_key=deployment_key,
        ).consume()
        session.run(
            """
            MATCH (deployment:ProtocolDeployment {key:$deployment_key})
            UNWIND $records AS item
            MERGE (contract:Contract {chain_id:$chain_id, address:item.address})
            SET contract.name=item.name, contract.role=item.role, contract.tier=item.tier,
                contract.verified=true, contract.source='uniswap-deployments-feed',
                contract.source_repo=item.source_repo, contract.source_ref=item.source_ref,
                contract.explorer_url=item.explorer_url, contract.graph_version=$graph_version
            MERGE (deployment)-[rel:DEPLOYED_CONTRACT {role:item.role}]->(contract)
            SET rel.active=true, rel.last_synced_at=$synced_at
            """,
            deployment_key=deployment_key,
            chain_id=chain_id,
            records=records,
            graph_version=GRAPH_VERSION,
            synced_at=_now(),
        ).consume()
        _add_functions(session, deployment_key, "uniswap-v3")

        rpc_url = os.getenv(NETWORKS[chain_id]["rpc_env"])
        pools = list(CURATED_MAINNET_POOLS) if chain_id == 1 else []
        latest = None
        rpc = None
        if rpc_url:
            rpc = RpcClient(rpc_url)
            if rpc.chain_id() != chain_id:
                raise ValueError(f"{NETWORKS[chain_id]['rpc_env']} is on the wrong chain")
            latest, discovered = _scan_factory(
                rpc, factory, NETWORKS[chain_id]["factory_start_block"]
            )
            by_address = {pool["address"]: pool for pool in pools}
            by_address.update({pool["address"]: pool for pool in discovered})
            pools = list(by_address.values())
        coverage = _upsert_uniswap_pools(
            session, deployment_key, chain_id, factory, pools, rpc
        )
        session.run(
            """
            UNWIND $pairs AS pair
            MATCH (deployment:ProtocolDeployment {key:$deployment_key})
                  -[rel:HAS_POOL]->(pool:Pool {active:true, verification_eligible:true})
            WHERE rel.active=true
            MATCH (pool)-[:TOKEN0]->(token0:Token {verified:true})
            MATCH (pool)-[:TOKEN1]->(token1:Token {verified:true})
            WHERE (token0.symbol=pair.left AND token1.symbol=pair.right)
               OR (token0.symbol=pair.right AND token1.symbol=pair.left)
            WITH pair, pool ORDER BY pool.fee ASC
            WITH pair, collect(DISTINCT pool)[0..2] AS selected
            UNWIND selected AS pool
            SET pool.featured=true
            """,
            deployment_key=deployment_key,
            pairs=[
                {"left": sorted(pair)[0], "right": sorted(pair)[1]}
                for pair in sorted(FEATURED_SWAP_PAIRS, key=lambda p: sorted(p))
            ],
        ).consume()
        session.run(
            """
            MATCH (deployment:ProtocolDeployment {key:$deployment_key})
            SET deployment.pool_discovery_complete=$complete,
                deployment.pool_discovery_mode=$mode,
                deployment.factory_scanned_to_block=$latest_block,
                deployment.discovered_pool_count=$discovered,
                deployment.accepted_pool_count=$accepted,
                deployment.rejected_untrusted_pool_count=$rejected,
                deployment.discovered_asset_count=$discovered_assets,
                deployment.trusted_asset_count=$trusted_assets,
                deployment.asset_trust_scope='active Aave V3 reserves plus canonical WETH'
            """,
            deployment_key=deployment_key,
            complete=bool(rpc_url),
            mode="full-rpc" if rpc_url else "curated-no-rpc",
            latest_block=latest,
            discovered=coverage["discovered"],
            accepted=coverage["accepted"],
            rejected=coverage["rejected_untrusted"],
            discovered_assets=coverage["discovered_assets"],
            trusted_assets=coverage["trusted_assets"],
        ).consume()
    return {
        "chain_id": chain_id,
        "contracts": len(records),
        "pools": coverage["accepted"],
        "discovered_pools": coverage["discovered"],
        "rejected_untrusted_pools": coverage["rejected_untrusted"],
        "discovered_assets": coverage["discovered_assets"],
        "trusted_assets_in_pools": coverage["trusted_assets"],
        "latest_block": latest,
        "mode": "full-rpc" if rpc_url else "curated-no-rpc",
    }


def build_demo_view():
    with get_session() as session:
        session.run(
            """
            MATCH (view:GraphView {key:'thesis-demo-v2'})-[old:INCLUDES]->()
            DELETE old
            """
        ).consume()
        session.run(
            """
            MERGE (view:GraphView {key:'thesis-demo-v2'})
            SET view.name='Thesis Demo — Mainnet and Sepolia', view.graph_version=$graph_version
            WITH view
            MATCH (node)
            WHERE node:ProtocolFamily
               OR node:ProtocolDeployment
               OR node:Chain
               OR (node:Reserve AND node.featured=true)
               OR (node:Pool AND node.featured=true AND EXISTS {
                    MATCH (:ProtocolDeployment {protocol_key:'uniswap-v3'})-[:HAS_POOL]->(node)
                  })
            MERGE (view)-[:INCLUDES]->(node)
            """,
            graph_version=GRAPH_VERSION,
        ).consume()
        session.run(
            """
            MATCH (view:GraphView {key:'thesis-demo-v2'})
            MATCH (view)-[:INCLUDES]->(parent)-[r]->(child)
            WHERE child:Action
               OR (parent:ProtocolDeployment AND child:Contract
                   AND child.role IN ['factory', 'swap_router', 'quoter', 'pool'])
               OR ((parent:Reserve OR parent:Pool)
                   AND (child:Token OR child:Contract))
               OR child:Function
               OR child:FeeTier
            MERGE (view)-[:INCLUDES]->(child)
            """
        ).consume()


def build_fixture_graph():
    """Create a small, logically isolated graph for security test scenarios."""
    with get_session() as session:
        session.run(
            """
            MERGE (root:FixtureNode:FixtureGraph {key:'fixture-root'})
            SET root.name='Deterministic DeFi Verification Fixtures'
            MERGE (chain:FixtureNode:FixtureChain {key:'fixture-chain-sepolia'})
            SET chain.name='Ethereum Sepolia', chain.chain_id=11155111
            MERGE (uni:FixtureNode:FixtureDeployment {key:'fixture-uniswap-sepolia'})
            SET uni.name='Uniswap V3 — Sepolia', uni.verified=true
            MERGE (aave:FixtureNode:FixtureDeployment {key:'fixture-aave-sepolia'})
            SET aave.name='Aave V3 — Sepolia', aave.verified=true
            MERGE (usdc:FixtureNode:FixtureToken {key:'fixture-usdc'})
            SET usdc.symbol='USDC', usdc.verified=true
            MERGE (weth:FixtureNode:FixtureToken {key:'fixture-weth'})
            SET weth.symbol='WETH', weth.verified=true
            MERGE (rug:FixtureNode:FixtureToken {key:'fixture-rug'})
            SET rug.symbol='RUG', rug.verified=false
            MERGE (valid:FixtureNode:FixturePool {key:'fixture-valid-pool'})
            SET valid.name='USDC/WETH valid pool', valid.verified=true
            MERGE (malicious:FixtureNode:FixturePool {key:'fixture-malicious-pool'})
            SET malicious.name='USDC/RUG untrusted-token pool', malicious.verified=true
            MERGE (fake:FixtureNode:FixtureDeployment {key:'fixture-fake-protocol'})
            SET fake.name='FakeSwap', fake.verified=false
            MERGE (reserve:FixtureNode:FixtureReserve {key:'fixture-usdc-reserve'})
            SET reserve.name='Aave USDC valid reserve', reserve.verified=true
            MERGE (supply:FixtureNode:FixtureAction {key:'fixture-action-supply'})
            SET supply.name='supply'
            MERGE (validSwap:FixtureNode:FixtureScenario {key:'fixture-scenario-valid-swap'})
            SET validSwap.name='Valid USDC/WETH swap', validSwap.expected='APPROVED'
            MERGE (rugSwap:FixtureNode:FixtureScenario {key:'fixture-scenario-rug-swap'})
            SET rugSwap.name='Pool contains untrusted token', rugSwap.expected='BLOCKED'
            MERGE (fakeSwap:FixtureNode:FixtureScenario {key:'fixture-scenario-fake-protocol'})
            SET fakeSwap.name='Unverified protocol', fakeSwap.expected='BLOCKED'
            MERGE (validSupply:FixtureNode:FixtureScenario {key:'fixture-scenario-valid-supply'})
            SET validSupply.name='Valid Aave USDC supply', validSupply.expected='APPROVED'
            MERGE (root)-[:INCLUDES]->(chain)
            MERGE (root)-[:INCLUDES]->(uni)
            MERGE (root)-[:INCLUDES]->(aave)
            MERGE (root)-[:INCLUDES]->(valid)
            MERGE (root)-[:INCLUDES]->(malicious)
            MERGE (root)-[:INCLUDES]->(fake)
            MERGE (root)-[:INCLUDES]->(usdc)
            MERGE (root)-[:INCLUDES]->(weth)
            MERGE (root)-[:INCLUDES]->(rug)
            MERGE (root)-[:INCLUDES]->(reserve)
            MERGE (root)-[:INCLUDES]->(supply)
            MERGE (root)-[:INCLUDES]->(validSwap)
            MERGE (root)-[:INCLUDES]->(rugSwap)
            MERGE (root)-[:INCLUDES]->(fakeSwap)
            MERGE (root)-[:INCLUDES]->(validSupply)
            MERGE (chain)-[:HOSTS]->(uni)
            MERGE (chain)-[:HOSTS]->(aave)
            MERGE (chain)-[:HOSTS]->(fake)
            MERGE (uni)-[:HAS_POOL]->(valid)
            MERGE (uni)-[:HAS_POOL]->(malicious)
            MERGE (valid)-[:TOKEN0]->(usdc)
            MERGE (valid)-[:TOKEN1]->(weth)
            MERGE (malicious)-[:TOKEN0]->(usdc)
            MERGE (malicious)-[:TOKEN1]->(rug)
            MERGE (aave)-[:HAS_RESERVE]->(reserve)
            MERGE (reserve)-[:UNDERLYING_ASSET]->(usdc)
            MERGE (reserve)-[:SUPPORTS_ACTION]->(supply)
            MERGE (validSwap)-[:EXPECTS_APPROVED]->(valid)
            MERGE (rugSwap)-[:EXPECTS_BLOCKED]->(malicious)
            MERGE (fakeSwap)-[:EXPECTS_BLOCKED]->(fake)
            MERGE (validSupply)-[:EXPECTS_APPROVED]->(reserve)
            """
        ).consume()


def v2_summary():
    with get_session() as session:
        nodes = session.run(
            """
            MATCH (n)
            WHERE n.graph_version=$version OR n:FixtureNode
            UNWIND labels(n) AS label
            RETURN label, count(*) AS count ORDER BY label
            """,
            version=GRAPH_VERSION,
        ).data()
        hierarchy = session.run(
            """
            MATCH (chain:Chain)-[:HOSTS]->(deployment:ProtocolDeployment)
            CALL (deployment) {
              OPTIONAL MATCH (deployment)-[rel:HAS_POOL]->(pool:Pool {active:true})
              WHERE rel.active=true
              RETURN count(DISTINCT pool) AS pools,
                     count(DISTINCT CASE WHEN pool.verification_eligible=true THEN pool END)
                       AS eligible_pools
            }
            CALL (deployment) {
              OPTIONAL MATCH (deployment)-[rel:HAS_RESERVE]->(reserve:Reserve {active:true})
              WHERE rel.active=true
              RETURN count(DISTINCT reserve) AS reserves
            }
            CALL (deployment) {
              OPTIONAL MATCH (deployment)-[:SUPPORTS_ASSET]->(token:Token {verified:true})
              RETURN count(DISTINCT token) AS assets
            }
            CALL (deployment) {
              OPTIONAL MATCH (deployment)-[:DISCOVERED_ASSET]->(token:Token)
              RETURN count(DISTINCT token) AS discovered_assets
            }
            CALL (deployment) {
              OPTIONAL MATCH (deployment)-[rel:DEPLOYED_CONTRACT]->
                             (:Contract)-[:EXPOSES_FUNCTION]->(fn:Function)
              WHERE rel.active=true
              RETURN count(DISTINCT fn) AS functions
            }
            RETURN chain.name AS chain, chain.chain_id AS chain_id,
                   deployment.name AS deployment,
                   pools, eligible_pools, reserves, assets, discovered_assets, functions,
                   deployment.pool_discovery_complete AS pool_discovery_complete,
                   deployment.pool_discovery_mode AS pool_discovery_mode
            ORDER BY chain_id, deployment
            """
        ).data()
    return {"nodes": nodes, "hierarchy": hierarchy}


def sync_v2():
    ensure_v2_schema()
    removed_orphans = _cleanup_orphan_asset_support_nodes()
    feed = fetch_json(UNISWAP_DEPLOYMENTS_URL)
    result = {
        "aave": [], "uniswap": [],
        "migration": {"removed_orphan_asset_support_nodes": removed_orphans},
    }
    for chain_id in (1, 11155111):
        result["aave"].append(load_aave_v2(chain_id))
        result["uniswap"].append(load_uniswap_v2(chain_id, feed=feed))
    build_demo_view()
    build_fixture_graph()
    result["summary"] = v2_summary()
    return result


if __name__ == "__main__":
    print(json.dumps(sync_v2(), indent=2))
