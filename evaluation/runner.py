"""Execute the evaluation dataset through the real application pipeline."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import platform
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import settings
from core.models import PromptRequest
from evaluation.metrics import calculate_metrics
from services.pipeline import process_prompt


DEFAULT_DATASET = Path(__file__).parent / "datasets" / "cases.json"
DEFAULT_REPORTS = ROOT / '.cache/evaluation-runs/pipeline'


async def run_case(case: dict, run_number: int) -> dict:
    started = time.perf_counter()
    conversation_id = f"eval-{case['id']}-{run_number}-{uuid.uuid4()}"
    turns = case.get("turns") or [case["query"]]
    responses = []
    error = None
    try:
        for index, prompt in enumerate(turns):
            responses.append(await process_prompt(PromptRequest(
                prompt=prompt,
                conversation_id=conversation_id,
                new_operation=index == 0,
            )))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    final = responses[-1] if responses else {}
    return {
        "id": case["id"],
        "run": run_number,
        "category": case["category"],
        "group_id": case.get("group_id"),
        "query": case.get("query") or turns[0],
        "turns": turns,
        "expected_intent": case.get("expected_intent"),
        "expected_outcome": case["expected_outcome"],
        "actual_intent": final.get("intent"),
        "actual_outcome": final.get("decision") or "ERROR",
        "capability_issued": bool(final.get("verification_id")),
        "missing_fields": final.get("missing_fields", []),
        "message": final.get("message") or final.get("reason"),
        "latency_ms": latency_ms,
        "stage_latencies": {
            "graph_verification_ms": final.get("latency_ms"),
        },
        "error": error,
        "error_code": final.get("error_code"),
        "responses": [
            {key: value for key, value in response.items() if key != "verification_id"}
            for response in responses
        ],
    }


def _summary_markdown(metadata: dict, metrics: dict) -> str:
    def pct(value):
        return "n/a" if value is None else f"{value * 100:.2f}%"

    lines = [
        "# Evaluation summary", "",
        f"- Timestamp (UTC): {metadata['timestamp_utc']}",
        f"- Model: `{metadata['model']}`",
        f"- Temperature: {metadata['temperature']}",
        f"- Total test executions: {metrics['total_cases']}",
        f"- Intent exact-match accuracy: {pct(metrics['intent_exact_match_accuracy'])}",
        f"- Verification outcome accuracy: {pct(metrics['verification_outcome_accuracy'])}",
        f"- Clarification accuracy: {pct(metrics['clarification_accuracy'])}",
        f"- Invalid-query rejection accuracy: {pct(metrics['invalid_query_rejection_accuracy'])}",
        f"- Paraphrase consistency: {pct(metrics['paraphrase_consistency'])}",
        f"- Unexpected failures: {metrics['unexpected_failures']}",
        f"- Controlled pipeline errors: {metrics['controlled_pipeline_errors']}",
        f"- Average total latency: {metrics['average_latency_ms'] or 'n/a'} ms", "",
        "## Field accuracy", "",
        "| Field | Correct | Evaluated | Accuracy |", "|---|---:|---:|---:|",
    ]
    for field, item in metrics["field_accuracy"].items():
        lines.append(f"| {field} | {item['correct']} | {item['evaluated']} | {pct(item['accuracy'])} |")
    lines.extend(["", "## By category", "", "| Category | Cases | Intent exact | Outcome |", "|---|---:|---:|---:|"])
    for category, item in metrics["by_category"].items():
        lines.append(
            f"| {category} | {item['count']} | {pct(item['intent_exact_accuracy'])} | {pct(item['outcome_accuracy'])} |"
        )
    return "\n".join(lines) + "\n"


async def run(args) -> int:
    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    if dataset.get("requires_sourced_runner"):
        raise ValueError(
            "This dataset separates interpretation references from conditional graph outcomes. "
            "Use python -m evaluation.sourced_runner; do not score it as an end-to-end graph benchmark."
        )
    cases = dataset["cases"]
    if args.case:
        selected = set(args.case)
        cases = [case for case in cases if case["id"] in selected]
    cases = cases[: args.limit or None]
    records = []
    for repeat in range(1, args.repeats + 1):
        for case in cases:
            records.append(await run_case(case, repeat))

    metrics = calculate_metrics(records)
    timestamp = datetime.now(timezone.utc)
    metadata = {
        "timestamp_utc": timestamp.isoformat(),
        "dataset": str(Path(args.dataset).resolve()),
        "dataset_version": dataset.get("version"),
        "model": settings.llm_model,
        "temperature": 0,
        "reasoning_effort": "low",
        "chain_id": settings.supported_chain_id,
        "knowledge_max_age_hours": settings.knowledge_max_age_hours,
        "repeats": args.repeats,
        "python": platform.python_version(),
    }
    report = {"metadata": metadata, "metrics": metrics, "results": records}
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"evaluation-{stamp}.json"
    csv_path = output_dir / f"evaluation-{stamp}.csv"
    md_path = output_dir / f"evaluation-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "id", "run", "category", "query", "expected_outcome", "actual_outcome",
            "latency_ms", "missing_fields", "error",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = dict(record)
            row["missing_fields"] = ",".join(record.get("missing_fields") or [])
            writer.writerow(row)
    md_path.write_text(_summary_markdown(metadata, metrics), encoding="utf-8")
    print(_summary_markdown(metadata, metrics))
    print(f"JSON: {json_path}\nCSV: {csv_path}\nSummary: {md_path}")
    return 0 if metrics["unexpected_failures"] == 0 else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run reproducible DeFi verification evaluation")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORTS))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--case", action="append", default=[], help="Run one case ID; may be repeated")
    args = parser.parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
