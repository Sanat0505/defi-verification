import argparse
import asyncio
import hashlib
import json
import re
from collections import Counter

import pytest

from evaluation.build_expanded_dataset import OUTPUT, canonical_query
from evaluation.build_sourced_dataset import OUTPUT as BASELINE, validate_dataset
from evaluation.sourced_runner import metrics, resume_report, save_report


@pytest.fixture
def expanded():
    return json.loads(OUTPUT.read_bytes())


def test_expanded_count_unique_queries_and_coverage(expanded):
    cases = expanded["cases"]
    assert len(cases) == 500
    assert validate_dataset(expanded) == {"development": 500}
    assert len({canonical_query(c["query"]) for c in cases}) == 500
    assert len({c["family_id"] for c in cases}) == 350
    assert Counter(c["origin"] for c in cases) == {
        "unchanged_source": 150, "explicit_context_adaptation": 120,
        "explicit_protocol_adaptation": 30, "documentation_based_synthetic": 200,
    }
    assert all(c["expected_graph_outcome"] is None for c in cases)
    assert all(c["review_status"] == "assistant_draft_pending_researcher_review" for c in cases)


def test_baseline_holdout_and_all_baseline_cases_are_excluded(expanded):
    payload = BASELINE.read_bytes()
    baseline = json.loads(payload)
    assert expanded["sampling"]["baseline_sha256"] == hashlib.sha256(payload).hexdigest()
    assert len([c for c in baseline["cases"] if c["split"] == "test"]) == 90
    assert not ({c["family_id"] for c in baseline["cases"]} & {c["family_id"] for c in expanded["cases"]})
    assert not ({canonical_query(c["query"]) for c in baseline["cases"]} & {canonical_query(c["query"]) for c in expanded["cases"]})


def test_every_source_transformation_is_exactly_reproducible(expanded):
    for case in expanded["cases"]:
        if case["origin"] == "explicit_context_adaptation":
            original = case["sources"][0]["original_query"]
            assert case["query"] == re.sub(r"\bUniswap\b", "Uniswap V3 on Ethereum Sepolia", original, flags=re.I)
            assert case["expected_intent_status"] == "UNSUPPORTED"
        if case["origin"] == "explicit_protocol_adaptation":
            assert case["query"].endswith(case["sources"][0]["original_query"])


def test_positive_references_preserve_native_eth(expanded):
    native = [c for c in expanded["cases"] if c["category"] == "expanded_uniswap_core" and c["expected_intent"]["token_in"] == "ETH"]
    assert len(native) == 20
    assert all(" ETH" in c["query"] for c in native)


def record(case_id="one", family="shared", **changes):
    return {"id": case_id, "family_id": family, "run": 1, "category": "constraints", "origin": "unchanged_source",
            "expected_outcome": "UNSUPPORTED", "actual_outcome": "REJECTED", "expected_intent": None,
            "actual_intent": None, "missing_fields": [], "latency_ms": 1, **changes}


def test_correlated_cases_and_safe_nonapproval_are_reported_separately():
    result = metrics([record(), record("two"), record("three", actual_outcome="ERROR")])
    assert result["unique_cases"] == 3
    assert result["declared_families"] == 1
    assert result["primary_outcome_correct"] == 0
    assert result["nonapproval_without_error"] == 2
    assert result["errors"] == 1


def test_compact_analysis_separates_core_fields_from_disposition():
    from evaluation.summarize_expanded_results import summarize
    core = record("core", category="expanded_aave_core", expected_outcome="APPROVED", actual_outcome="APPROVED",
                  expected_intent={"amount": "5"}, actual_intent={"amount": "50"}, query="Repay 5 USDT using Aave.")
    refused = record("blocked", query="Constrained swap")
    result = summarize({"metadata": {"completion_status": "complete", "planned_executions": 2,
                                      "review_status": "assistant_draft_pilot_not_final"},
                        "dataset_snapshot": {"limitations": ["draft"]}, "results": [core, refused]})
    assert result["core_requests"]["status_matches"] == 1
    assert result["core_requests"]["joint_reference_matches"] == 0
    assert result["nonapproval_references"]["nonapproval_without_error"] == 1
    assert result["overall"]["status_matches"] == 1
    assert result["findings"][0]["field_mismatches"] == ["amount"]


def test_atomic_checkpoint_and_resume_guard(tmp_path):
    path = tmp_path / "run.json"
    metadata = {"dataset_sha256": "abc", "model": "test", "chain_id": 11155111,
                "repeats": 1, "split": "development", "selected_case_ids": ["one"], "code_sha256": {"file": "hash"}}
    report = {"metadata": metadata, "results": [record()]}
    save_report(report, path)
    assert not list(tmp_path.glob("*.tmp"))
    assert resume_report(path, metadata)["metrics"]["unique_cases"] == 1
    with pytest.raises(ValueError, match="dataset_sha256"):
        resume_report(path, {**metadata, "dataset_sha256": "different"})
    report["results"].append(record())
    save_report(report, path)
    with pytest.raises(ValueError, match="Duplicate"):
        resume_report(path, metadata)


def test_run_stops_after_service_errors_and_saves_partial_json(tmp_path, monkeypatch):
    from evaluation import sourced_runner
    calls = []

    async def fake_run(case, repeat, timeout):
        calls.append(case["id"])
        row = record(case["id"], actual_outcome="ERROR")
        row["score"] = sourced_runner.score(row)
        return row

    monkeypatch.setattr(sourced_runner, "run_case", fake_run)
    args = argparse.Namespace(dataset=OUTPUT, output_dir=tmp_path, split="development", case=[], limit=5,
                              allow_unreviewed=False, repeats=1, timeout=1, checkpoint_every=2,
                              delay=0, max_consecutive_errors=2, resume=None)
    assert asyncio.run(sourced_runner.run(args)) == 1
    path = next(tmp_path.glob("*.json"))
    report = json.loads(path.read_bytes())
    assert len(calls) == 2
    assert report["metadata"]["completion_status"] == "stopped_consecutive_service_errors"
    assert report["metadata"]["planned_executions"] == 5
    assert report["metrics"]["errors"] == 2
    # Resume skips completed/error cases instead of erasing or hiding failures.
    args.resume = path
    assert asyncio.run(sourced_runner.run(args)) == 1
    assert len(calls) == 4
    assert len(set(calls)) == 4
