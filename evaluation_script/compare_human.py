from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from typing import Dict, List, Tuple

from .prepare_review import DIMENSIONS


def compare_human_reviews(review_json: Path, out_csv: Path | None = None) -> Dict[str, object]:
    data = json.loads(Path(review_json).read_text(encoding="utf-8"))
    reviews = data.get("reviews", [])
    dimension_ids = [dimension["id"] for dimension in DIMENSIONS]
    rows: List[Dict[str, object]] = []
    for review in reviews:
        for dimension in dimension_ids:
            item = review.get("decisions", {}).get(dimension, {})
            model_score = _to_float(item.get("model_score"))
            human_score = _to_float(item.get("human_score"))
            rows.append(
                {
                    "annotator_id": review.get("annotator_id") or data.get("annotator_id"),
                    "session_id": review.get("session_id") or data.get("session_id"),
                    "dataset_id": review.get("dataset_id"),
                    "sample_id": review.get("sample_id"),
                    "candidate_id": review.get("candidate_id"),
                    "dimension": dimension,
                    "status": review.get("status", ""),
                    "agree": item.get("agree"),
                    "model_score": model_score,
                    "human_score": human_score,
                    "confidence": item.get("confidence", ""),
                    "absolute_error": abs(model_score - human_score)
                    if model_score is not None and human_score is not None
                    else None,
                    "justification": item.get("justification", ""),
                }
            )

    valid_errors = [row["absolute_error"] for row in rows if row["absolute_error"] is not None]
    agree_values = [row["agree"] for row in rows if row["agree"] in {True, False}]
    summary = {
        "review_items": len(rows),
        "agreement_rate": sum(1 for value in agree_values if value) / len(agree_values) if agree_values else None,
        "score_mae": mean(valid_errors) if valid_errors else None,
    }

    if out_csv:
        _write_rows(rows, out_csv)
    return {"summary": summary, "rows": rows}


def _to_float(value) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_rows(rows: List[Dict[str, object]], out_csv: Path) -> None:
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "annotator_id",
        "session_id",
        "dataset_id",
        "sample_id",
        "candidate_id",
        "dimension",
        "status",
        "agree",
        "model_score",
        "human_score",
        "confidence",
        "absolute_error",
        "justification",
    ]
    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare human review decisions with L2 model-judge scores.")
    parser.add_argument("--review-json", type=Path, required=True, help="JSON exported by the frontend.")
    parser.add_argument("--out", type=Path, default=Path("evaluation/human_comparison.csv"), help="Per-item comparison CSV.")
    args = parser.parse_args()

    result = compare_human_reviews(args.review_json, args.out)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote comparison rows to {args.out}")


if __name__ == "__main__":
    main()
