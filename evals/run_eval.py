"""Evaluation harness: benchmark local models on the curated question set.

For each (model, question): generate SQL, validate, execute, and compare the
result set to the canonical answer by RESULT EQUIVALENCE (not SQL text). Writes
a per-model CSV and prints accuracy by tier plus latency percentiles.

Usage:
    python -m evals.run_eval                          # default models
    python -m evals.run_eval --models qwen2.5-coder:7b llama3.1:8b mistral
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.agent import OllamaAgent
from src.runner import Runner, execute_readonly

ROOT = Path(__file__).resolve().parent
QUESTIONS_PATH = ROOT / "questions.yaml"
RESULTS_DIR = ROOT / "results"
DB_PATH = ROOT.parent / "data" / "chinook.db"

DEFAULT_MODELS = ["qwen2.5-coder:7b", "llama3.1:8b"]


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    with open(path) as f:
        return yaml.safe_load(f)


def _norm_value(v: object) -> object:
    """Round floats so trailing-decimal noise doesn't cause false mismatches."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 4)
    return v


def _norm_row(row: tuple) -> tuple:
    """Normalize a row into a column-order-insensitive, hashable key."""
    vals = [_norm_value(v) for v in row]
    return tuple(sorted(vals, key=lambda x: (x is None, str(type(x)), str(x))))


def results_equivalent(a: list[tuple], b: list[tuple]) -> bool:
    """True if two result sets contain the same rows (ignoring row/column order).

    Multiset comparison: order-independent but duplicate-sensitive.
    """
    return Counter(_norm_row(r) for r in a) == Counter(_norm_row(r) for r in b)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def evaluate_model(model: str, questions: list[dict]) -> list[dict]:
    """Run every question through one model; return one record per question."""
    runner = Runner(DB_PATH, OllamaAgent(model))
    records: list[dict] = []

    for q in questions:
        canonical_cols, canonical_rows = execute_readonly(DB_PATH, q["sql"])
        res = runner.run(q["question"])

        passed = bool(res.ok and results_equivalent(res.rows, canonical_rows))
        # An ok run whose results differ is a correctness failure, not a pipeline one.
        reason = res.failure_reason
        if res.ok and not passed:
            reason = "wrong_result"

        records.append(
            {
                "question_id": q["id"],
                "difficulty": q["difficulty"],
                "model": model,
                "passed": passed,
                "latency_ms": round(res.latency_ms, 1),
                "failure_reason": reason or "",
                "generated_sql": (res.sql or "").replace("\n", " ").strip(),
            }
        )
    return records


def write_csv(model: str, records: list[dict]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_model = model.replace(":", "-").replace("/", "-")
    out = RESULTS_DIR / f"{ts}_{safe_model}.csv"
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    return out


def summarize(model: str, records: list[dict]) -> None:
    total = len(records)
    passed = sum(r["passed"] for r in records)
    print(f"\n=== {model} ===")
    print(f"accuracy: {passed}/{total} = {100 * passed / total:.0f}%")

    for tier in ("easy", "medium", "hard"):
        tier_recs = [r for r in records if r["difficulty"] == tier]
        if tier_recs:
            tp = sum(r["passed"] for r in tier_recs)
            print(f"  {tier:6}: {tp}/{len(tier_recs)}")

    latencies = [r["latency_ms"] for r in records]
    print(f"  latency p50: {_percentile(latencies, 0.50):.0f} ms")
    print(f"  latency p95: {_percentile(latencies, 0.95):.0f} ms")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    args = parser.parse_args()

    questions = load_questions()
    for model in args.models:
        records = evaluate_model(model, questions)
        out = write_csv(model, records)
        summarize(model, records)
        print(f"  wrote {out}")


if __name__ == "__main__":
    main()
