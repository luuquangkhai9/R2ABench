from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, Optional


L2_DIMENSIONS = [
    "completeness",
    "faithfulness",
    "architectural_rationality",
    "traceability",
    "readability",
]


@dataclass
class L2JudgeConfig:
    enabled: bool = False
    model: str = "gemini-2.5-pro"
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
    ) -> "L2JudgeConfig":
        return cls(
            enabled=enabled,
            model=model or os.environ.get("OPENAI_MODEL", "gemini-2.5-pro"),
            base_url=(base_url or os.environ.get("OPENAI_BASE_URL", "https://api.chatanywhere.tech/v1")).rstrip("/"),
            api_key=os.environ.get(api_key_env),
        )


def empty_l2_result(status: str) -> Dict[str, object]:
    result: Dict[str, object] = {"l2_status": status}
    for dimension in L2_DIMENSIONS:
        result[f"l2_{dimension}_score"] = None
        result[f"l2_{dimension}_reasoning"] = None
    result.update(
        {
            "l2_requirement_coverage": None,
            "l2_asr_coverage": None,
            "l2_unsupported_inference_rate": None,
            "l2_raw_json": None,
        }
    )
    return result


def evaluate_l2(requirements_text: Optional[str], predicted_puml: str, config: L2JudgeConfig) -> Dict[str, object]:
    if not config.enabled:
        return empty_l2_result("skipped_disabled")
    if not config.api_key:
        return empty_l2_result("skipped_missing_api_key")
    if not requirements_text:
        return empty_l2_result("skipped_missing_requirements")

    prompt = _build_prompt(requirements_text, predicted_puml)
    try:
        raw = _chat_completion(prompt, config)
        parsed = _parse_json(raw)
        return _flatten_l2(parsed)
    except Exception as exc:  # noqa: BLE001 - surfaced in CSV for batch runs.
        result = empty_l2_result("failed")
        result["l2_error"] = str(exc)
        return result


def _build_prompt(requirements_text: str, predicted_puml: str) -> str:
    return f"""You are a senior software architect and an impartial evaluator.

Evaluate the generated architecture diagram using an ATAM-inspired protocol.
Focus on requirements-to-architecture reasoning, ASR coverage, traceability,
and unsupported inferences. Do not reward visual similarity to a reference
diagram.
Before scoring, list concrete defects in the relevant reasoning fields. If no
concrete evidence supports an architectural element, penalize faithfulness and
traceability.

Return strict JSON only, with this schema:
{{
  "scores": {{
    "completeness": {{"score": 1, "reasoning": "..."}},
    "faithfulness": {{"score": 1, "reasoning": "..."}},
    "architectural_rationality": {{"score": 1, "reasoning": "..."}},
    "traceability": {{"score": 1, "reasoning": "..."}},
    "readability": {{"score": 1, "reasoning": "..."}}
  }},
  "metrics": {{
    "requirement_coverage": 0.0,
    "asr_coverage": 0.0,
    "unsupported_inference_rate": 0.0
  }}
}}

Use the full 1--5 scale strictly. Scores must be integers. Before assigning
each score, identify concrete defects in that dimension; if the reasoning
does not name specific evidence from the requirements and diagram, do not
assign a 5.

General scoring rubric for every dimension:
- 5: Strong. No major missing requirements, no incorrect architectural
  boundaries, no unsupported components or relations, and trace IDs/evidence
  links are all verifiable against the requirements.
- 4: Good. Only minor omissions, minor ambiguity, or a small number of
  unsupported inferences; the main architecture remains evidence-supported.
- 3: Partially acceptable. The diagram covers the main requirements, but has
  clear omissions, boundary mistakes, weak traceability, or several unsupported
  assumptions.
- 2: Weak. Multiple important requirements are missing, architectural
  relations or deployment/runtime boundaries are often wrong, or many elements
  are unsupported by the requirements.
- 1: Poor. The diagram is largely inconsistent with the requirements, models a
  different system, or provides little usable requirements-to-architecture
  reasoning.

Apply these additional dimension-specific checks:
- Completeness: penalize missing functional requirements, quality drivers,
  ASRs, external systems, data stores, or deployment/runtime concerns that are
  explicit in the requirements.
- Faithfulness: penalize components, technologies, relations, protocols,
  constraints, or assumptions that are not supported by the requirements, even
  if they look plausible.
- Architectural rationality: penalize incorrect abstraction level, misplaced
  responsibilities, wrong dependencies, poor separation of concerns, or
  architecture decisions that do not address quality attributes.
- Traceability: verify that cited requirement IDs actually exist and support
  the linked element. Penalize hallucinated IDs, vague trace labels, and
  elements without evidence.
- Readability: penalize clutter, misleading grouping, inconsistent notation,
  ambiguous labels, overly flat diagrams, and diagrams that are syntactically
  valid but hard to audit.

<REQUIREMENTS>
{requirements_text}
</REQUIREMENTS>

<PREDICTED_PLANTUML>
{predicted_puml}
</PREDICTED_PLANTUML>
"""


def _chat_completion(prompt: str, config: L2JudgeConfig) -> str:
    payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
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
        raise RuntimeError(f"judge request failed: {exc.code} {detail}") from exc
    return body["choices"][0]["message"]["content"]


def _parse_json(raw: str) -> Dict[str, object]:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    text = match.group(1) if match else raw
    return json.loads(text)


def _flatten_l2(parsed: Dict[str, object]) -> Dict[str, object]:
    result = empty_l2_result("completed")
    scores = parsed.get("scores", {}) if isinstance(parsed, dict) else {}
    for dimension in L2_DIMENSIONS:
        item = scores.get(dimension, {}) if isinstance(scores, dict) else {}
        if isinstance(item, dict):
            result[f"l2_{dimension}_score"] = item.get("score")
            result[f"l2_{dimension}_reasoning"] = item.get("reasoning")

    metrics = parsed.get("metrics", {}) if isinstance(parsed, dict) else {}
    if isinstance(metrics, dict):
        result["l2_requirement_coverage"] = metrics.get("requirement_coverage")
        result["l2_asr_coverage"] = metrics.get("asr_coverage")
        result["l2_unsupported_inference_rate"] = metrics.get("unsupported_inference_rate")

    result["l2_raw_json"] = json.dumps(parsed, ensure_ascii=False)
    return result
