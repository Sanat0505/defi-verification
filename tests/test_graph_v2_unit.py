"""Pure unit tests for graph-v2 parsing and trust-boundary helpers."""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.graph_v2 import PROTOCOL_FUNCTIONS, _filter_trusted_pools
from db.loaders.aave_loader import _parse_address_book


ADDRESS_BOOK_SAMPLE = """
library AaveV3Example {
  IPool internal constant POOL = IPool(0x1111111111111111111111111111111111111111);
  address internal constant ACL_MANAGER = 0x2222222222222222222222222222222222222222;
  address internal constant EXTRA_STEWARD = 0x3333333333333333333333333333333333333333;
}
library AaveV3ExampleAssets {
  address internal constant wstETH_UNDERLYING = 0x4444444444444444444444444444444444444444;
  uint8 internal constant wstETH_DECIMALS = 18;
  address internal constant wstETH_A_TOKEN = 0x5555555555555555555555555555555555555555;
  address internal constant wstETH_V_TOKEN = 0x6666666666666666666666666666666666666666;
  address internal constant wstETH_ORACLE = 0x7777777777777777777777777777777777777777;
  address internal constant wstETH_INTEREST_RATE_STRATEGY = 0x8888888888888888888888888888888888888888;
}
"""


def test_address_book_keeps_mixed_case_assets_and_all_core_contracts():
    contracts, assets = _parse_address_book(ADDRESS_BOOK_SAMPLE)
    assert {item["name"] for item in contracts} == {
        "POOL", "ACL_MANAGER", "EXTRA_STEWARD"
    }
    assert assets == [{
        "symbol": "wstETH",
        "underlying": "0x4444444444444444444444444444444444444444",
        "a_token": "0x5555555555555555555555555555555555555555",
        "v_token": "0x6666666666666666666666666666666666666666",
        "oracle": "0x7777777777777777777777777777777777777777",
        "interest_rate_strategy": "0x8888888888888888888888888888888888888888",
        "decimals": 18,
    }]


def test_uniswap_filter_requires_both_assets_to_be_trusted():
    trusted = {"0xaaa", "0xbbb"}
    pools = [
        {"address": "0x1", "token0": "0xaaa", "token1": "0xbbb"},
        {"address": "0x2", "token0": "0xaaa", "token1": "0xccc"},
    ]
    assert [pool["address"] for pool in _filter_trusted_pools(pools, trusted)] == ["0x1"]


def test_every_execution_function_has_a_selector():
    execution_functions = [
        fn for functions in PROTOCOL_FUNCTIONS.values() for fn in functions
        if fn["purpose"] == "execute"
    ]
    assert execution_functions
    assert all(fn["selector"].startswith("0x") and len(fn["selector"]) == 10
               for fn in execution_functions)


if __name__ == "__main__":
    test_address_book_keeps_mixed_case_assets_and_all_core_contracts()
    test_uniswap_filter_requires_both_assets_to_be_trusted()
    test_every_execution_function_has_a_selector()
    print("graph-v2 unit checks passed")
