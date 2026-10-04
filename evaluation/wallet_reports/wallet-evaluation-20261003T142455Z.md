# Wallet evaluation summary

- Timestamp (UTC): 2026-10-03T14:24:55.286512+00:00
- Dataset version: `1.0.0`
- Implemented scenarios: 1
- Implemented scenarios passed: 1
- Implemented conformance: 100.00%
- Explicitly documented gaps: 0
- Transactions broadcast: 0

## Scenario results

| ID | Category | Expected | Actual | Reason code | Result |
|---|---|---|---|---|---|
| W02 | destination_policy | BLOCKED | BLOCKED | `DESTINATION_NOT_ALLOWED` | PASS |

## Interpretation

`NOT_IMPLEMENTED` rows are declared scope gaps and are excluded from the implemented-conformance denominator. All RPC, bundler, paymaster, simulation, and success responses are controlled fixtures. The runner exercises the real local JavaScript destination and transaction-data policy but never broadcasts.
