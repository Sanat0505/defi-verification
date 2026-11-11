"""Evaluate source-derived queries at the real interpretation boundary only.

No wallet or graph verifier is called. APPROVED means ready for graph checking.
Default selection is the development split; unreviewed test execution requires
an explicit override and is reported as an unreviewed pilot, not final evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import platform
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from evaluation.build_sourced_dataset import OUTPUT, ROOT, validate_dataset

def score(record):
    expected = record.get("expected_intent")
    actual = record.get("actual_intent") or {}
    fields = {key: actual.get(key) == value for key, value in (expected or {}).items()}
    status_ok = record["actual_outcome"] == record["expected_outcome"]
    missing_ok = set(record.get("expected_missing_fields", [])).issubset(record.get("missing_fields", []))
    return {
        "outcome_correct": status_ok,
        "intent_exact": all(fields.values()) if expected is not None else None,
        "field_scores": fields,
        "required_clarification_fields_present": missing_ok,
        "joint_correct": status_ok and missing_ok and all(fields.values()),
        "unsafe_approval": record["expected_outcome"] != "APPROVED" and record["actual_outcome"] == "APPROVED",
    }


def percentile(values, fraction):
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(fraction * len(values)) - 1)]


def metrics(records):
    # First run per case is primary. Repeats never inflate independent n.
    primary = [r for r in records if r["run"] == 1]
    grouped = defaultdict(list)
    for record in primary:
        grouped[record["category"]].append(record)
    fields = defaultdict(list)
    for record in primary:
        for key, value in score(record)["field_scores"].items():
            fields[key].append(value)
    exact = [score(r)["intent_exact"] for r in primary if r.get("expected_intent") is not None]
    labeled_joint = [r for r in primary if r.get("expected_intent") is not None]
    confusion = defaultdict(Counter)
    for record in primary:
        confusion[record["expected_outcome"]][record["actual_outcome"]] += 1
    repeat_groups = defaultdict(list)
    for record in records:
        repeat_groups[record["id"]].append(record)
    repeated = [rows for rows in repeat_groups.values() if len(rows) > 1]
    latencies = [r["latency_ms"] for r in records]
    outcome_correct = sum(score(r)["outcome_correct"] for r in primary)
    negative = [r for r in primary if r["expected_outcome"] != "APPROVED"]
    origins = defaultdict(list)
    for record in primary:
        origins[record.get("origin", "unspecified")].append(record)
    return {
        # Legacy name retained for older consumers: these are unique cases,
        # NOT statistically independent observations (pairs/templates correlate).
        "independent_cases": len(primary), "executions": len(records),
        "unique_cases": len(primary),
        "declared_families": len({r.get("family_id", r["id"]) for r in primary}),
        "independence_note": "The legacy independent_cases key counts cases, not independent observations. Source pairs and templates correlate.",
        "primary_outcome_correct": outcome_correct,
        "primary_outcome_accuracy": outcome_correct / len(primary) if primary else None,
        "primary_complete_reference_matches": sum(score(r)["joint_correct"] for r in primary),
        "intent_exact_correct": sum(exact), "intent_exact_denominator": len(exact),
        "intent_exact_accuracy": sum(exact) / len(exact) if exact else None,
        "joint_correct": sum(score(r)["joint_correct"] for r in labeled_joint),
        "joint_denominator": len(labeled_joint),
        "unsafe_approvals": sum(score(r)["unsafe_approval"] for r in primary),
        "nonapproval_reference_cases": len(negative),
        "nonapproval_without_error": sum(r["actual_outcome"] in {"REJECTED", "UNSUPPORTED", "NEEDS_CLARIFICATION", "INSUFFICIENT_EVIDENCE"} for r in negative),
        "by_origin": {key: {"cases": len(rows), "outcome_correct": sum(score(r)["outcome_correct"] for r in rows),
                            "unsafe_approvals": sum(score(r)["unsafe_approval"] for r in rows)} for key, rows in sorted(origins.items())},
        "errors": sum(r["actual_outcome"] == "ERROR" for r in primary),
        "field_accuracy": {key: {"correct": sum(values), "evaluated": len(values)} for key, values in sorted(fields.items())},
        "confusion_matrix": {key: dict(values) for key, values in confusion.items()},
        "by_category": {key: {"cases": len(rows), "outcome_correct": sum(score(r)["outcome_correct"] for r in rows),
                              "unsafe_approvals": sum(score(r)["unsafe_approval"] for r in rows)} for key, rows in sorted(grouped.items())},
        "repeated_cases": len(repeated),
        "repeat_consistent_cases": sum(len({json.dumps([r["actual_outcome"], r["actual_intent"], r["missing_fields"]], sort_keys=True) for r in rows}) == 1 for rows in repeated),
        "interpretation_latency_ms_not_R6": {
            "p50_nearest_rank": percentile(latencies, 0.5),
            "p95_nearest_rank": percentile(latencies, 0.95),
            "maximum": max(latencies) if latencies else None,
        },
    }


async def run_case(case, run_number, timeout_seconds):
    from source.llm.intent_parser import parse_intent

    started = time.perf_counter()
    error = None
    actual, candidate, missing, message, error_code = "ERROR", None, [], None, None
    unhandled_constraints = []
    try:
        resolution = await asyncio.wait_for(parse_intent(case["query"]), timeout=timeout_seconds)
        actual = resolution.status.value
        candidate = resolution.intent.model_dump(mode="json", exclude_none=True) if resolution.intent else None
        missing, message, error_code = resolution.missing_fields, resolution.message, resolution.error_code
        unhandled_constraints = resolution.unhandled_constraints
    except Exception as exc:
        # Exception text can include provider configuration; record only its type.
        error = type(exc).__name__
    record = {
        "id": case["id"], "run": run_number, "category": case["category"],
        "family_id": case["family_id"], "split": case["split"], "origin": case["origin"],
        "query": case["query"], "expected_intent": case.get("expected_intent"),
        "expected_outcome": case["expected_intent_status"],
        "expected_missing_fields": case.get("expected_missing_fields", []),
        "actual_intent": candidate, "actual_outcome": actual,
        "missing_fields": missing, "message": message, "error_code": error_code,
        "unhandled_constraints": unhandled_constraints,
        "error": error, "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "reference_rationale": case["reference_rationale"],
        "review_status": case["review_status"], "sources": case["sources"],
        "graph_verification_run": False, "transaction_broadcast": False,
    }
    record["score"] = score(record)
    return record


def summary(report):
    meta, result = report["metadata"], report["metrics"]
    lines = ["# Source-derived evaluation: interpretation and scope pilot", "",
        f"- Timestamp: {meta['timestamp_utc']}", f"- Split: {meta['split']}",
        f"- Reference status: {meta['review_status']}",
        f"- Model: `{meta['model']}`; temperature 0; reasoning effort low",
        f"- Dataset SHA-256: `{meta['dataset_sha256']}`",
        f"- Unique cases: {result['unique_cases']}; declared families: {result['declared_families']}; total executions: {result['executions']}",
        "- Case count is not a statistical independence claim; source pairs and templates are correlated.",
        f"- Completion: {meta.get('completion_status', 'complete')}; planned executions: {meta.get('planned_executions', result['executions'])}",
        f"- Primary disposition matches: {result['primary_outcome_correct']}/{result['independent_cases']}",
        f"- Exact supported-schema field matches: {result['intent_exact_correct']}/{result['intent_exact_denominator']}",
        f"- Joint intent/disposition/clarification matches: {result['joint_correct']}/{result['joint_denominator']}",
        f"- Improper APPROVED results for non-approval references: {result['unsafe_approvals']}",
        f"- Primary service/runtime errors: {result['errors']}",
        f"- Non-approval without service error (regardless of exact disposition): {result['nonapproval_without_error']}/{result['nonapproval_reference_cases']}",
        "- Graph calls: 0. Wallet calls: 0. Transactions broadcast: 0.", "",
        "APPROVED means that interpretation accepted the request for subsequent graph checking. It does not mean graph approval, wallet authorization, or transaction success. An improper APPROVED result here identifies an interpretation/scope gap, not a broadcast transaction.", "",
        "This is a development/pilot result with assistant-drafted labels unless the recorded review status says otherwise. Original Arbiter labels were not used as expected outcomes. Errors are not successful rejections. Timing includes the LLM and is NOT the R6 graph-verification measurement.", "",
        "## Category results", "", "| Category | Cases | Correct disposition | Improper approvals |", "|---|---:|---:|---:|"]
    for category, values in result["by_category"].items():
        lines.append(f"| {category} | {values['cases']} | {values['outcome_correct']} | {values['unsafe_approvals']} |")
    lines.extend(["", "## Mismatches", "", "| Case | Expected | Actual | Diagnostic |", "|---|---|---|---|"])
    for row in report["results"]:
        if row["run"] == 1 and not row["score"]["joint_correct"]:
            diagnostic = row.get("error_code") or ("reference-field mismatch" if row["score"]["outcome_correct"] else "disposition mismatch")
            lines.append(f"| {row['id']} | {row['expected_outcome']} | {row['actual_outcome']} | {diagnostic} |")
    lines.extend(["", "## Interpretation latency (not R6)", "", "```json",
                  json.dumps(result["interpretation_latency_ms_not_R6"], indent=2), "```", ""])
    return "\n".join(lines)


def choose_cases(dataset, split, ids, limit, allow_unreviewed):
    validate_dataset(dataset)
    cases = [c for c in dataset["cases"] if c["split"] == split]
    if ids:
        selected = set(ids)
        known = {c["id"] for c in cases}
        if selected - known:
            raise ValueError(f"Unknown IDs for split {split}: {sorted(selected - known)}")
        cases = [c for c in cases if c["id"] in selected]
    if limit:
        cases = cases[:limit]
    if not cases:
        raise ValueError("No evaluation cases selected")
    if split == "test" and not allow_unreviewed and any(c["review_status"] != "researcher_reviewed" for c in cases):
        raise ValueError("Test references are not researcher-reviewed. Review/freeze them first, or explicitly use --allow-unreviewed for an exploratory pilot (not final evaluation).")
    return cases


def save_report(report, json_path):
    """Atomically replace only this run's JSON checkpoint, never another run."""
    report["metrics"] = metrics(report["results"])
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=json_path.parent,
                                     prefix=json_path.stem + "-", suffix=".tmp", delete=False) as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(json_path)


def resume_report(path, expected_metadata):
    report = json.loads(path.read_bytes())
    for key in ("dataset_sha256", "model", "chain_id", "repeats", "split", "selected_case_ids", "code_sha256"):
        if report["metadata"].get(key) != expected_metadata[key]:
            raise ValueError(f"Cannot resume: {key} changed. Start a separate report.")
    keys = [(r["id"], r["run"]) for r in report["results"]]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate completed case/run in checkpoint")
    allowed = {(case_id, repeat) for case_id in expected_metadata["selected_case_ids"]
               for repeat in range(1, expected_metadata["repeats"] + 1)}
    if not set(keys).issubset(allowed):
        raise ValueError("Unexpected completed case/run in checkpoint")
    return report


async def run(args):
    from source.core.config import settings

    payload = args.dataset.read_bytes()
    dataset = json.loads(payload)
    cases = choose_cases(dataset, args.split, args.case, args.limit, args.allow_unreviewed)
    timestamp = datetime.now(timezone.utc)
    report = {
        "dataset_snapshot": dataset,
        "metadata": {
            "timestamp_utc": timestamp.isoformat(), "mode": "intent_only_real_model",
            "dataset": str(args.dataset.resolve()), "dataset_version": dataset["version"],
            "dataset_sha256": hashlib.sha256(payload).hexdigest(), "split": args.split,
            "review_status": "researcher_reviewed" if all(c["review_status"] == "researcher_reviewed" for c in cases) else "assistant_draft_pilot_not_final",
            "model": settings.llm_model, "temperature": 0, "reasoning_effort": "low",
            "chain_id": settings.supported_chain_id, "repeats": args.repeats,
            "python": platform.python_version(), "transaction_broadcast": False,
            "source_commit": dataset.get("source_commit"),
            "selected_case_ids": [c["id"] for c in cases],
            "planned_executions": len(cases) * args.repeats,
            "completion_status": "running",
            "checkpoint_every": args.checkpoint_every,
            "delay_seconds": args.delay,
            "timeout_seconds": args.timeout,
            "max_consecutive_errors": args.max_consecutive_errors,
            "code_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in [
                ROOT / "source/llm" / "intent_parser.py", ROOT / "source/llm" / "normalization.py", Path(__file__).resolve(),
                ROOT / "source/llm" / "request_constraints.py", ROOT / "source/core" / "slippage.py",
                ROOT / "source/core" / "models.py", ROOT / "source/core" / "config.py",
            ]},
        }, "metrics": metrics([]), "results": [],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = "sourced-intent-" + timestamp.strftime("%Y%m%dT%H%M%S%fZ")
    json_path = args.resume or args.output_dir / (stem + ".json")
    if args.resume:
        report = resume_report(json_path, report["metadata"])
        report["metadata"]["completion_status"] = "running"
        report["metadata"].setdefault("resumed_at_utc", []).append(timestamp.isoformat())
    records = report["results"]
    completed = {(r["id"], r["run"]) for r in records}
    save_report(report, json_path)
    print(f"Checkpoint JSON: {json_path}", flush=True)
    consecutive_errors = 0
    try:
        for repeat in range(1, args.repeats + 1):
            for case in cases:
                if (case["id"], repeat) in completed:
                    continue
                record = await run_case(case, repeat, args.timeout)
                records.append(record)
                consecutive_errors = consecutive_errors + 1 if record["actual_outcome"] == "ERROR" else 0
                marker = "MATCH" if record["score"]["joint_correct"] else "MISMATCH"
                print(f"[{len(records)}/{len(cases) * args.repeats}] {case['id']} run={repeat} {marker}: {record['actual_outcome']} (reference {record['expected_outcome']})", flush=True)
                if len(records) % args.checkpoint_every == 0 or consecutive_errors:
                    save_report(report, json_path)
                if consecutive_errors >= args.max_consecutive_errors:
                    report["metadata"]["completion_status"] = "stopped_consecutive_service_errors"
                    break
                if args.delay:
                    await asyncio.sleep(args.delay)
            if consecutive_errors >= args.max_consecutive_errors:
                break
        if len(records) == len(cases) * args.repeats:
            report["metadata"]["completion_status"] = "complete"
    except BaseException:
        report["metadata"]["completion_status"] = "interrupted"
        raise
    finally:
        report["metadata"]["last_checkpoint_utc"] = datetime.now(timezone.utc).isoformat()
        save_report(report, json_path)
        json_path.with_suffix(".md").write_text(summary(report), encoding="utf-8")
    print(summary(report))
    print(f"JSON: {json_path}\nSummary: {json_path.with_suffix('.md')}")
    return 1 if report["metrics"]["errors"] else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=OUTPUT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / '.cache/evaluation-runs/sourced')
    parser.add_argument("--split", choices=("development", "test"), default="development")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--checkpoint-every", type=int, default=10)
    parser.add_argument("--delay", type=float, default=0, help="Seconds between sequential requests")
    parser.add_argument("--max-consecutive-errors", type=int, default=3)
    parser.add_argument("--resume", type=Path, help="Continue a matching JSON checkpoint; completed cases are not rerun")
    parser.add_argument("--allow-unreviewed", action="store_true")
    parser.add_argument("--validate-only", action="store_true", help="Validate the dataset offline; never call the model")
    args = parser.parse_args(argv)
    if args.limit < 0 or args.repeats < 1 or args.timeout <= 0 or args.delay < 0 or args.checkpoint_every < 1 or args.max_consecutive_errors < 1:
        parser.error("Invalid limit, repeats, timeout, delay, checkpoint interval or error limit")
    if args.validate_only:
        dataset = json.loads(args.dataset.read_bytes())
        print(json.dumps({"cases": len(dataset["cases"]), "splits": validate_dataset(dataset)}, indent=2))
        return 0
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
