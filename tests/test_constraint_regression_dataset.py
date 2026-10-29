import json
from collections import Counter

from evaluation.build_constraint_regression import OUTPUT, build
from evaluation.build_sourced_dataset import validate_dataset


def test_versioned_regression_dataset_matches_authored_references():
    dataset = json.loads(OUTPUT.read_bytes())
    assert dataset == build()
    assert validate_dataset(dataset) == {"development": 60}
    assert Counter(c["expected_intent_status"] for c in dataset["cases"]) == {
        "APPROVED": 22, "UNSUPPORTED": 24, "REJECTED": 10, "NEEDS_CLARIFICATION": 4}
    assert all(c["expected_graph_outcome"] is None for c in dataset["cases"])
    assert all(c["review_status"] != "researcher_reviewed" for c in dataset["cases"])
