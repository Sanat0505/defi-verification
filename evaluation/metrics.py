"""Pure metric calculations for evaluation result records."""

from __future__ import annotations

from collections import defaultdict


INTENT_FIELDS = ("action", "protocol", "chain", "token_in", "token_out", "amount")


def _case_scores(record: dict) -> dict:
    expected = record.get("expected_intent") or {}
    actual = record.get("actual_intent") or {}
    field_scores = {
        field: actual.get(field) == expected.get(field)
        for field in INTENT_FIELDS if field in expected
    }
    exact = bool(expected) and all(field_scores.values()) and all(
        actual.get(field) == expected.get(field) for field in expected
    )
    expected_outcome = record.get("expected_outcome")
    actual_outcome = record.get("actual_outcome")
    return {
        "field_scores": field_scores,
        "intent_exact": exact,
        "outcome_correct": actual_outcome == expected_outcome,
        "clarification_correct": (
            expected_outcome != "NEEDS_CLARIFICATION"
            or actual_outcome == "NEEDS_CLARIFICATION"
        ),
        "invalid_prevented": (
            expected_outcome == "APPROVED"
            or (actual_outcome != "APPROVED" and not record.get("capability_issued"))
        ),
    }


def calculate_metrics(records: list[dict]) -> dict:
    total = len(records)
    scored = [(_case_scores(record), record) for record in records]
    field_metrics = {}
    for field in INTENT_FIELDS:
        values = [score["field_scores"][field] for score, _ in scored if field in score["field_scores"]]
        field_metrics[field] = {
            "correct": sum(values),
            "evaluated": len(values),
            "accuracy": (sum(values) / len(values)) if values else None,
        }

    groups = defaultdict(list)
    for score, record in scored:
        groups[record.get("category", "uncategorized")].append(score)
    by_category = {}
    for category, values in sorted(groups.items()):
        category_records = [record for _, record in scored if record.get("category", "uncategorized") == category]
        exact_values = [
            value["intent_exact"] for value, record in zip(values, category_records)
            if record.get("expected_intent")
        ]
        by_category[category] = {
            "count": len(values),
            "intent_exact_accuracy": (
                sum(exact_values) / len(exact_values) if exact_values else None
            ),
            "outcome_accuracy": sum(v["outcome_correct"] for v in values) / len(values),
        }

    consistency_groups = defaultdict(list)
    for record in records:
        if record.get("group_id"):
            signature = (record.get("actual_intent"), record.get("actual_outcome"))
            consistency_groups[record["group_id"]].append(str(signature))
    comparable = [values for values in consistency_groups.values() if len(values) > 1]
    consistent = sum(len(set(values)) == 1 for values in comparable)
    latencies = [record["latency_ms"] for record in records if isinstance(record.get("latency_ms"), (int, float))]
    exceptions = sum(bool(record.get("error")) for record in records)
    pipeline_errors = sum(record.get("actual_outcome") == "ERROR" for record in records)
    intent_scored = [score for score, record in scored if record.get("expected_intent")]
    clarification_scored = [
        score for score, record in scored
        if record.get("expected_outcome") == "NEEDS_CLARIFICATION"
    ]
    invalid_scored = [
        score for score, record in scored
        if record.get("expected_outcome") != "APPROVED"
    ]
    return {
        "total_cases": total,
        "successful_pipeline_executions": total - exceptions - pipeline_errors,
        "unexpected_failures": exceptions,
        "controlled_pipeline_errors": pipeline_errors,
        "crash_error_rate": (exceptions / total) if total else 0,
        "intent_exact_match_accuracy": (
            sum(score["intent_exact"] for score in intent_scored) / len(intent_scored)
            if intent_scored else None
        ),
        "verification_outcome_accuracy": (
            sum(score["outcome_correct"] for score, _ in scored) / total if total else 0
        ),
        "clarification_accuracy": (
            sum(score["clarification_correct"] for score in clarification_scored)
            / len(clarification_scored) if clarification_scored else None
        ),
        "invalid_query_rejection_accuracy": (
            sum(score["invalid_prevented"] for score in invalid_scored)
            / len(invalid_scored) if invalid_scored else None
        ),
        "paraphrase_consistency": (consistent / len(comparable)) if comparable else None,
        "paraphrase_groups_evaluated": len(comparable),
        "average_latency_ms": (sum(latencies) / len(latencies)) if latencies else None,
        "field_accuracy": field_metrics,
        "by_category": by_category,
    }
