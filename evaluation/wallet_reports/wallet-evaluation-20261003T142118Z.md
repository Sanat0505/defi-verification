# Wallet evaluation summary

- Timestamp (UTC): 2026-10-03T14:21:18.435483+00:00
- Dataset version: `1.0.0`
- Implemented scenarios: 28
- Implemented scenarios passed: 28
- Implemented conformance: 100.00%
- Explicitly documented gaps: 3
- Transactions broadcast: 0

## Scenario results

| ID | Category | Expected | Actual | Reason code | Result |
|---|---|---|---|---|---|
| W01 | destination_policy | PASS | PASS | `DESTINATION_ALLOWED` | PASS |
| W02 | destination_policy | BLOCKED | BLOCKED | `DESTINATION_NOT_ALLOWED` | PASS |
| W03 | destination_policy | BLOCKED | BLOCKED | `POLICY_EXPIRED` | PASS |
| W05 | destination_policy | BLOCKED | BLOCKED | `NATIVE_VALUE_LIMIT_EXCEEDED` | PASS |
| H01 | approved_handover | BLOCKED | BLOCKED | `REQUEST_SCHEMA_REJECTED` | PASS |
| H02_REPLAY | approved_handover | BLOCKED | BLOCKED | `VERIFICATION_REUSED` | PASS |
| H02_EXPIRED | approved_handover | BLOCKED | BLOCKED | `VERIFICATION_EXPIRED` | PASS |
| P01_AAVE | transaction_data | BLOCKED | BLOCKED | `INVALID_EXECUTION_DATA` | PASS |
| P01_SWAP | transaction_data | BLOCKED | BLOCKED | `INVALID_EXECUTION_DATA` | PASS |
| P02_AAVE_VALID | transaction_data | PASS | PASS | `EXECUTION_DATA_VALID` | PASS |
| P07_SLIPPAGE | transaction_data | BLOCKED | BLOCKED | `INVALID_EXECUTION_DATA` | PASS |
| P03_SWAP | funding_preflight | BLOCKED | BLOCKED | `INSUFFICIENT_TOKEN_BALANCE` | PASS |
| P03_AAVE_SUPPLY | funding_preflight | BLOCKED | BLOCKED | `INSUFFICIENT_TOKEN_BALANCE` | PASS |
| P04_SWAP | funding_preflight | PASS | PASS | `ALLOWANCE_APPROVAL_REQUIRED` | PASS |
| P04_AAVE_REPAY | funding_preflight | PASS | PASS | `ALLOWANCE_APPROVAL_REQUIRED` | PASS |
| P05 | funding_preflight | PASS | PASS | `PREFLIGHT_READY` | PASS |
| A01 | api_execution_gate | BLOCKED | BLOCKED | `APPROVAL_MISMATCH` | PASS |
| A02 | api_execution_gate | BLOCKED | BLOCKED | `DESTINATION_NOT_ALLOWED` | PASS |
| P10 | simulation_and_submission | BLOCKED | BLOCKED | `SIMULATION_REVERTED` | PASS |
| P06 | simulation_and_submission | BLOCKED | BLOCKED | `NO_USABLE_QUOTE` | PASS |
| P08 | simulation_and_submission | BLOCKED | BLOCKED | `OUTPUT_TOO_SMALL` | PASS |
| AAVE_WITHDRAW_POSITION | aave_protocol_state | BLOCKED | BLOCKED | `AAVE_POSITION_UNAVAILABLE` | PASS |
| AAVE_BORROW_COLLATERAL | aave_protocol_state | BLOCKED | BLOCKED | `COLLATERAL_INSUFFICIENT` | PASS |
| AAVE_REPAY_DEBT | aave_protocol_state | BLOCKED | BLOCKED | `AAVE_DEBT_UNAVAILABLE` | PASS |
| E01 | simulation_and_submission | BLOCKED | BLOCKED | `SPONSORSHIP_DENIED` | PASS |
| E02 | simulation_and_submission | BLOCKED | BLOCKED | `INVALID_SIGNATURE` | PASS |
| E04 | simulation_and_submission | BLOCKED | BLOCKED | `EXECUTION_REVERTED` | PASS |
| E05 | simulation_and_submission | EXECUTED | EXECUTED | `TRANSACTION_SUBMITTED` | PASS |
| W04 | documented_gap | NOT_IMPLEMENTED | NOT_IMPLEMENTED | `SIGNER_BINDING_NOT_IMPLEMENTED` | PASS |
| W06 | documented_gap | NOT_IMPLEMENTED | NOT_IMPLEMENTED | `TOKEN_BUDGET_NOT_IMPLEMENTED` | PASS |
| E03 | documented_gap | NOT_IMPLEMENTED | NOT_IMPLEMENTED | `RECEIPT_RECONCILIATION_NOT_IMPLEMENTED` | PASS |

## Interpretation

`NOT_IMPLEMENTED` rows are declared scope gaps and are excluded from the implemented-conformance denominator. All RPC, bundler, paymaster, simulation, and success responses are controlled fixtures. The runner exercises the real local JavaScript destination and transaction-data policy but never broadcasts.
