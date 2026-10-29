# Retrospective error review: all 71 joint mismatches

Assistant analysis of frozen records, not human adjudication. Original labels and results are unchanged. A missing normalized candidate after validation is not by itself evidence that every field was extracted incorrectly.

## BAL600-007-B

Please convert an exact input of 37.0625 AAVE to WBTC through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 0.01 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "AAVE",
  "token_out": "WBTC",
  "amount": "37.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "0.01",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-008-B

Please convert an exact input of 38.0625 LINK to USDT through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 0.01 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "LINK",
  "token_out": "USDT",
  "amount": "38.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "0.01",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-009-B

Please convert an exact input of 39.0625 USDC to WETH through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 0.01 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "USDC",
  "token_out": "WETH",
  "amount": "39.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "0.01",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-010-B

Please convert an exact input of 40.0625 USDT to LINK through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 0.01 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "USDT",
  "token_out": "LINK",
  "amount": "40.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "0.01",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-011-B

Please convert an exact input of 41.0625 WBTC to AAVE through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 0.01 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "WBTC",
  "token_out": "AAVE",
  "amount": "41.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "0.01",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-012-B

Please convert an exact input of 42.0625 WETH to USDC through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 0.01 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "WETH",
  "token_out": "USDC",
  "amount": "42.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "0.01",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-019-B

Please convert an exact input of 49.0625 AAVE to WBTC through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 0.5 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "AAVE",
  "token_out": "WBTC",
  "amount": "49.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "0.5",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-020-B

Please convert an exact input of 50.0625 LINK to USDT through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 0.5 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "LINK",
  "token_out": "USDT",
  "amount": "50.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "0.5",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-021-B

Please convert an exact input of 51.0625 USDC to WETH through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 0.5 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "USDC",
  "token_out": "WETH",
  "amount": "51.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "0.5",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-022-B

Please convert an exact input of 52.0625 USDT to LINK through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 0.5 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "USDT",
  "token_out": "LINK",
  "amount": "52.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "0.5",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-023-B

Please convert an exact input of 53.0625 WBTC to AAVE through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 0.5 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "WBTC",
  "token_out": "AAVE",
  "amount": "53.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "0.5",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-024-B

Please convert an exact input of 54.0625 WETH to USDC through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 0.5 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "WETH",
  "token_out": "USDC",
  "amount": "54.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "0.5",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-031-B

Please convert an exact input of 61.0625 AAVE to WBTC through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 5 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "AAVE",
  "token_out": "WBTC",
  "amount": "61.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "5",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-032-B

Please convert an exact input of 62.0625 LINK to USDT through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 5 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "LINK",
  "token_out": "USDT",
  "amount": "62.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "5",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-033-B

Please convert an exact input of 63.0625 USDC to WETH through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 5 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "USDC",
  "token_out": "WETH",
  "amount": "63.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "5",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-034-B

Please convert an exact input of 64.0625 USDT to LINK through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 5 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "USDT",
  "token_out": "LINK",
  "amount": "64.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "5",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-035-B

Please convert an exact input of 65.0625 WBTC to AAVE through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 5 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "WBTC",
  "token_out": "AAVE",
  "amount": "65.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "5",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-036-B

Please convert an exact input of 66.0625 WETH to USDC through Uniswap V3 on Ethereum Sepolia. Slippage must not exceed 5 percent.

Reference: **APPROVED**. Observed: **UNSUPPORTED**. Diagnosis: `slippage_guard`.

Raw extraction preserves the numeric slippage; the deterministic text guard flags unrecognized wording before graph verification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "WETH",
  "token_out": "USDC",
  "amount": "66.0625",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": {
    "value": "5",
    "unit": "percent"
  },
  "unhandled_constraints": []
}
```

## BAL600-090-B

Pay back 82.03125 AAVE of the loan I have on Aave V3 on Ethereum Sepolia.

Reference: **APPROVED**. Observed: **ERROR**. Diagnosis: `provider_quota`.

No successful model response; recorded llm_unavailable quota error. Not a semantic rejection.

Raw extraction:
```json
null
```

## BAL600-183-B

I want to deposit 135.125 SOL into the Ethereum Sepolia Aave V3 market.

Reference: **REJECTED**. Observed: **ERROR**. Diagnosis: `provider_quota`.

No successful model response; recorded llm_unavailable quota error. Not a semantic rejection.

Raw extraction:
```json
null
```

## BAL600-201-A

On Ethereum Sepolia, I want to swap an unspecified amount of USDC into WETH using Uniswap V3. The amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "USDC",
  "token_out": "WETH",
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "unspecified amount"
  ]
}
```

## BAL600-202-A

On Ethereum Sepolia, I want to swap 37.42 an unspecified asset into WETH using Uniswap V3. The input asset is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": null,
  "token_out": "WETH",
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "input asset unspecified"
  ]
}
```

## BAL600-202-B

Using Uniswap V3 on Ethereum Sepolia, my request is to swap 37.42 an unspecified asset into WETH; the input asset is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": null,
  "token_out": "WETH",
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "input asset is not specified"
  ]
}
```

## BAL600-205-A

On Ethereum Sepolia, I want to swap an unspecified amount of USDC into WETH using Uniswap V3. The amount is undecided between 37.42 and 52.84.

Reference: **NEEDS_CLARIFICATION**. Observed: **REJECTED**. Diagnosis: `ambiguous_amount_literal`.

Raw amount contains prose or an unresolved range instead of null; positive-decimal validation rejects it.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "USDC",
  "token_out": "WETH",
  "amount": "between 37.42 and 52.84",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": []
}
```

## BAL600-205-B

Using Uniswap V3 on Ethereum Sepolia, my request is to swap an unspecified amount of USDC into WETH; the amount is undecided between 37.42 and 52.84.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "USDC",
  "token_out": "WETH",
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "amount is undecided between 37.42 and 52.84"
  ]
}
```

## BAL600-206-A

On Ethereum Sepolia, I want to swap 37.42 an unspecified asset into WETH using Uniswap V3. The input asset is undecided between usdc and link.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": null,
  "token_out": "WETH",
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "input asset undecided between usdc and link"
  ]
}
```

## BAL600-206-B

Using Uniswap V3 on Ethereum Sepolia, my request is to swap 37.42 an unspecified asset into WETH; the input asset is undecided between USDC and LINK.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": null,
  "token_out": "WETH",
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "input asset undecided between USDC and LINK"
  ]
}
```

## BAL600-208-B

Using a protocol I have not selected on Ethereum Sepolia, my request is to swap an unspecified amount of USDC into WETH; the protocol is undecided; do not choose it for me; the amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": null,
  "token_in": "USDC",
  "token_out": "WETH",
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "protocol undecided"
  ]
}
```

## BAL600-210-A

On Ethereum Sepolia, I want to swap 37.42 USDC into an unspecified output asset using Uniswap V3. The output asset is undecided between weth and link.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "USDC",
  "token_out": null,
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "output asset undecided between weth and link"
  ]
}
```

## BAL600-215-A

On Ethereum Sepolia, I want to supply an unspecified amount of DAI using Aave V3. The amount is undecided between 37.42 and 52.84.

Reference: **NEEDS_CLARIFICATION**. Observed: **REJECTED**. Diagnosis: `ambiguous_amount_literal`.

Raw amount contains prose or an unresolved range instead of null; positive-decimal validation rejects it.

Raw extraction:
```json
{
  "action": "supply",
  "protocol": "Aave V3",
  "token_in": "DAI",
  "token_out": null,
  "amount": "between 37.42 and 52.84",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": []
}
```

## BAL600-215-B

Using Aave V3 on Ethereum Sepolia, my request is to supply an unspecified amount of DAI; the amount is undecided between 37.42 and 52.84.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "supply",
  "protocol": "Aave V3",
  "token_in": "DAI",
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "amount between 37.42 and 52.84"
  ]
}
```

## BAL600-216-A

On Ethereum Sepolia, I want to supply 37.42 an unspecified asset using Aave V3. The input asset is undecided between dai and link.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "supply",
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "input asset undecided between dai and link"
  ]
}
```

## BAL600-216-B

Using Aave V3 on Ethereum Sepolia, my request is to supply 37.42 an unspecified asset; the input asset is undecided between DAI and LINK.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "supply",
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "unspecified asset",
    "input asset undecided between DAI and LINK"
  ]
}
```

## BAL600-218-B

Using a protocol I have not selected on Ethereum Sepolia, my request is to supply an unspecified amount of DAI; the protocol is undecided; do not choose it for me; the amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "supply",
  "protocol": null,
  "token_in": "DAI",
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "protocol undecided"
  ]
}
```

## BAL600-219-B

Using Aave V3 on Ethereum Sepolia, my request is to perform an operation an unspecified amount of DAI; I have not decided which operation to request; the amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **NEEDS_CLARIFICATION**. Diagnosis: `clarification_field_loss`.

Clarification status matches, but explicit fields are lost and the requested missing-field set is too broad.

Raw extraction:
```json
{
  "action": null,
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": []
}
```

## BAL600-220-A

On Ethereum Sepolia, I want to perform an operation 37.42 DAI using a protocol I have not selected. I have not decided which operation to request; the protocol is undecided; do not choose it for me.

Reference: **NEEDS_CLARIFICATION**. Observed: **NEEDS_CLARIFICATION**. Diagnosis: `clarification_field_loss`.

Clarification status matches, but explicit fields are lost and the requested missing-field set is too broad.

Raw extraction:
```json
{
  "action": null,
  "protocol": null,
  "token_in": null,
  "token_out": null,
  "amount": null,
  "chain": null,
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": []
}
```

## BAL600-221-A

On Ethereum Sepolia, I want to withdraw an unspecified amount of GHO using Aave V3. The amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "withdraw",
  "protocol": "Aave V3",
  "token_in": "GHO",
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "unspecified amount"
  ]
}
```

## BAL600-223-A

On Ethereum Sepolia, I want to withdraw 37.42 GHO using a protocol I have not selected. The protocol is undecided; do not choose it for me.

Reference: **NEEDS_CLARIFICATION**. Observed: **ERROR**. Diagnosis: `provider_quota`.

No successful model response; recorded llm_unavailable quota error. Not a semantic rejection.

Raw extraction:
```json
null
```

## BAL600-223-B

Using a protocol I have not selected on Ethereum Sepolia, my request is to withdraw 37.42 GHO; the protocol is undecided; do not choose it for me.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "withdraw",
  "protocol": null,
  "token_in": "GHO",
  "token_out": null,
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "protocol undecided"
  ]
}
```

## BAL600-225-A

On Ethereum Sepolia, I want to withdraw an unspecified amount of GHO using Aave V3. The amount is undecided between 37.42 and 52.84.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "withdraw",
  "protocol": "Aave V3",
  "token_in": "GHO",
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "amount undecided between 37.42 and 52.84"
  ]
}
```

## BAL600-225-B

Using Aave V3 on Ethereum Sepolia, my request is to withdraw an unspecified amount of GHO; the amount is undecided between 37.42 and 52.84.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "withdraw",
  "protocol": "Aave V3",
  "token_in": "GHO",
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "amount between 37.42 and 52.84"
  ]
}
```

## BAL600-226-A

On Ethereum Sepolia, I want to withdraw 37.42 an unspecified asset using Aave V3. The input asset is undecided between gho and link.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "withdraw",
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "unspecified asset",
    "input asset undecided between gho and link"
  ]
}
```

## BAL600-226-B

Using Aave V3 on Ethereum Sepolia, my request is to withdraw 37.42 an unspecified asset; the input asset is undecided between GHO and LINK.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "withdraw",
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "input asset is undecided between GHO and LINK"
  ]
}
```

## BAL600-227-A

On Ethereum Sepolia, I want to withdraw an unspecified amount of an unspecified asset using Aave V3. The amount is not specified; the input asset is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "withdraw",
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "unspecified amount",
    "unspecified asset"
  ]
}
```

## BAL600-228-A

On Ethereum Sepolia, I want to withdraw an unspecified amount of GHO using a protocol I have not selected. The protocol is undecided; do not choose it for me; the amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "withdraw",
  "protocol": null,
  "token_in": "GHO",
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "protocol undecided"
  ]
}
```

## BAL600-228-B

Using a protocol I have not selected on Ethereum Sepolia, my request is to withdraw an unspecified amount of GHO; the protocol is undecided; do not choose it for me; the amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "withdraw",
  "protocol": null,
  "token_in": "GHO",
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "protocol is undecided"
  ]
}
```

## BAL600-229-A

On Ethereum Sepolia, I want to perform an operation an unspecified amount of GHO using Aave V3. I have not decided which operation to request; the amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **REJECTED**. Diagnosis: `ambiguous_amount_literal`.

Raw amount contains prose or an unresolved range instead of null; positive-decimal validation rejects it.

Raw extraction:
```json
{
  "action": null,
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": "unspecified amount of GHO",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": []
}
```

## BAL600-229-B

Using Aave V3 on Ethereum Sepolia, my request is to perform an operation an unspecified amount of GHO; I have not decided which operation to request; the amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **REJECTED**. Diagnosis: `ambiguous_amount_literal`.

Raw amount contains prose or an unresolved range instead of null; positive-decimal validation rejects it.

Raw extraction:
```json
{
  "action": null,
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": "unspecified amount of GHO",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": []
}
```

## BAL600-230-B

Using a protocol I have not selected on Ethereum Sepolia, my request is to perform an operation 37.42 GHO; I have not decided which operation to request; the protocol is undecided; do not choose it for me.

Reference: **NEEDS_CLARIFICATION**. Observed: **NEEDS_CLARIFICATION**. Diagnosis: `clarification_field_loss`.

Clarification status matches, but explicit fields are lost and the requested missing-field set is too broad.

Raw extraction:
```json
{
  "action": null,
  "protocol": null,
  "token_in": null,
  "token_out": null,
  "amount": null,
  "chain": null,
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": []
}
```

## BAL600-233-B

Using a protocol I have not selected on Ethereum Sepolia, my request is to borrow 37.42 WBTC; the protocol is undecided; do not choose it for me.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "borrow",
  "protocol": null,
  "token_in": "WBTC",
  "token_out": null,
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "protocol undecided"
  ]
}
```

## BAL600-234-B

Using Aave V3 on Ethereum Sepolia, my request is to perform an operation 37.42 WBTC; I have not decided which operation to request.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": null,
  "protocol": "Aave V3",
  "token_in": "WBTC",
  "token_out": null,
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "operation not specified"
  ]
}
```

## BAL600-235-A

On Ethereum Sepolia, I want to borrow an unspecified amount of WBTC using Aave V3. The amount is undecided between 37.42 and 52.84.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "borrow",
  "protocol": "Aave V3",
  "token_in": "WBTC",
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "amount between 37.42 and 52.84"
  ]
}
```

## BAL600-235-B

Using Aave V3 on Ethereum Sepolia, my request is to borrow an unspecified amount of WBTC; the amount is undecided between 37.42 and 52.84.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "borrow",
  "protocol": "Aave V3",
  "token_in": "WBTC",
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "amount between 37.42 and 52.84"
  ]
}
```

## BAL600-236-A

On Ethereum Sepolia, I want to borrow 37.42 an unspecified asset using Aave V3. The input asset is undecided between wbtc and link.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "borrow",
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "input asset undecided between wbtc and link"
  ]
}
```

## BAL600-236-B

Using Aave V3 on Ethereum Sepolia, my request is to borrow 37.42 an unspecified asset; the input asset is undecided between WBTC and LINK.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "borrow",
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "input asset undecided between WBTC and LINK"
  ]
}
```

## BAL600-237-A

On Ethereum Sepolia, I want to borrow an unspecified amount of an unspecified asset using Aave V3. The amount is not specified; the input asset is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "borrow",
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "unspecified amount",
    "unspecified asset"
  ]
}
```

## BAL600-238-A

On Ethereum Sepolia, I want to borrow an unspecified amount of WBTC using a protocol I have not selected. The protocol is undecided; do not choose it for me; the amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "borrow",
  "protocol": null,
  "token_in": "WBTC",
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "protocol undecided",
    "amount unspecified"
  ]
}
```

## BAL600-238-B

Using a protocol I have not selected on Ethereum Sepolia, my request is to borrow an unspecified amount of WBTC; the protocol is undecided; do not choose it for me; the amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **NEEDS_CLARIFICATION**. Diagnosis: `clarification_field_loss`.

Clarification status matches, but explicit fields are lost and the requested missing-field set is too broad.

Raw extraction:
```json
{
  "action": null,
  "protocol": null,
  "token_in": null,
  "token_out": null,
  "amount": null,
  "chain": null,
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": []
}
```

## BAL600-239-A

On Ethereum Sepolia, I want to perform an operation an unspecified amount of WBTC using Aave V3. I have not decided which operation to request; the amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": null,
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "unspecified amount",
    "unspecified operation"
  ]
}
```

## BAL600-239-B

Using Aave V3 on Ethereum Sepolia, my request is to perform an operation an unspecified amount of WBTC; I have not decided which operation to request; the amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": null,
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "unspecified amount of WBTC",
    "operation not decided"
  ]
}
```

## BAL600-240-B

Using a protocol I have not selected on Ethereum Sepolia, my request is to perform an operation 37.42 WBTC; I have not decided which operation to request; the protocol is undecided; do not choose it for me.

Reference: **NEEDS_CLARIFICATION**. Observed: **NEEDS_CLARIFICATION**. Diagnosis: `clarification_field_loss`.

Clarification status matches, but explicit fields are lost and the requested missing-field set is too broad.

Raw extraction:
```json
{
  "action": null,
  "protocol": null,
  "token_in": null,
  "token_out": null,
  "amount": null,
  "chain": null,
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": []
}
```

## BAL600-245-A

On Ethereum Sepolia, I want to repay an unspecified amount of USDT using Aave V3. The amount is undecided between 37.42 and 52.84.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "repay",
  "protocol": "Aave V3",
  "token_in": "USDT",
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "amount between 37.42 and 52.84"
  ]
}
```

## BAL600-245-B

Using Aave V3 on Ethereum Sepolia, my request is to repay an unspecified amount of USDT; the amount is undecided between 37.42 and 52.84.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "repay",
  "protocol": "Aave V3",
  "token_in": "USDT",
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "amount between 37.42 and 52.84"
  ]
}
```

## BAL600-246-A

On Ethereum Sepolia, I want to repay 37.42 an unspecified asset using Aave V3. The input asset is undecided between usdt and link.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "repay",
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "input asset undecided between usdt and link"
  ]
}
```

## BAL600-246-B

Using Aave V3 on Ethereum Sepolia, my request is to repay 37.42 an unspecified asset; the input asset is undecided between USDT and LINK.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "repay",
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": "37.42",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "unspecified asset",
    "input asset undecided between USDT and LINK"
  ]
}
```

## BAL600-247-A

On Ethereum Sepolia, I want to repay an unspecified amount of an unspecified asset using Aave V3. The amount is not specified; the input asset is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "repay",
  "protocol": "Aave V3",
  "token_in": null,
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "unspecified amount",
    "unspecified asset"
  ]
}
```

## BAL600-248-A

On Ethereum Sepolia, I want to repay an unspecified amount of USDT using a protocol I have not selected. The protocol is undecided; do not choose it for me; the amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "repay",
  "protocol": null,
  "token_in": "USDT",
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "unspecified amount",
    "protocol undecided"
  ]
}
```

## BAL600-248-B

Using a protocol I have not selected on Ethereum Sepolia, my request is to repay an unspecified amount of USDT; the protocol is undecided; do not choose it for me; the amount is not specified.

Reference: **NEEDS_CLARIFICATION**. Observed: **UNSUPPORTED**. Diagnosis: `clarification_as_constraint`.

Raw unhandled_constraints includes missing or ambiguous information; constraint validation returns UNSUPPORTED before clarification.

Raw extraction:
```json
{
  "action": "repay",
  "protocol": null,
  "token_in": "USDT",
  "token_out": null,
  "amount": null,
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "protocol undecided",
    "amount not specified"
  ]
}
```

## BAL600-254-A

Please supply exactly -3.125 USDC using Aave V3 on Ethereum Sepolia.

Reference: **REJECTED**. Observed: **UNSUPPORTED**. Diagnosis: `negative_amount_priority`.

Raw negative amount is also labelled an unhandled constraint; UNSUPPORTED takes precedence over the reference REJECTED.

Raw extraction:
```json
{
  "action": "supply",
  "protocol": "Aave V3",
  "token_in": "USDC",
  "token_out": null,
  "amount": "-3.125",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": [
    "negative amount"
  ]
}
```

## BAL600-275-A

On Ethereum Sepolia, use Uniswap V3 to swap an input of 23.8125 USDC for WETH; route through USDT as an intermediate token.

Reference: **UNSUPPORTED**. Observed: **APPROVED**. Diagnosis: `omitted_intermediate_token`.

Raw extraction omits the required intermediate token. The direct swap path is verified for the reduced intent.

Raw extraction:
```json
{
  "action": "swap",
  "protocol": "Uniswap V3",
  "token_in": "USDC",
  "token_out": "WETH",
  "amount": "23.8125",
  "chain": "Ethereum Sepolia",
  "unsupported_action": null,
  "slippage": null,
  "unhandled_constraints": []
}
```

## BAL600-288-A

On Ethereum Sepolia, use Uniswap V3 to swap an input of 23.8125 USDC for WETH; set the transaction deadline to Unix timestamp 1793000000.

Reference: **UNSUPPORTED**. Observed: **ERROR**. Diagnosis: `provider_quota`.

No successful model response; recorded llm_unavailable quota error. Not a semantic rejection.

Raw extraction:
```json
null
```
