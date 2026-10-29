"""Offline checks for ordering, preservation, and quota/freshness boundaries."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from evaluation import balanced_600_runner as runner


def test_balanced_saved_order_and_denominators():
    dataset = json.loads(runner.DEFAULT_DATASET.read_bytes())
    cases = runner.flatten(dataset)
    order = json.loads(runner.ORDER_PATH.read_bytes())["prompt_ids"]
    assert [c["id"] for c in cases] == order
    assert len(cases) == 600
    assert sum(c["primary"] for c in cases) == 300
    assert sum(c["graph_eligible"] for c in cases) == 340
    assert len({runner.graph_key(c["reference_intent"]) for c in cases if c["graph_eligible"]}) == 112
    for start in range(0, 600, 12):
        block = cases[start:start + 12]
        assert set(runner.Counter(c["category"] for c in block).values()) == {2}
    assert [c["primary"] for c in cases[:2]] != [c["primary"] for c in cases[2:4]] or any(
        not cases[i]["primary"] for i in range(0, 600, 2))


def test_order_cannot_silently_drop_or_duplicate_a_case(tmp_path, monkeypatch):
    order = json.loads(runner.ORDER_PATH.read_bytes())
    order["prompt_ids"][0] = order["prompt_ids"][1]
    path = tmp_path / "order.json"
    path.write_text(json.dumps(order))
    monkeypatch.setattr(runner, "ORDER_PATH", path)
    with pytest.raises(AssertionError):
        runner.flatten(json.loads(runner.DEFAULT_DATASET.read_bytes()))


def test_daily_quota_stops_but_minute_limit_does_not():
    assert runner.daily_quota_hit([{"success": False, "rate_limit_scope": ["tokens_per_day"]}])
    assert runner.daily_quota_hit([{"success": False, "rate_limit_scope": ["requests_per_day"]}])
    assert not runner.daily_quota_hit([{"success": False, "rate_limit_scope": ["tokens_per_minute"]}])
    assert not runner.daily_quota_hit([{"success": True}])


def test_expired_snapshot_cannot_continue_a_multiday_run():
    now = datetime.now(timezone.utc)
    def facts(age):
        return {"preflight": {"deployments": [
            {"protocol": name, "last_successful_sync_at": (now - timedelta(hours=age)).isoformat()}
            for name in ["Uniswap V3", "Aave V3"]]}}
    assert runner.snapshot_still_fresh(facts(1))
    assert not runner.snapshot_still_fresh(facts(runner.settings.knowledge_max_age_hours + 1))
    assert not runner.snapshot_still_fresh({"preflight": {"deployments": []}})


def test_execution_authorization_pins_dataset_and_order():
    record = json.loads(runner.AUTH_PATH.read_bytes())
    assert record["dataset_sha256"] == runner.digest(runner.DEFAULT_DATASET.read_bytes())
    assert record["order_sha256"] == runner.digest(runner.ORDER_PATH.read_bytes())
    assert record["user_accepted_for_execution"]
    assert not record["item_level_human_review_documented"]


def test_resume_journal_rejects_duplicate_results(tmp_path):
    path = tmp_path / "interpretations.jsonl"
    record = {"id": "BAL600-001-A", "resolution": {"status": "ERROR"}}
    runner.journal(path, record)
    assert runner.saved_interpretations(path)[record["id"]] == record
    runner.journal(path, record)
    with pytest.raises(ValueError, match="Duplicate"):
        runner.saved_interpretations(path)


def test_binary_metrics_keep_errors_and_abstentions_outside_matrix():
    from evaluation.analyse_balanced_600 import binary_counts
    rows = [dict(expected_pipeline=expected, actual_pipeline=actual, operational_error=error)
            for expected,actual,error in [
                ('APPROVED','APPROVED',False), ('REJECTED','APPROVED',False),
                ('APPROVED','UNSUPPORTED',False), ('NEEDS_CLARIFICATION','REJECTED',False),
                ('APPROVED','ERROR',True), ('REJECTED','INSUFFICIENT_EVIDENCE',False)]]
    result=binary_counts(rows)
    assert [result[k] for k in ['TP','FP','FN','TN']] == [1,1,1,1]
    assert result['operational_errors'] == result['abstentions'] == 1
    assert result['decision_denominator'] == 4
    assert result['decision_coverage'] == pytest.approx(4/6)
    assert result['precision'] == result['recall'] == result['f1'] == .5
    assert binary_counts([])['precision'] is None
