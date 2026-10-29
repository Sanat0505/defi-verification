# Tables derived from the frozen 600-prompt run

| Category | Prompts | Exact status | Joint match | Errors |
| --- | --- | --- | --- | --- |
| Valid Uniswap | 100 | 82 | 82 | 0 |
| Valid Aave | 100 | 99 | 99 | 1 |
| Invalid relationships | 100 | 100 | 100 | 0 |
| Unknown / unsupported | 100 | 99 | 99 | 1 |
| Incomplete / ambiguous | 100 | 57 | 52 | 1 |
| Invalid parameters / conditions | 100 | 97 | 97 | 1 |

| Primary diagnosis | Prompts |
| --- | --- |
| Missing information treated as unsupported | 38 |
| Slippage wording blocked by text guard | 18 |
| Clarification fields lost | 5 |
| Ambiguous amount emitted as prose | 4 |
| Provider quota errors | 4 |
| Intermediate token omitted: false approval | 1 |
| Negative amount: wrong disposition | 1 |

| Pair outcome | Scenario instances |
| --- | --- |
| Both exact | 250 |
| Only A exact | 24 |
| Only B exact | 10 |
| Neither exact | 16 |

| Unknown / unsupported subtype | Prompts | Exact status | Errors |
| --- | --- | --- | --- |
| asset_absent_from_saved_reserves | 38 | 37 | 1 |
| native_asset_boundary | 2 | 2 | 0 |
| unsupported_action | 20 | 20 | 0 |
| unsupported_network | 20 | 20 | 0 |
| unsupported_protocol | 20 | 20 | 0 |
