"""Parse Uniswap V3 deployment roles and PoolCreated events for db.graph_v2."""

from db.loaders.common import normalize_address


POOL_CREATED_TOPIC = (
    "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
)

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
