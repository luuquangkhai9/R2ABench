from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .l0_syntax import _plantuml_command, _run_plantuml_render
from .pipeline import DatasetSample, build_dataset_index


DIMENSIONS = [
    {
        "id": "completeness",
        "label": "Completeness",
        "description": "Covers requirements, ASRs, and quality scenarios.",
    },
    {
        "id": "faithfulness",
        "label": "Faithfulness",
        "description": "Avoids hallucinated components, relations, technologies, and unsupported assumptions.",
    },
    {
        "id": "architectural_rationality",
        "label": "Architectural Rationality",
        "description": "Uses reasonable responsibilities, dependencies, boundaries, and quality-attribute handling.",
    },
    {
        "id": "traceability",
        "label": "Traceability",
        "description": "Links key elements and decisions back to requirements or project evidence.",
    },
    {
        "id": "readability",
        "label": "Readability",
        "description": "Presents a clear, reviewable architecture view.",
    },
]

IMAGE_SUFFIXES = [".png", ".jpg", ".jpeg", ".svg", ".webp"]
PREDICTION_FILENAMES = [
    "predicted.puml",
    "prediction.puml",
    "candidate.puml",
    "output.puml",
    "generated.puml",
    "architecture.puml",
]
MAX_CONTEXT_CHARS = 6000


def prepare_review_samples(
    results_csv: Path | Sequence[Path],
    out_json: Path,
    sample_size: int = 20,
    seed: int = 13,
    gt_image_dir: Optional[Path] = None,
    pred_image_dir: Optional[Path] = None,
    *,
    strategy: str = "random",
    dataset_dirs: Optional[Sequence[Path]] = None,
    pred_roots: Optional[Sequence[Path]] = None,
    asset_dir: Optional[Path] = None,
    render_candidates: bool = False,
    require_candidate_image: Optional[bool] = None,
) -> Dict[str, object]:
    result_paths = _path_list(results_csv)
    rows = _read_rows(result_paths)
    eligible = [row for row in rows if _truthy_or_blank(row.get("l0_valid"))]
    if not eligible:
        eligible = rows

    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)

    dataset_index = _build_dataset_index(dataset_dirs or [])
    asset_root = Path(asset_dir) if asset_dir else None
    if asset_root:
        asset_root.mkdir(parents=True, exist_ok=True)

    image_required = bool(pred_image_dir or render_candidates) if require_candidate_image is None else require_candidate_image
    rng = random.Random(seed)
    selected = _sample_rows(eligible, sample_size, rng, strategy)
    skipped_missing_candidate_image = 0

    if image_required:
        selected = _sample_rows(eligible, len(eligible), rng, strategy, preserve_full_order=False)

    samples = []
    for row in selected:
        sample = _row_to_sample(
            row,
            out_json,
            gt_image_dir=Path(gt_image_dir) if gt_image_dir else None,
            pred_image_dir=Path(pred_image_dir) if pred_image_dir else None,
            dataset_index=dataset_index,
            pred_roots=[Path(path) for path in (pred_roots or [])],
            asset_dir=asset_root,
            render_candidates=render_candidates,
        )
        if image_required and not sample.get("candidate_image"):
            skipped_missing_candidate_image += 1
            continue
        samples.append(sample)
        if len(samples) >= sample_size:
            break

    payload = {
        "schema_version": "ma4sa-review-samples-v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_results": [str(path) for path in result_paths],
        "sampling": {
            "strategy": strategy,
            "seed": seed,
            "requested_n": sample_size,
            "eligible_n": len(eligible),
            "actual_n": len(samples),
            "require_candidate_image": image_required,
            "skipped_missing_candidate_image": skipped_missing_candidate_image,
        },
        "dimensions": DIMENSIONS,
        "samples": samples,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _path_list(value: Path | Sequence[Path]) -> List[Path]:
    if isinstance(value, (str, Path)):
        return [Path(value)]
    return [Path(path) for path in value]


def _read_rows(paths: Sequence[Path]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for path in paths:
        inferred_dataset = _infer_dataset_id(path)
        with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                item = dict(row)
                if not item.get("dataset_id"):
                    item["dataset_id"] = inferred_dataset
                item["_source_results_csv"] = str(path)
                rows.append(item)
    return rows


def _sample_rows(
    rows: List[Dict[str, str]],
    sample_size: int,
    rng: random.Random,
    strategy: str,
    *,
    preserve_full_order: bool = True,
) -> List[Dict[str, str]]:
    if sample_size >= len(rows) and preserve_full_order:
        return list(rows)
    if strategy == "stratified":
        return _balanced_stratified_sample(rows, sample_size, rng)
    ordered = list(rows)
    rng.shuffle(ordered)
    return ordered[:sample_size]


def _balanced_stratified_sample(rows: List[Dict[str, str]], sample_size: int, rng: random.Random) -> List[Dict[str, str]]:
    groups: Dict[tuple[str, str, str], List[Dict[str, str]]] = {}
    for row in rows:
        key = (
            row.get("dataset_id") or "dataset",
            row.get("workflow") or _candidate_part(row.get("candidate_id", ""), 0),
            row.get("model_id") or _candidate_part(row.get("candidate_id", ""), 1),
        )
        groups.setdefault(key, []).append(row)

    for group in groups.values():
        rng.shuffle(group)

    selected: List[Dict[str, str]] = []
    group_keys = sorted(groups)
    rng.shuffle(group_keys)
    while len(selected) < sample_size and any(groups.values()):
        for key in group_keys:
            if len(selected) >= sample_size:
                break
            if groups[key]:
                selected.append(groups[key].pop())
    return selected


def _row_to_sample(
    row: Dict[str, str],
    out_json: Path,
    *,
    gt_image_dir: Optional[Path],
    pred_image_dir: Optional[Path],
    dataset_index: Dict[str, DatasetSample],
    pred_roots: Sequence[Path],
    asset_dir: Optional[Path],
    render_candidates: bool,
) -> Dict[str, object]:
    sample_id = row.get("sample_id") or Path(row.get("pred_path", "sample")).stem
    candidate_id = row.get("candidate_id") or "candidate"
    dataset_id = row.get("dataset_id") or _infer_dataset_id(Path(row.get("_source_results_csv", "")))
    dataset_sample = dataset_index.get(_dataset_lookup_key(dataset_id, sample_id))
    pred_source_path = _find_prediction_path(row, pred_roots)

    gt_image_path = (
        _find_image(gt_image_dir, sample_id, dataset_id=dataset_id) if gt_image_dir else _find_dataset_image(dataset_sample)
    )
    pred_image_path = _find_image(pred_image_dir, sample_id, candidate_id=candidate_id, dataset_id=dataset_id) if pred_image_dir else None

    ground_truth_image = _publish_asset(
        gt_image_path,
        out_json,
        asset_dir,
        category=f"references/{_safe_filename(dataset_id or 'dataset')}",
        filename=f"{_safe_filename(sample_id)}{gt_image_path.suffix.lower()}" if gt_image_path else None,
    )
    candidate_image = _publish_asset(
        pred_image_path,
        out_json,
        asset_dir,
        category=f"candidates/{_safe_filename(dataset_id or 'dataset')}/{_safe_filename(candidate_id)}",
        filename=f"{_safe_filename(sample_id)}{pred_image_path.suffix.lower()}" if pred_image_path else None,
    )

    if not candidate_image and render_candidates and pred_source_path:
        rendered = _render_candidate(pred_source_path, out_json, asset_dir, dataset_id, candidate_id, sample_id)
        candidate_image = rendered or ""

    gt_source_path = Path(row["gt_path"]) if row.get("gt_path") else dataset_sample.reference_path if dataset_sample else None
    sample = {
        "sample_id": sample_id,
        "candidate_id": candidate_id,
        "dataset_id": dataset_id,
        "workflow": row.get("workflow", ""),
        "model_id": row.get("model_id", ""),
        "title": f"{sample_id} / {candidate_id}",
        "ground_truth_image": ground_truth_image,
        "candidate_image": candidate_image,
        "pred_path": str(pred_source_path or row.get("pred_path", "")),
        "gt_path": str(gt_source_path or row.get("gt_path", "")),
        "project_context": _project_context(dataset_sample),
        "pred_source": _read_text(pred_source_path),
        "gt_source": _read_text(gt_source_path),
        "model_scores": _model_scores(row),
        "metrics": _metrics(row),
        "raw_result": {key: value for key, value in row.items() if not key.startswith("_")},
    }
    return sample


def _model_scores(row: Dict[str, str]) -> Dict[str, Dict[str, str]]:
    scores: Dict[str, Dict[str, str]] = {}
    for dimension in DIMENSIONS:
        key = dimension["id"]
        scores[key] = {
            "score": row.get(f"l2_{key}_score", ""),
            "reasoning": row.get(f"l2_{key}_reasoning", ""),
        }
    return scores


def _metrics(row: Dict[str, str]) -> Dict[str, str]:
    keys = [
        "stage_status",
        "l0_valid",
        "l0_node_count",
        "l0_edge_count",
        "l1_node_coverage",
        "l1_gen_precision",
        "l1_edge_f1",
        "l1_boundary_accuracy",
        "l1_ged_accuracy",
        "l2_status",
        "l2_requirement_coverage",
        "l2_asr_coverage",
        "l2_unsupported_inference_rate",
    ]
    return {key: row.get(key, "") for key in keys}


def _project_context(sample: Optional[DatasetSample]) -> Dict[str, str]:
    requirements_path = sample.requirements_path if sample else None
    text = _read_text(requirements_path)
    if not text:
        return {
            "introduction": "",
            "functional_requirements": "",
            "asr": "",
            "source_path": str(requirements_path or ""),
        }

    introduction = _extract_markdown_section(text, ["introduction", "system introduction"])
    if not introduction:
        introduction = _extract_markdown_section(text, ["purpose", "product scope"])

    functional_requirements = _extract_functional_requirements_context(text)
    return {
        "introduction": _clip_context(introduction or text),
        "functional_requirements": _clip_context(functional_requirements),
        "asr": _clip_context(functional_requirements),
        "source_path": str(requirements_path or ""),
    }


def _extract_functional_requirements_context(text: str) -> str:
    return _extract_markdown_section(
        text,
        [
            "functional requirements",
            "functional requirement",
            "functional features",
            "functional feature",
            "functionality requirements",
            "功能需求",
            "功能性需求",
        ],
        include_heading=True,
        exclude_keywords=["non-functional", "non functional", "nonfunctional", "非功能"],
    )


def _extract_markdown_section(
    text: str,
    keywords: Sequence[str],
    *,
    include_heading: bool = False,
    exclude_keywords: Sequence[str] = (),
) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue
        title = match.group(2).casefold()
        if any(keyword.casefold() in title for keyword in exclude_keywords):
            continue
        if not any(keyword.casefold() in title for keyword in keywords):
            continue
        level = len(match.group(1))
        start = index if include_heading else index + 1
        end = len(lines)
        for next_index in range(index + 1, len(lines)):
            next_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", lines[next_index])
            if next_match and len(next_match.group(1)) <= level:
                end = next_index
                break
        return "\n".join(lines[start:end]).strip()
    return ""


def _clip_context(text: str, max_chars: int = MAX_CONTEXT_CHARS) -> str:
    normalized = text.strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 16].rstrip() + "\n...[truncated]"


def _build_dataset_index(dataset_dirs: Sequence[Path]) -> Dict[str, DatasetSample]:
    index: Dict[str, DatasetSample] = {}
    for dataset_dir in dataset_dirs:
        dataset_id = Path(dataset_dir).name
        for sample in build_dataset_index(Path(dataset_dir)).values():
            index[_dataset_lookup_key(dataset_id, sample.sample_id)] = sample
    return index


def _find_dataset_image(sample: Optional[DatasetSample]) -> Optional[Path]:
    if not sample:
        return None
    candidates = []
    for suffix in IMAGE_SUFFIXES:
        candidates.append(sample.project_dir / "AD" / f"ad{suffix}")
        candidates.append(sample.project_dir / "AD" / f"architecture_diagram{suffix}")
    return _first_existing(candidates)


def _find_image(
    image_dir: Optional[Path],
    sample_id: str,
    *,
    candidate_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
) -> Optional[Path]:
    if not image_dir:
        return None
    for path in _candidate_image_paths(Path(image_dir), sample_id, candidate_id=candidate_id, dataset_id=dataset_id):
        if path.exists():
            return path
    return None


def _candidate_image_paths(
    image_dir: Path,
    sample_id: str,
    *,
    candidate_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
) -> Iterable[Path]:
    safe_candidate = _safe_filename(candidate_id or "")
    safe_dataset = _safe_filename(dataset_id or "")
    for suffix in IMAGE_SUFFIXES:
        yield image_dir / f"{sample_id}{suffix}"
        yield image_dir / sample_id / f"{sample_id}{suffix}"
        if dataset_id:
            yield image_dir / safe_dataset / f"{sample_id}{suffix}"
            yield image_dir / safe_dataset / sample_id / f"{sample_id}{suffix}"
        if candidate_id:
            yield image_dir / safe_candidate / f"{sample_id}{suffix}"
            yield image_dir / sample_id / f"{safe_candidate}{suffix}"
            yield image_dir / f"{safe_candidate}__{sample_id}{suffix}"
            if dataset_id:
                yield image_dir / safe_dataset / safe_candidate / f"{sample_id}{suffix}"
                yield image_dir / safe_dataset / sample_id / f"{safe_candidate}{suffix}"


def _find_prediction_path(row: Dict[str, str], pred_roots: Sequence[Path]) -> Optional[Path]:
    sample_id = row.get("sample_id") or ""
    candidate_id = row.get("candidate_id") or ""
    dataset_id = row.get("dataset_id") or ""
    workflow = row.get("workflow") or _candidate_part(candidate_id, 0)
    model_id = row.get("model_id") or _candidate_part(candidate_id, 1)

    if row.get("pred_path"):
        path = Path(row["pred_path"])
        if path.exists():
            return path

    for root in pred_roots:
        parts = [part for part in re.split(r"[\\/]+", candidate_id) if part]
        candidates = []
        for filename in PREDICTION_FILENAMES:
            if parts:
                candidates.append(Path(root, *parts, sample_id, filename))
                if dataset_id:
                    candidates.append(Path(root, dataset_id, *parts, sample_id, filename))
            if workflow and model_id:
                candidates.append(Path(root, workflow, model_id, sample_id, filename))
                if dataset_id:
                    candidates.append(Path(root, dataset_id, workflow, model_id, sample_id, filename))
        existing = _first_existing(candidates)
        if existing:
            return existing
    return None


def _render_candidate(
    pred_source_path: Path,
    out_json: Path,
    asset_dir: Optional[Path],
    dataset_id: str,
    candidate_id: str,
    sample_id: str,
) -> str:
    if not asset_dir:
        return ""
    command = _plantuml_command()
    if not command:
        return ""

    destination = (
        asset_dir
        / "candidates"
        / _safe_filename(dataset_id or "dataset")
        / _safe_filename(candidate_id or "candidate")
        / f"{_safe_filename(sample_id)}.svg"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ma4sa_review_render_") as tmp:
        output_dir = Path(tmp) / "out"
        output_dir.mkdir()
        result = _run_plantuml_render(command, pred_source_path, output_dir, 60)
        if result.returncode != 0:
            return ""
        rendered = output_dir / f"{pred_source_path.stem}.svg"
        if not rendered.exists():
            matches = sorted(output_dir.glob("*.svg"))
            rendered = matches[0] if matches else rendered
        if rendered.exists():
            shutil.copy2(rendered, destination)
            return _relative_uri(destination, out_json.parent)
    return ""


def _publish_asset(
    path: Optional[Path],
    out_json: Path,
    asset_dir: Optional[Path],
    *,
    category: str,
    filename: Optional[str],
) -> str:
    if not path:
        return ""
    path = Path(path)
    if not path.exists():
        return ""
    if not asset_dir:
        return path.resolve().as_uri()

    destination = asset_dir / category / (filename or path.name)
    if path.resolve() == destination.resolve():
        return _relative_uri(destination, out_json.parent)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    return _relative_uri(destination, out_json.parent)


def _relative_uri(path: Path, base_dir: Path) -> str:
    return Path(os.path.relpath(Path(path).resolve(), Path(base_dir).resolve())).as_posix()


def _read_text(path: Optional[Path]) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _first_existing(candidates: Iterable[Path]) -> Optional[Path]:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _infer_dataset_id(path: Path) -> str:
    text = str(path).casefold()
    if "c-r2a-17" in text or "c_r2a_17" in text:
        return "C-R2A-17"
    if "g-r2a-52" in text or "g_r2a_52" in text:
        return "G-R2A-52"
    return ""


def _dataset_lookup_key(dataset_id: str, sample_id: str) -> str:
    return f"{dataset_id.casefold()}::{sample_id.casefold()}"


def _candidate_part(candidate_id: str, index: int) -> str:
    parts = [part for part in re.split(r"[\\/]+", candidate_id or "") if part]
    return parts[index] if len(parts) > index else ""


def _truthy_or_blank(value: object) -> bool:
    if value in {None, ""}:
        return True
    return str(value).strip().casefold() in {"true", "1", "yes", "y", "t"}


def _safe_filename(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "item").strip("._")
    return text or "item"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare human-review samples for the evaluation frontend.")
    parser.add_argument("--results", type=Path, nargs="+", required=True, help="One or more evaluation CSV files.")
    parser.add_argument("--out", type=Path, default=Path("evaluation_script/frontend/samples.json"), help="Output samples JSON.")
    parser.add_argument("--n", type=int, default=20, help="Number of candidate diagrams to draw.")
    parser.add_argument("--seed", type=int, default=13, help="Random seed.")
    parser.add_argument(
        "--strategy",
        choices=["random", "stratified"],
        default="random",
        help="Sampling strategy. stratified balances dataset/workflow/model strata.",
    )
    parser.add_argument("--gt-image-dir", type=Path, default=None, help="Optional reference rendered-image directory.")
    parser.add_argument("--pred-image-dir", type=Path, default=None, help="Optional candidate rendered-image directory.")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        action="append",
        default=[],
        help="Dataset root used to find reference diagrams/images. Repeat for multiple datasets.",
    )
    parser.add_argument(
        "--pred-root",
        type=Path,
        action="append",
        default=[],
        help="Prediction root used to locate candidate predicted.puml files. Repeat for multiple roots.",
    )
    parser.add_argument(
        "--asset-dir",
        type=Path,
        default=None,
        help="Optional frontend asset directory. Images rendered/copied here use deployable relative URLs.",
    )
    parser.add_argument(
        "--render-candidates",
        action="store_true",
        help="Render selected candidate PlantUML files to SVG in --asset-dir when possible.",
    )
    parser.add_argument(
        "--allow-missing-candidate-image",
        action="store_true",
        help="Keep selected rows even when candidate images are missing. By default, rows without candidate images are skipped when --pred-image-dir or --render-candidates is used.",
    )
    args = parser.parse_args()

    payload = prepare_review_samples(
        args.results,
        args.out,
        sample_size=args.n,
        seed=args.seed,
        gt_image_dir=args.gt_image_dir,
        pred_image_dir=args.pred_image_dir,
        strategy=args.strategy,
        dataset_dirs=args.dataset_dir,
        pred_roots=args.pred_root,
        asset_dir=args.asset_dir,
        render_candidates=args.render_candidates,
        require_candidate_image=False if args.allow_missing_candidate_image else None,
    )
    print(f"Wrote {len(payload['samples'])} review samples to {args.out}")


if __name__ == "__main__":
    main()
