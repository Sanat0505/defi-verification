"""Create a compact JSON analysis of an existing run; never call any service."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from evaluation.sourced_runner import score


def summarize(report):
    primary = [r for r in report["results"] if r["run"] == 1]
    core = [r for r in primary if r["category"] in {"expanded_uniswap_core", "expanded_aave_core"}]
    blocked = [r for r in primary if r["expected_outcome"] != "APPROVED"]
    groups = defaultdict(list)
    for row in primary:
        groups[row["category"]].append(row)

    def counts(rows):
        matched = sum(score(r)["outcome_correct"] for r in rows)
        return {
            "queries": len(rows),
            "status_matches": matched,
            "status_agreement": matched / len(rows) if rows else None,
            "joint_reference_matches": sum(score(r)["joint_correct"] for r in rows),
            "improper_semantic_approvals": sum(score(r)["unsafe_approval"] for r in rows),
            "service_errors": sum(r["actual_outcome"] == "ERROR" for r in rows),
        }

    findings = []
    for row in primary:
        result = score(row)
        if not result["joint_correct"]:
            findings.append({
                "id": row["id"], "query": row["query"], "category": row["category"],
                "expected_status": row["expected_outcome"], "actual_status": row["actual_outcome"],
                "expected_intent": row.get("expected_intent"), "actual_intent": row.get("actual_intent"),
                "improper_semantic_approval": result["unsafe_approval"],
                "field_mismatches": [key for key, matches in result["field_scores"].items() if not matches],
                "error_code": row.get("error_code"),
                "note": "Review against the frozen draft reference; this is not a broadcast transaction.",
            })
    return {
        "completion_status": report["metadata"]["completion_status"],
        "planned_executions": report["metadata"]["planned_executions"],
        "reference_status": report["metadata"]["review_status"],
        "measurement": "Interpretation/scope agreement against assistant-drafted references, not full-system accuracy.",
        "overall": counts(primary), "core_requests": counts(core),
        "core_by_protocol": {
            "Uniswap V3": counts([r for r in core if r["category"] == "expanded_uniswap_core"]),
            "Aave V3": counts([r for r in core if r["category"] == "expanded_aave_core"]),
        },
        "nonapproval_references": {
            **counts(blocked),
            "nonapproval_without_error": sum(r["actual_outcome"] in {"REJECTED", "UNSUPPORTED", "NEEDS_CLARIFICATION", "INSUFFICIENT_EVIDENCE"} for r in blocked),
        },
        "by_category": {key: counts(rows) for key, rows in sorted(groups.items())},
        "not_measured": ["graph verification", "wallet checks", "execution success", "R6 graph-only latency"],
        "limitations": report["dataset_snapshot"]["limitations"],
        "findings": findings,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = args.report.read_bytes()
    result = summarize(json.loads(payload))
    result["source_report"] = str(args.report)
    result["source_report_sha256"] = hashlib.sha256(payload).hexdigest()
    output = args.output or args.report.with_name(args.report.stem + "-analysis.json")
    if output.resolve() == args.report.resolve() or output.exists():
        raise FileExistsError("Use a new output path; never overwrite the input report or an existing analysis.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "completion_status": result["completion_status"],
                      "overall": result["overall"], "core_requests": result["core_requests"],
                      "nonapproval_references": result["nonapproval_references"]}, indent=2))


if __name__ == "__main__":
    main()
