import json

import pytest

from evaluation.build_sourced_dataset import OUTPUT, validate_dataset
from evaluation.source_import import audit, constraint_flags, source_family, load_source
from evaluation.sourced_runner import choose_cases, metrics, score


@pytest.fixture
def dataset():
    return json.loads(OUTPUT.read_text(encoding="utf-8"))


def test_dataset_counts_and_review_state(dataset):
    assert len(dataset["cases"]) == 120
    assert validate_dataset(dataset) == {"development": 30, "test": 90}
    assert all(c["review_status"] == "assistant_draft_pending_researcher_review" for c in dataset["cases"])
    assert all(c["expected_graph_outcome"] is None for c in dataset["cases"])


def test_originals_are_unchanged_and_labels_are_not_copied(dataset):
    originals = [c for c in dataset["cases"] if c["origin"] == "unchanged_source"]
    assert len(originals) == 18
    assert {c["sources"][0]["upstream_label_not_gold"] for c in originals} == {"PASS", "REJECT"}
    for case in originals:
        assert case["query"] == case["sources"][0]["original_query"]
        assert case["sources"][0]["commit"] == dataset["source_commit"]
        assert len(case["sources"][0]["record_sha256"]) == 64


def test_constraints_preserved_and_simplifications_explicit(dataset):
    cases = {case["id"]: case for case in dataset["cases"]}
    for i in range(1, 13):
        original, adapted = cases[f"SRC-U{i:02}"], cases[f"ADP-U{i:02}"]
        assert adapted["query"].replace("Uniswap V3 on Ethereum Sepolia", "Uniswap") == original["query"]
        assert constraint_flags(adapted["query"]) == constraint_flags(original["query"])
        for variant in (1, 2):
            control = cases[f"CTL-U{i:02}-{variant}"]
            assert control["origin"] == "source_inspired_simplified_control"
            assert len(control["transformations"]) >= 4
            assert control["family_id"] == original["family_id"]


def test_family_leakage_rejected(dataset):
    dataset["cases"][1]["split"] = "test"
    with pytest.raises(ValueError, match="leaks"):
        validate_dataset(dataset)


def test_paraphrase_semantics_must_match(dataset):
    target = next(c for c in dataset["cases"] if c["id"] == "CTL-U01-2")
    target["expected_intent"] = {**target["expected_intent"], "amount": "999"}
    with pytest.raises(ValueError, match="paraphrase"):
        validate_dataset(dataset)


def test_test_split_is_not_silently_exposed(dataset):
    with pytest.raises(ValueError, match="researcher-reviewed"):
        choose_cases(dataset, "test", [], 0, False)
    assert len(choose_cases(dataset, "development", [], 0, False)) == 30
    assert len(choose_cases(dataset, "test", [], 0, True)) == 90
    with pytest.raises(ValueError, match="Unknown IDs"):
        choose_cases(dataset, "development", ["absent"], 0, False)


def make_record(**changes):
    return {
        "id": "one", "run": 1, "category": "constraint",
        "expected_outcome": "UNSUPPORTED", "actual_outcome": "APPROVED",
        "expected_intent": {"amount": "2"}, "actual_intent": {"amount": "2"},
        "missing_fields": [], "expected_missing_fields": [], "latency_ms": 4,
        **changes,
    }


def test_correct_core_fields_cannot_hide_a_dropped_constraint():
    result = score(make_record())
    assert result["intent_exact"] is True
    assert result["outcome_correct"] is False
    assert result["joint_correct"] is False
    assert result["unsafe_approval"] is True


def test_errors_are_not_successful_rejections():
    result = metrics([make_record(actual_outcome="ERROR", actual_intent=None)])
    assert result["errors"] == 1
    assert result["primary_outcome_correct"] == 0
    assert result["joint_correct"] == 0


def test_repeats_do_not_inflate_primary_denominator():
    records = [make_record(run=n) for n in (1, 2, 3)]
    result = metrics(records)
    assert result["executions"] == 3
    assert result["independent_cases"] == 1
    assert result["unsafe_approvals"] == 1
    assert result["intent_exact_denominator"] == 1
    assert result["repeated_cases"] == 1


def test_clarification_must_identify_required_missing_fields():
    result = score(make_record(expected_outcome="NEEDS_CLARIFICATION", actual_outcome="NEEDS_CLARIFICATION",
                               expected_intent=None, expected_missing_fields=["protocol"], missing_fields=["amount"]))
    assert result["outcome_correct"] is True
    assert result["joint_correct"] is False


def test_audit_does_not_reinterpret_transaction_context_as_query_fields():
    record = {"human_intent": "Swap 2 USDC for WETH.", "metadata": {"tx_hash": "0xABC"},
              "proposed_tx": {"protocol": "Uniswap V2", "chain_id": 1}, "label": "PASS"}
    result = audit([record])
    assert result["proposed_transaction_protocols_not_query_labels"] == {"Uniswap V2": 1}
    assert result["explicit_v3_intent_texts"] == 0
    assert source_family(record) == "0xabc"


def test_tampered_cache_is_not_used(tmp_path):
    (tmp_path / "eg_uniswap_samples.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_source("uniswap", tmp_path)


def test_cli_validation_never_needs_model_or_graph(monkeypatch):
    from evaluation import sourced_runner
    monkeypatch.setattr(sourced_runner, "run", lambda *args: (_ for _ in ()).throw(AssertionError("model call")))
    assert sourced_runner.main(["--validate-only"]) == 0
