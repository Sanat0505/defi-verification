"""Parse Aave V3 address-book contracts and reserve metadata for db.graph_v2."""

import re

from source.db.loaders.common import normalize_address


CORE_ROLES = {
    "POOL_ADDRESSES_PROVIDER": "addresses_provider",
    "POOL": "pool",
    "POOL_CONFIGURATOR": "pool_configurator",
    "ORACLE": "oracle",
    "ACL_MANAGER": "acl_manager",
    "AAVE_PROTOCOL_DATA_PROVIDER": "protocol_data_provider",
    "UI_POOL_DATA_PROVIDER": "ui_pool_data_provider",
    "WETH_GATEWAY": "weth_gateway",
}

ASSET_PATTERN = re.compile(
    r"address\s+internal\s+constant\s+([A-Za-z0-9_]+?)_"
    r"(INTEREST_RATE_STRATEGY|STATIC_A_TOKEN|UNDERLYING|A_TOKEN|V_TOKEN|S_TOKEN|ORACLE)\s*=\s*"
    r"(0x[a-fA-F0-9]{40})\s*;",
    re.MULTILINE,
)
DECIMALS_PATTERN = re.compile(
    r"uint8\s+internal\s+constant\s+([A-Za-z0-9_]+)_DECIMALS\s*=\s*(\d+)\s*;"
)
CORE_ADDRESS_PATTERN = re.compile(
    r"(?:address|I[A-Za-z0-9_]*)\s+internal\s+constant\s+"
    r"([A-Z][A-Z0-9_]*)\s*=\s*"
    r"(?:[A-Za-z0-9_]+\s*\(\s*)?"
    r"(0x[a-fA-F0-9]{40})\s*\)?\s*;",
    re.MULTILINE,
)


def _parse_address_book(source: str):
    match = re.search(r"library\s+AaveV3[A-Za-z0-9]+Assets\s*\{", source)
    if not match:
        raise ValueError("Aave V3 assets library was not found in address book")
    core_source = source[:match.start()]
    assets_source = source[match.end():]
    core = [
        {
            "name": constant,
            "role": CORE_ROLES.get(constant, constant.lower()),
            "address": normalize_address(address),
        }
        for constant, address in CORE_ADDRESS_PATTERN.findall(core_source)
    ]

    decimals = {symbol: int(value) for symbol, value in DECIMALS_PATTERN.findall(assets_source)}
    assets = {}
    for symbol, kind, address in ASSET_PATTERN.findall(assets_source):
        asset = assets.setdefault(symbol, {"symbol": symbol})
        asset[kind.lower()] = normalize_address(address)
    for symbol, asset in assets.items():
        asset["decimals"] = decimals.get(symbol)
        if "underlying" not in asset:
            raise ValueError(f"Aave address book has no underlying address for {symbol}")
    return core, list(assets.values())
