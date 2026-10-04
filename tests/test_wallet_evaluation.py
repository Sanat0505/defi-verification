import asyncio
import json
from pathlib import Path

from evaluation import wallet_runner


DATASET = Path("evaluation/datasets/wallet_cases.json")


def test_wallet_dataset_has_unique_scenario_ids_and_declared_expectations():
    cases = json.loads(DATASET.read_text(encoding="utf-8"))["cases"]
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))
    assert all(case.get("expected_outcome") for case in cases)
    assert all(case.get("expected_reason_code") for case in cases)


def test_wallet_metrics_exclude_documented_gaps_from_conformance():
    records = [
        {
            "id": "implemented",
            "category": "policy",
            "implemented": True,
            "passed": True,
            "transaction_broadcast": False,
            "latency_ms": 2,
        },
        {
            "id": "gap",
            "category": "documented_gap",
            "implemented": False,
            "passed": True,
            "transaction_broadcast": False,
            "latency_ms": 0,
        },
    ]
    metrics = wallet_runner.calculate_wallet_metrics(records)
    assert metrics["implemented_conformance"] == 1
    assert metrics["implemented_scenarios"] == 1
    assert metrics["documented_gaps"] == 1
    assert metrics["transactions_broadcast"] == 0


def test_policy_case_uses_wallet_result_without_broadcast(monkeypatch, tmp_path):
    monkeypatch.setattr(wallet_runner.erc4337, "evaluate_policy", lambda case: {
        "success": True,
        "allowed": False,
        "reason_code": "INSUFFICIENT_TOKEN_BALANCE",
    })
    record = asyncio.run(wallet_runner.run_case({
        "id": "P03",
        "category": "funding_preflight",
        "mode": "wallet_policy",
        "input": {"kind": "funding"},
        "expected_outcome": "BLOCKED",
        "expected_reason_code": "INSUFFICIENT_TOKEN_BALANCE",
    }, tmp_path / "whitelist.json"))
    assert record["passed"] is True
    assert record["transaction_broadcast"] is False


def test_capability_replay_and_expiry_are_classified(tmp_path):
    base = {
        "category": "approved_handover",
        "expected_outcome": "BLOCKED",
    }
    replay = asyncio.run(wallet_runner.run_case({
        **base,
        "id": "replay",
        "mode": "capability_replay",
        "expected_reason_code": "VERIFICATION_REUSED",
    }, tmp_path / "whitelist.json"))
    expired = asyncio.run(wallet_runner.run_case({
        **base,
        "id": "expired",
        "mode": "capability_expired",
        "expected_reason_code": "VERIFICATION_EXPIRED",
    }, tmp_path / "whitelist.json"))
    assert replay["passed"] is True
    assert expired["passed"] is True


def test_mocked_submission_case_never_broadcasts(tmp_path):
    record = asyncio.run(wallet_runner.run_case({
        "id": "E05",
        "category": "simulation_and_submission",
        "mode": "api_wallet_success",
        "expected_outcome": "EXECUTED",
        "expected_reason_code": "TRANSACTION_SUBMITTED",
    }, tmp_path / "whitelist.json"))
    assert record["passed"] is True
    assert record["transaction_broadcast"] is False
    assert record["evidence"]["submission_simulated"] is True
