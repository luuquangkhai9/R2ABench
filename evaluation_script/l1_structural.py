from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from .plantuml_parser import ParsedDiagram, PlantUMLParser
except ImportError:  # Allows `python evaluation_script/l1_structural.py ...`.
    from plantuml_parser import ParsedDiagram, PlantUMLParser


@dataclass
class L1AlignmentConfig:
    enabled: bool = False
    model: Optional[str] = None
    base_url: str = "https://api.chatanywhere.tech/v1"
    api_key: Optional[str] = None
    timeout_seconds: int = 600

    @classmethod
    def from_env(
        cls,
        enabled: bool = False,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key_env: str = "OPENAI_API_KEY",
    ) -> "L1AlignmentConfig":
        return cls(
            enabled=enabled,
            model=model or os.environ.get("L1_JUDGE_MODEL") or os.environ.get("OPENAI_MODEL"),
            base_url=(base_url or os.environ.get("OPENAI_BASE_URL", "https://api.chatanywhere.tech/v1")).rstrip("/"),
            api_key=os.environ.get(api_key_env),
        )


class L1AlignmentError(RuntimeError):
    """Raised when L1 cannot obtain a required node alignment."""


def evaluate_l1(
    predicted_puml: str,
    reference_puml: Optional[str] = None,
    *,
    requirements_text: Optional[str] = None,
    alignment_data: Optional[Dict[str, object]] = None,
    alignment_config: Optional[L1AlignmentConfig] = None,
    alignment_cache_path: Optional[Path] = None,
) -> Dict[str, object]:
    parser = PlantUMLParser()
    pred = parser.parse(predicted_puml)
    metrics = _intrinsic_metrics(pred)

    if not reference_puml:
        metrics.update(_empty_reference_metrics())
        metrics["l1_status"] = "skipped_no_reference"
        return metrics

    gt = parser.parse(reference_puml)
    if alignment_data is None:
        alignment_data, _, _ = _resolve_alignment_data(
            requirements_text=requirements_text,
            gt=gt,
            pred=pred,
            config=alignment_config or L1AlignmentConfig(),
            cache_path=alignment_cache_path,
        )

    node_coverage, gen_precision = _calculate_node_metrics(alignment_data)
    edge_precision, edge_recall, edge_f1 = _calculate_edge_metrics(
        alignment_data,
        gt_edges=gt.edges,
        pred_edges=pred.edges,
        gt_all_nodes=gt.nodes,
    )
    ged_report = _calculate_ged_and_accuracy(
        gt_nodes=gt.nodes,
        gt_edges=gt.edges,
        pred_nodes=pred.nodes,
        pred_edges=pred.edges,
        alignment_data=alignment_data,
    )

    metrics.update(
        {
            "l1_status": "completed",
            "l1_reference_node_count": len(gt.nodes),
            "l1_reference_edge_count": len(gt.edges),
            "l1_node_coverage": round(node_coverage, 4),
            "l1_gen_precision": round(gen_precision, 4),
            "l1_edge_precision": round(edge_precision, 4),
            "l1_edge_recall": round(edge_recall, 4),
            "l1_edge_f1": round(edge_f1, 4),
            "l1_boundary_accuracy": round(_calculate_boundary_accuracy(alignment_data), 4),
            "l1_ged_accuracy": ged_report["accuracy_score"],
            "l1_absolute_ged": ged_report["absolute_ged"],
            "l1_ged_missed_node_count": ged_report["missed_node_count"],
            "l1_ged_hallucinated_node_count": ged_report["hallucinated_node_count"],
            "l1_ged_boundary_error_count": ged_report["boundary_error_count"],
            "l1_ged_missing_edge_count": ged_report["missing_edge_count"],
            "l1_ged_hallucinated_edge_count": ged_report["hallucinated_edge_count"],
            "l1_matched_node_count": _count_matched_predicted_nodes(alignment_data),
            "l1_unmatched_predicted_node_count": _list_count(alignment_data.get("unmatched_predicted_nodes")),
            "l1_unmatched_reference_node_count": _list_count(alignment_data.get("unmatched_gt_nodes")),
        }
    )
    return metrics


def _empty_reference_metrics() -> Dict[str, object]:
    return {
        "l1_reference_node_count": None,
        "l1_reference_edge_count": None,
        "l1_node_coverage": None,
        "l1_gen_precision": None,
        "l1_edge_precision": None,
        "l1_edge_recall": None,
        "l1_edge_f1": None,
        "l1_boundary_accuracy": None,
        "l1_ged_accuracy": None,
        "l1_absolute_ged": None,
        "l1_ged_missed_node_count": None,
        "l1_ged_hallucinated_node_count": None,
        "l1_ged_boundary_error_count": None,
        "l1_ged_missing_edge_count": None,
        "l1_ged_hallucinated_edge_count": None,
        "l1_matched_node_count": None,
        "l1_unmatched_predicted_node_count": None,
        "l1_unmatched_reference_node_count": None,
    }


def _resolve_alignment_data(
    *,
    requirements_text: Optional[str],
    gt: ParsedDiagram,
    pred: ParsedDiagram,
    config: L1AlignmentConfig,
    cache_path: Optional[Path],
) -> Tuple[Dict[str, object], str, Optional[str]]:
    if cache_path and Path(cache_path).exists():
        try:
            return _read_alignment_cache(Path(cache_path)), "cache", None
        except Exception as exc:  # noqa: BLE001 - fall back but expose the issue.
            cache_error = f"cache_read_failed: {exc}"
        else:
            cache_error = None
    else:
        cache_error = None

    if config.enabled:
        if not config.model:
            raise L1AlignmentError(_alignment_error_message("missing judge model", cache_error))
        if not config.api_key:
            raise L1AlignmentError(_alignment_error_message("missing judge API key", cache_error))
        try:
            alignment = _call_alignment_judge(
                prd_summary=requirements_text or "",
                gt_nodes=_alignment_candidates(gt),
                predicted_nodes=_alignment_candidates(pred),
                config=config,
            )
            if cache_path:
                _write_alignment_cache(Path(cache_path), alignment)
            return alignment, "judge", None
        except Exception as exc:  # noqa: BLE001 - preserve batch evaluation.
            error = f"judge_failed: {exc}"
            if cache_error:
                error = f"{cache_error} | {error}"
            raise L1AlignmentError(error) from exc

    raise L1AlignmentError(
        _alignment_error_message("missing alignment cache and judge is disabled", cache_error)
    )


def _alignment_error_message(reason: str, cache_error: Optional[str] = None) -> str:
    message = (
        f"L1 alignment required but unavailable: {reason}. "
        "Provide alignment_data, a readable alignment cache in the prediction directory, "
        "or enable the judge with a model and API key."
    )
    if cache_error:
        return f"{cache_error} | {message}"
    return message


def _alignment_candidates(parsed: ParsedDiagram) -> List[str]:
    component_like_types = {"component", "database", "queue", "cloud", "node", "rectangle", "interface"}
    candidates = set(parsed.leaf_nodes or parsed.nodes)
    for node, node_type in parsed.node_types.items():
        if node_type.lower() in component_like_types:
            candidates.add(node)
    return sorted(candidates)


def _intrinsic_metrics(parsed: ParsedDiagram) -> Dict[str, object]:
    leaf_nodes = parsed.leaf_nodes or parsed.nodes
    degree = {node: 0 for node in leaf_nodes}
    leaf_set = set(leaf_nodes)
    for src, dst in parsed.edges:
        if src in leaf_set:
            degree[src] += 1
        if dst in leaf_set:
            degree[dst] += 1

    orphan_ratio = 0.0
    god_ratio = 0.0
    if degree:
        orphan_ratio = sum(1 for value in degree.values() if value == 0) / len(degree)
        values = list(degree.values())
        if len(values) > 1:
            mean = sum(values) / len(values)
            variance = sum((value - mean) ** 2 for value in values) / len(values)
            threshold = mean + 2 * (variance**0.5)
            god_ratio = sum(1 for value in values if value > threshold and value > 2) / len(values)

    return {
        "l1_predicted_node_count": len(parsed.nodes),
        "l1_predicted_edge_count": len(parsed.edges),
        "l1_orphan_ratio": round(orphan_ratio, 4),
        "l1_god_ratio": round(god_ratio, 4),
    }


def _calculate_node_metrics(alignment_data: Dict[str, object]) -> Tuple[float, float]:
    reference_scan = alignment_data.get("reference_node_coverage")
    generated_scan = alignment_data.get("predicted_node_grounding")

    if isinstance(reference_scan, list):
        reference_total = sum(1 for item in reference_scan if isinstance(item, dict))
        reference_covered = sum(
            1 for item in reference_scan if isinstance(item, dict) and bool(item.get("covered"))
        )
    else:
        matched_gt_nodes = _matched_gt_node_set(alignment_data)
        reference_covered = len(matched_gt_nodes)
        reference_total = reference_covered + _list_count(alignment_data.get("unmatched_gt_nodes"))

    if isinstance(generated_scan, list):
        generated_total = sum(1 for item in generated_scan if isinstance(item, dict))
        generated_grounded = sum(
            1 for item in generated_scan if isinstance(item, dict) and bool(item.get("grounded"))
        )
    else:
        matched_predicted_nodes = _matched_predicted_node_set(alignment_data)
        generated_grounded = len(matched_predicted_nodes)
        generated_total = generated_grounded + _list_count(alignment_data.get("unmatched_predicted_nodes"))

    node_coverage = reference_covered / reference_total if reference_total else 0.0
    gen_precision = generated_grounded / generated_total if generated_total else 0.0
    return node_coverage, gen_precision


def _calculate_edge_metrics(
    alignment_data: Dict[str, object],
    gt_edges: List[Tuple[str, str]],
    pred_edges: List[Tuple[str, str]],
    gt_all_nodes: Optional[List[str]] = None,
) -> Tuple[float, float, float]:
    pred_to_gt_map: Dict[str, List[str]] = {}
    matched_pairs = alignment_data.get("matched_pairs", [])

    if isinstance(matched_pairs, list):
        for pair in matched_pairs:
            if not isinstance(pair, dict):
                continue
            gt_nodes = pair.get("gt_nodes", [])
            pred_nodes = pair.get("predicted_nodes", [])
            if isinstance(gt_nodes, list) and isinstance(pred_nodes, list):
                for pred_node in pred_nodes:
                    pred_to_gt_map[str(pred_node).replace("\n", "\\n")] = [str(node) for node in gt_nodes]

    gt_nodes_set = set(gt_all_nodes) if gt_all_nodes else set()

    def get_node_and_ancestors(node_name: str) -> set[str]:
        result = {node_name}
        parts = node_name.split("::")
        for index in range(1, len(parts)):
            prefix = "::".join(parts[:index])
            if prefix in gt_nodes_set:
                result.add(prefix)
            global_prefix = f"Global::{prefix}"
            if global_prefix in gt_nodes_set:
                result.add(global_prefix)
        return result

    gt_edges_set = set(gt_edges)
    tp_pred_edges = 0
    tp_gt_edges_covered = set()

    for src_p, dst_p in pred_edges:
        mapped_srcs = pred_to_gt_map.get(src_p, [])
        mapped_dsts = pred_to_gt_map.get(dst_p, [])
        is_edge_matched = False

        for g_src in mapped_srcs:
            if is_edge_matched:
                break
            src_candidates = get_node_and_ancestors(g_src)
            for g_dst in mapped_dsts:
                dst_candidates = get_node_and_ancestors(g_dst)
                for a_src in src_candidates:
                    for a_dst in dst_candidates:
                        if (a_src, a_dst) in gt_edges_set:
                            is_edge_matched = True
                            tp_gt_edges_covered.add((a_src, a_dst))
                            break
                    if is_edge_matched:
                        break
                if is_edge_matched:
                    break

        if is_edge_matched:
            tp_pred_edges += 1

    precision = tp_pred_edges / len(pred_edges) if len(pred_edges) > 0 else 0.0
    recall = len(tp_gt_edges_covered) / len(gt_edges) if len(gt_edges) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def _calculate_ged_and_accuracy(
    gt_nodes: List[str],
    gt_edges: List[Tuple[str, str]],
    pred_nodes: List[str],
    pred_edges: List[Tuple[str, str]],
    alignment_data: Dict[str, object],
) -> Dict[str, object]:
    weights = {
        "miss_node": 1.0,
        "hallu_node": 0.8,
        "contains_err": 2.0,
        "miss_dep": 1.0,
        "hallu_dep": 1.2,
    }
    matched_pairs = alignment_data.get("matched_pairs", [])
    gt_to_pred_map: Dict[str, set[str]] = {}
    pred_to_gt_map: Dict[str, set[str]] = {}
    mapped_gt_nodes = set()
    mapped_pred_nodes = set()
    boundary_errors_count = 0

    if isinstance(matched_pairs, list):
        for match in matched_pairs:
            if not isinstance(match, dict):
                continue
            preds = match.get("predicted_nodes", [])
            gts = match.get("gt_nodes", [])
            if not isinstance(preds, list) or not isinstance(gts, list):
                continue

            pred_targets = {str(pred).replace("\n", "\\n") for pred in preds}
            for gt in gts:
                gt_name = str(gt)
                mapped_gt_nodes.add(gt_name)
                if pred_targets:
                    gt_to_pred_map.setdefault(gt_name, set()).update(pred_targets)
                    mapped_pred_nodes.update(pred_targets)
                    for pred_target in pred_targets:
                        pred_to_gt_map.setdefault(pred_target, set()).add(gt_name)

            if not match.get("is_boundary_correct", False) and pred_targets:
                boundary_errors_count += len(gts)

    unmapped_gt = set(gt_nodes) - mapped_gt_nodes
    unmapped_pred = set(pred_nodes) - mapped_pred_nodes

    pred_edges_set = set(pred_edges)
    gt_edges_set = set(gt_edges)
    missing_depends = set()
    for src, dst in gt_edges:
        src_candidates = gt_to_pred_map.get(src, {src})
        dst_candidates = gt_to_pred_map.get(dst, {dst})
        if src_candidates & dst_candidates:
            continue
        if not any(
            (src_candidate, dst_candidate) in pred_edges_set
            for src_candidate in src_candidates
            for dst_candidate in dst_candidates
        ):
            missing_depends.add((src, dst))

    hallucinated_depends = set()
    for src, dst in pred_edges:
        src_candidates = pred_to_gt_map.get(src, {src})
        dst_candidates = pred_to_gt_map.get(dst, {dst})
        if not any(
            (src_candidate, dst_candidate) in gt_edges_set
            for src_candidate in src_candidates
            for dst_candidate in dst_candidates
        ):
            hallucinated_depends.add((src, dst))

    ged = (
        len(unmapped_gt) * weights["miss_node"]
        + len(unmapped_pred) * weights["hallu_node"]
        + boundary_errors_count * weights["contains_err"]
        + len(missing_depends) * weights["miss_dep"]
        + len(hallucinated_depends) * weights["hallu_dep"]
    )

    max_possible_ged = (
        len(gt_nodes) * weights["miss_node"]
        + len(pred_nodes) * weights["hallu_node"]
        + len(gt_nodes) * weights["contains_err"]
        + len(gt_edges) * weights["miss_dep"]
        + len(pred_edges) * weights["hallu_dep"]
    )
    accuracy_score = 100.0 if max_possible_ged == 0 else max(0.0, 100.0 * (1.0 - (ged / max_possible_ged)))
    return {
        "accuracy_score": round(accuracy_score, 2),
        "absolute_ged": round(ged, 2),
        "missed_node_count": len(unmapped_gt),
        "hallucinated_node_count": len(unmapped_pred),
        "boundary_error_count": boundary_errors_count,
        "missing_edge_count": len(missing_depends),
        "hallucinated_edge_count": len(hallucinated_depends),
    }


def _calculate_boundary_accuracy(alignment_data: Dict[str, object]) -> float:
    matched_pairs = alignment_data.get("matched_pairs", [])
    if not isinstance(matched_pairs, list) or not matched_pairs:
        return 0.0

    valid_pairs = [pair for pair in matched_pairs if isinstance(pair, dict)]
    if not valid_pairs:
        return 0.0

    correct_boundaries = sum(1 for pair in valid_pairs if pair.get("is_boundary_correct", False))
    return correct_boundaries / len(valid_pairs)


def _count_matched_predicted_nodes(alignment_data: Dict[str, object]) -> int:
    return len(_matched_predicted_node_set(alignment_data))


def _matched_gt_node_set(alignment_data: Dict[str, object]) -> set[str]:
    matched_pairs = alignment_data.get("matched_pairs", [])
    matched_nodes: set[str] = set()
    if isinstance(matched_pairs, list):
        for pair in matched_pairs:
            if isinstance(pair, dict) and isinstance(pair.get("gt_nodes"), list):
                matched_nodes.update(str(node) for node in pair["gt_nodes"])
    return matched_nodes


def _matched_predicted_node_set(alignment_data: Dict[str, object]) -> set[str]:
    matched_pairs = alignment_data.get("matched_pairs", [])
    matched_nodes: set[str] = set()
    if isinstance(matched_pairs, list):
        for pair in matched_pairs:
            if isinstance(pair, dict) and isinstance(pair.get("predicted_nodes"), list):
                matched_nodes.update(str(node).replace("\n", "\\n") for node in pair["predicted_nodes"])
    return matched_nodes


def _list_count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def _is_boundary_correct(pred_node: str, gt_node: str) -> bool:
    pred_parent = "::".join(pred_node.split("::")[:-1])
    gt_parent = "::".join(gt_node.split("::")[:-1])
    return PlantUMLParser.semantic_key(pred_parent) == PlantUMLParser.semantic_key(gt_parent)


def _prf(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def _read_alignment_cache(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_alignment_cache(path: Path, alignment_data: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(alignment_data, ensure_ascii=False, indent=2), encoding="utf-8")


def _alignment_cache_path_for_prediction(pred_path: Path, model: Optional[str]) -> Optional[Path]:
    if not model:
        return None
    return Path(pred_path).parent / f"judge_alignment_{_safe_filename(model)}.json"


def _safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value)


def _call_alignment_judge(
    *,
    prd_summary: str,
    gt_nodes: List[str],
    predicted_nodes: List[str],
    config: L1AlignmentConfig,
) -> Dict[str, object]:
    prompt = _build_alignment_prompt(prd_summary, gt_nodes, predicted_nodes)
    payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{config.base_url}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"alignment judge request failed: {exc.code} {detail}") from exc
    raw_content = body["choices"][0]["message"]["content"]
    return _parse_alignment_json(raw_content)


def _parse_alignment_json(raw_content: str) -> Dict[str, object]:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw_content, re.DOTALL | re.IGNORECASE)
    json_str = match.group(1) if match else raw_content
    return json.loads(json_str)


def _build_alignment_prompt(prd_summary: str, gt_nodes: List[str], predicted_nodes: List[str]) -> str:
    return (
        "You are a senior software architect. Your task now is to evaluate whether the AI-generated architecture "
        "diagram nodes and their layer/boundary attribution accurately reproduce the real manual design "
        "(Ground Truth).\n\n"
        'I will provide you with two lists of nodes (the format convention is "boundary/package name::node name"; '
        'if there is no boundary, it is "Global::node name"): one is a list of manually drawn standard nodes '
        "(GT Nodes), and the other is a list of nodes predicted by AI (Predicted Nodes). A system PRD will also "
        "be provided as context.\n\n"
        "[Your Task]\n"
        "Perform two independent node-level scans, then provide supporting semantic matches for edge and boundary "
        "evaluation.\n"
        "1. Reference-side coverage scan: for each GT node, decide whether one or more predicted nodes cover its "
        "responsibility.\n"
        "2. Generated-side grounding scan: for each predicted node, decide whether it corresponds to one or more "
        "GT concepts, or whether it is hallucinated.\n"
        "These two scans are independent 0/1 judgments. Do not compute a node F1 score.\n\n"
        "[Matching Rules - Very Important]\n"
        "1. Exact Matching (1:1): Nodes with different names but referring to the same component are considered "
        "a successful match.\n"
        "2. Split/Merged Matching (1:N or N:1) may be recorded in matched_pairs for edge/boundary evaluation:\n"
        "   - A single large node in the GT is split into multiple specific microservices by the AI, and they are "
        "mapped together.\n"
        "   - Multiple detailed nodes in the GT are aggregated into one node by the AI, and they are mapped together.\n"
        "3. Boundary/Layer Evaluation (Boundary Check):\n"
        '   - For successfully matched nodes, compare their "boundary/package names."\n'
        "   - For all package names of the node, if there is a case where they are different from the successfully "
        "matched GT node's package name but semantically equivalent (e.g., GT is "
        '"Backend::Data Layer::MySQL", AI is "Database::MySQL"), it is judged as `true`.\n'
        "   - If a severe boundary-crossing error or context confusion occurs (e.g., a service belonging to the "
        '"Order Context" in the GT is placed in the "User Context" by the AI, or a backend component is placed in '
        "a frontend package), it is judged as `false`.\n"
        "4. Unmatched Nodes: Nodes that are hallucinated by the AI or omitted, placed in the unmatched lists "
        "respectively.\n\n"
        "[Input Data]\n"
        f"PRD Background Description: {prd_summary}\n"
        f"GT Nodes: {json.dumps(gt_nodes, ensure_ascii=False)}\n"
        f"Predicted Nodes: {json.dumps(predicted_nodes, ensure_ascii=False)}\n\n"
        "[Output Format]\n"
        "Please output strictly in JSON format, without including any markdown code block markers or unnecessary "
        "explanations. The format is as follows:\n"
        "{\n"
        '  "reference_node_coverage": [\n'
        "    {\n"
        '      "gt_node": "Backend::Login Service",\n'
        '      "covered": true,\n'
        '      "covering_predicted_nodes": ["Gateway::Auth Center"],\n'
        '      "reasoning": "The predicted auth component covers the login responsibility."\n'
        "    },\n"
        "    {\n"
        '      "gt_node": "Global::Payment API",\n'
        '      "covered": false,\n'
        '      "covering_predicted_nodes": [],\n'
        '      "reasoning": "No generated node covers this payment responsibility."\n'
        "    }\n"
        "  ],\n"
        '  "predicted_node_grounding": [\n'
        "    {\n"
        '      "predicted_node": "Gateway::Auth Center",\n'
        '      "grounded": true,\n'
        '      "reference_nodes": ["Backend::Login Service", "Backend::Register Service"],\n'
        '      "reasoning": "The component is grounded in the reference authentication concepts."\n'
        "    },\n"
        "    {\n"
        '      "predicted_node": "Frontend::Vue Router",\n'
        '      "grounded": false,\n'
        '      "reference_nodes": [],\n'
        '      "reasoning": "The reference architecture does not include this component."\n'
        "    }\n"
        "  ],\n"
        '  "matched_pairs": [\n'
        "    {\n"
        '      "gt_nodes": ["Backend::Auth Service"],\n'
        '      "predicted_nodes": ["Gateway::Auth Center"],\n'
        '      "match_type": "1:1",\n'
        '      "is_boundary_correct": false,\n'
        '      "reasoning": "The functionality matches, but the boundary is incorrect."\n'
        "    },\n"
        "    {\n"
        '      "gt_nodes": ["Data Layer::User DB"],\n'
        '      "predicted_nodes": ["Database::MySQL_User", "Database::Redis_User"],\n'
        '      "match_type": "1:N",\n'
        '      "is_boundary_correct": true,\n'
        '      "reasoning": "The GT storage node is split into finer components, but the database boundary '
        'attribution is semantically consistent."\n'
        "    }\n"
        "  ],\n"
        '  "unmatched_gt_nodes": ["Global::Payment API"],\n'
        '  "unmatched_predicted_nodes": ["Frontend::Vue Router"]\n'
        "}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MA4SA L1 structural architecture evaluation.")
    parser.add_argument("--pred", type=Path, required=True, help="Predicted PlantUML file.")
    parser.add_argument("--gt", "--reference", dest="reference_path", type=Path, help="Ground-truth PlantUML file.")
    parser.add_argument(
        "--requirements",
        "--requirements-path",
        dest="requirements_path",
        type=Path,
        help="Optional requirements/PRD/SRS text file used as judge context.",
    )
    parser.add_argument(
        "--alignment-cache",
        type=Path,
        default=None,
        help="Optional explicit alignment JSON path. Defaults to the prediction directory and model name.",
    )
    parser.add_argument("--out", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument("--enable-judge", action="store_true", help="Call an OpenAI-compatible L1 alignment judge.")
    parser.add_argument(
        "--llm-model",
        "--l1-judge-model",
        dest="model",
        default=None,
        help="Judge model name used for L1 and for judge_alignment_{model}.json.",
    )
    parser.add_argument("--llm-base-url", default=None, help="OpenAI-compatible base URL.")
    parser.add_argument("--llm-api-key-env", default="OPENAI_API_KEY", help="Environment variable containing API key.")
    args = parser.parse_args(argv)

    predicted_puml = args.pred.read_text(encoding="utf-8")
    reference_puml = args.reference_path.read_text(encoding="utf-8") if args.reference_path else None
    requirements_text = args.requirements_path.read_text(encoding="utf-8") if args.requirements_path else None
    config = L1AlignmentConfig.from_env(
        enabled=args.enable_judge,
        model=args.model,
        base_url=args.llm_base_url,
        api_key_env=args.llm_api_key_env,
    )
    alignment_cache_path = args.alignment_cache or _alignment_cache_path_for_prediction(args.pred, config.model)

    try:
        result = evaluate_l1(
            predicted_puml,
            reference_puml,
            requirements_text=requirements_text,
            alignment_config=config,
            alignment_cache_path=alignment_cache_path,
        )
    except L1AlignmentError as exc:
        print(f"L1 alignment error: {exc}", file=sys.stderr)
        return 2
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
