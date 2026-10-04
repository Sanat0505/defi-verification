from evaluation.metrics import calculate_metrics


def test_metrics_are_calculated_from_records():
    records = [{
        "category": "canonical",
        "expected_intent": {"action": "swap"},
        "actual_intent": {"action": "swap"},
        "expected_outcome": "APPROVED",
        "actual_outcome": "APPROVED",
        "latency_ms": 10,
        "error": None,
        "capability_issued": True,
    }]
    metrics = calculate_metrics(records)
    assert metrics["total_cases"] == 1
    assert metrics["intent_exact_match_accuracy"] == 1
    assert metrics["verification_outcome_accuracy"] == 1
    assert metrics["average_latency_ms"] == 10
