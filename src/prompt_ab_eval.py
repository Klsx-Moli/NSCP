"""Reproducible A/B evaluation: raw request vs. NSCP-compiled prompt.

The harness is intentionally split into stages so it can run in offline or
restricted environments:

1. ``prepare`` compiles every case with the real NSCP service and writes the
   generation requests (baseline arm = raw user input, treatment arm =
   compiled prompt).
2. Any HTTP executor posts those request files to an OpenAI-compatible
   endpoint and stores the responses. ``execute`` is included for normal
   environments; restricted environments can use any external executor.
3. ``judge`` builds blind pairwise judge requests (both A/B orders).
4. ``report`` parses the judge JSON, maps scores back to the arms, runs
   deterministic checks, and writes ``report.md`` + ``report.json``.

No API key is ever written to disk. Model output is never used to compute
the deterministic checks for the other arm.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from npsc_service import CompileRequest, compile_prompt

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "tools" / "ab_eval" / "cases.json"
DEFAULT_RUN_ROOT = Path(__file__).resolve().parents[1] / "outputs" / "ab_eval"
DIMENSIONS = (
    "requirement_coverage",
    "constraint_compliance",
    "deliverable_quality",
    "structure_clarity",
    "verification",
    "non_invention",
    "overall",
)
SCORE_ABBREVIATIONS = {
    "requirement_coverage": "req",
    "constraint_compliance": "con",
    "deliverable_quality": "del",
    "structure_clarity": "str",
    "verification": "ver",
    "non_invention": "inv",
    "overall": "all",
}


# ─── IO helpers ─────────────────────────────────────────────────────────────

def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ─── case loading and preparation ──────────────────────────────────────────

def load_cases(path: str | Path | None = None) -> list[dict[str, Any]]:
    payload = read_json(path or DEFAULT_CASES)
    cases = payload.get("cases", payload)
    if not isinstance(cases, list) or not cases:
        raise ValueError("case file must contain a non-empty 'cases' list")
    for case in cases:
        for key in ("id", "input"):
            if not case.get(key):
                raise ValueError(f"case is missing required key '{key}': {case!r}")
    return cases


def _compiler_metadata(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "target": result.get("target"),
        "requested_profile": result.get("requested_profile"),
        "applied_profile": result.get("applied_profile"),
        "chosen_level": result.get("chosen_level"),
        "quality_report": result.get("quality_report"),
        "context_loss": {
            "score": result.get("context_loss_report", {}).get("score"),
            "critical_losses": result.get("context_loss_report", {}).get("critical_losses"),
            "warnings": result.get("context_loss_report", {}).get("warnings"),
        },
        "prompt_sha256": result.get("prompt_sha256"),
    }


def _generation_request(
    case: dict[str, Any],
    arm: str,
    prompt: str,
    run_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "request_id": f"{case['id']}__{arm}",
        "case_id": case["id"],
        "arm": arm,
        "endpoint": "/chat/completions",
        "body": {
            "model": run_config["generator_model"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": run_config["generator_max_tokens"],
            "temperature": run_config["generator_temperature"],
        },
    }


def prepare_run(
    cases: list[dict[str, Any]],
    run_dir: str | Path,
    run_config: dict[str, Any],
) -> dict[str, Any]:
    run_path = Path(run_dir)
    arms: dict[str, Any] = {}
    requests: list[dict[str, Any]] = []

    for case in cases:
        result = compile_prompt(
            CompileRequest(
                original=case["input"],
                target=case.get("target", "generic"),
                profile=case.get("profile", "STANDARD"),
            )
        )
        baseline = case["input"].strip()
        treatment = str(result["optimized_prompt"]).strip()
        arms[case["id"]] = {
            "id": case["id"],
            "language": case.get("language", "auto"),
            "task_type": case.get("task_type", "general"),
            "baseline_prompt": baseline,
            "treatment_prompt": treatment,
            "baseline_sha256": sha256_text(baseline),
            "treatment_sha256": sha256_text(treatment),
            "compiler": _compiler_metadata(result),
        }
        requests.append(_generation_request(case, "baseline", baseline, run_config))
        requests.append(_generation_request(case, "treatment", treatment, run_config))

    write_json(run_path / "arms.json", arms)
    write_json(run_path / "manifest.json", {
        "schema": "npsc.ab_eval.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_config": run_config,
        "case_ids": [c["id"] for c in cases],
        "stages": ["prepare"],
    })
    for request in requests:
        write_json(run_path / "requests" / "generation" / f"{request['request_id']}.json", request)
    return {"run_dir": str(run_path), "requests": len(requests), "cases": len(cases)}


# ─── response extraction ────────────────────────────────────────────────────

def _extract_content(response_payload: Any) -> str:
    if not isinstance(response_payload, dict):
        return ""
    if response_payload.get("ok") is False:
        return ""
    response = response_payload.get("response", response_payload)
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if content is None:
        content = choices[0].get("text")
    if isinstance(content, list):
        return "".join(
            str(part.get("text", "")) if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content or "")


def _response_path(run_path: Path, request_id: str) -> Path:
    return run_path / "responses" / "generation" / f"{request_id}.response.json"


def _judge_response_path(run_path: Path, request_id: str) -> Path:
    return run_path / "responses" / "judge" / f"{request_id}.response.json"


def _load_arm_outputs(run_path: Path, arms: dict[str, Any]) -> dict[str, dict[str, str]]:
    outputs: dict[str, dict[str, str]] = {}
    for case_id in arms:
        outputs[case_id] = {}
        for arm in ("baseline", "treatment"):
            path = _response_path(run_path, f"{case_id}__{arm}")
            if path.exists():
                outputs[case_id][arm] = _extract_content(read_json(path))
            else:
                outputs[case_id][arm] = ""
    return outputs


# ─── judge requests ────────────────────────────────────────────────────────

JUDGE_RUBRIC = """You are an impartial evaluator. Compare two assistant responses (A and B) to the SAME user request.

Evaluate each response independently on these dimensions, 0-10:
1. requirement_coverage: fulfills the explicit and clearly implied requirements.
2. constraint_compliance: respects every stated constraint and non-goal.
3. deliverable_quality: provides a concrete, usable deliverable of the requested kind.
4. structure_clarity: organized and easy to act on.
5. verification: includes tests, checks, acceptance criteria, or a clear way to verify success.
6. non_invention: avoids inventing requirements or facts not supported by the request; marks assumptions explicitly.
7. overall: overall usefulness to the user.

Rules:
- Judge only against the user request. Do not prefer a response for being longer or more detailed.
- A response that misses a stated constraint must score low on constraint_compliance even if it is otherwise good.
- A response that claims to have created files or run tests, without showing the actual code and test output, must score low on non_invention and deliverable_quality.
- Use the full 0-10 range.
"""

JUDGE_OUTPUT_SHAPE = (
    'Return ONLY valid JSON, no markdown fences, in exactly this shape: '
    '{"A":{"requirement_coverage":0,"constraint_compliance":0,"deliverable_quality":0,'
    '"structure_clarity":0,"verification":0,"non_invention":0,"overall":0},'
    '"B":{"requirement_coverage":0,"constraint_compliance":0,"deliverable_quality":0,'
    '"structure_clarity":0,"verification":0,"non_invention":0,"overall":0},'
    '"winner":"A|B|tie","rationale":"one or two sentences"}'
)


def build_judge_prompt(
    case: dict[str, Any],
    response_a: str,
    response_b: str,
) -> str:
    key_requirements = "\n".join(
        f"- {item}" for item in case.get("key_requirements", [])
    ) or "- (none declared)"
    return (
        f"{JUDGE_RUBRIC}\n"
        "Case-specific requirements that MUST be respected:\n"
        f"{key_requirements}\n\n"
        "USER REQUEST (verbatim):\n"
        "<request>\n"
        f"{case['input']}\n"
        "</request>\n\n"
        "RESPONSE A:\n"
        "<response_a>\n"
        f"{response_a}\n"
        "</response_a>\n\n"
        "RESPONSE B:\n"
        "<response_b>\n"
        f"{response_b}\n"
        "</response_b>\n\n"
        f"{JUDGE_OUTPUT_SHAPE}"
    )


def build_judge_requests(
    cases: list[dict[str, Any]],
    run_dir: str | Path,
    run_config: dict[str, Any],
) -> dict[str, Any]:
    run_path = Path(run_dir)
    arms = read_json(run_path / "arms.json")
    outputs = _load_arm_outputs(run_path, arms)
    mapping: dict[str, Any] = {}
    count = 0
    missing: list[str] = []

    for case in cases:
        case_id = case["id"]
        baseline = outputs[case_id]["baseline"]
        treatment = outputs[case_id]["treatment"]
        if not baseline or not treatment:
            missing.append(case_id)
            continue
        for order in (0, 1):
            response_a = baseline if order == 0 else treatment
            response_b = treatment if order == 0 else baseline
            request_id = f"{case_id}__order{order}"
            request = {
                "request_id": request_id,
                "case_id": case_id,
                "order": order,
                "endpoint": "/chat/completions",
                "body": {
                    "model": run_config["judge_model"],
                    "messages": [{
                        "role": "user",
                        "content": build_judge_prompt(case, response_a, response_b),
                    }],
                    "max_tokens": run_config["judge_max_tokens"],
                    "temperature": 0,
                },
            }
            mapping[request_id] = {
                "case_id": case_id,
                "order": order,
                "a_arm": "baseline" if order == 0 else "treatment",
                "b_arm": "treatment" if order == 0 else "baseline",
            }
            write_json(run_path / "requests" / "judge" / f"{request_id}.json", request)
            count += 1

    write_json(run_path / "judge_map.json", mapping)
    return {"requests": count, "missing_generations": missing}


# ─── judge parsing ─────────────────────────────────────────────────────────

def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _find_json_object(text: str) -> dict[str, Any] | None:
    stripped = _strip_code_fences(text)
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(stripped)):
        char = stripped[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = stripped[start:index + 1]
                try:
                    value = json.loads(candidate)
                    return value if isinstance(value, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


def _coerce_scores(payload: dict[str, Any] | None) -> dict[str, dict[str, float]] | None:
    if not payload:
        return None
    result: dict[str, dict[str, float]] = {}
    for side in ("A", "B"):
        side_payload = payload.get(side)
        if not isinstance(side_payload, dict):
            return None
        scores: dict[str, float] = {}
        for dimension in DIMENSIONS:
            try:
                scores[dimension] = float(side_payload[dimension])
            except (KeyError, TypeError, ValueError):
                return None
        result[side] = scores
    return result


def parse_judge_payload(text: str) -> dict[str, Any] | None:
    payload = _find_json_object(text)
    if payload is None:
        return None
    scores = _coerce_scores(payload)
    if scores is None:
        return None
    winner = str(payload.get("winner", "")).strip()
    if winner not in {"A", "B", "tie", "TIE", "a", "b"}:
        winner = "tie"
    winner = winner.lower() if winner.lower() in {"a", "b"} else "tie"
    return {
        "scores": scores,
        "winner": winner,
        "rationale": str(payload.get("rationale", "")).strip(),
    }


# ─── deterministic checks ──────────────────────────────────────────────────

_SPANISH_STOPWORDS = {
    "que", "de", "la", "el", "y", "en", "para", "con", "sin", "los", "las",
    "un", "una", "del", "se", "por", "es", "al", "lo", "como", "más",
}
_ENGLISH_STOPWORDS = {
    "the", "and", "to", "of", "in", "for", "with", "is", "are", "that", "on",
    "as", "be", "this", "it", "you", "a", "an", "or", "not", "do", "from",
}


def detect_language(text: str) -> str:
    words = re.findall(r"[a-záéíóúüñ]+", text.lower())
    spanish = sum(1 for word in words if word in _SPANISH_STOPWORDS)
    english = sum(1 for word in words if word in _ENGLISH_STOPWORDS)
    if spanish > english:
        return "es"
    if english > spanish:
        return "en"
    return "unknown"


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def _case_output_text(output: str) -> str:
    return output or ""


def run_deterministic_checks(case: dict[str, Any], output: str) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    text = _case_output_text(output)
    lowered = text.lower()
    spec = case.get("checks") or {}

    if spec.get("json_parse"):
        parsed = None
        stripped = text.strip()
        if stripped:
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
        checks["json_parse"] = {
            "passed": isinstance(parsed, (dict, list)),
            "detail": type(parsed).__name__ if parsed is not None else "invalid JSON",
        }

    if spec.get("contains_all"):
        missing = [item for item in spec["contains_all"] if item.lower() not in lowered]
        checks["contains_all"] = {"passed": not missing, "missing": missing}

    if spec.get("contains_any"):
        groups = spec["contains_any"]
        missing_groups = []
        for group in groups:
            if not any(item.lower() in lowered for item in group):
                missing_groups.append(group)
        checks["contains_any"] = {"passed": not missing_groups, "missing_groups": missing_groups}

    if spec.get("contains_none"):
        found = [item for item in spec["contains_none"] if item.lower() in lowered]
        checks["contains_none"] = {"passed": not found, "found": found}

    if spec.get("regex"):
        missing_patterns = [pattern for pattern in spec["regex"] if not re.search(pattern, text, re.IGNORECASE)]
        checks["regex"] = {"passed": not missing_patterns, "missing": missing_patterns}

    if spec.get("max_words"):
        count = _word_count(text)
        checks["max_words"] = {
            "passed": 0 < count <= int(spec["max_words"]),
            "words": count,
            "limit": int(spec["max_words"]),
        }

    if spec.get("min_bullets"):
        count = len(re.findall(r"(?m)^\s*(?:[-*]|\d+[.)])\s+\S", text))
        checks["min_bullets"] = {"passed": count >= int(spec["min_bullets"]), "bullets": count}

    if spec.get("min_citations"):
        citations = len(re.findall(r"\[\d+\]|\(\w[^)]*\d{4}[^)]*\)|https?://", text))
        checks["min_citations"] = {
            "passed": citations >= int(spec["min_citations"]),
            "citations": citations,
        }

    if spec.get("language"):
        detected = detect_language(text)
        checks["language"] = {
            "passed": detected == spec["language"] or detected == "unknown",
            "detected": detected,
            "expected": spec["language"],
        }

    if spec.get("max_duplicate_ratio"):
        original_words = _word_count(case["input"])
        ratio = _word_count(text) / max(1, original_words)
        checks["max_duplicate_ratio"] = {
            "passed": ratio <= float(spec["max_duplicate_ratio"]),
            "ratio": round(ratio, 3),
            "limit": float(spec["max_duplicate_ratio"]),
        }

    checks["_all_passed"] = all(
        value.get("passed", True) for key, value in checks.items() if not key.startswith("_")
    )
    return checks


# ─── aggregation ───────────────────────────────────────────────────────────

def _bootstrap_ci(values: list[float], seed: int = 20261107, iterations: int = 2000) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(iterations):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(mean(sample))
    means.sort()
    low = means[int(0.025 * (len(means) - 1))]
    high = means[int(0.975 * (len(means) - 1))]
    return (round(low, 3), round(high, 3))


def _sign_test_p_value(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return round(min(1.0, 2 * tail), 4)


def _score_means(rows: list[dict[str, Any]], arm: str) -> dict[str, float]:
    values = {dimension: [] for dimension in DIMENSIONS}
    for row in rows:
        for dimension in DIMENSIONS:
            value = row.get("scores", {}).get(arm, {}).get(dimension)
            if isinstance(value, (int, float)):
                values[dimension].append(float(value))
    return {dimension: round(mean(items), 3) if items else 0.0 for dimension, items in values.items()}


def build_report(
    cases: list[dict[str, Any]],
    run_dir: str | Path,
    run_config: dict[str, Any],
) -> dict[str, Any]:
    run_path = Path(run_dir)
    arms = read_json(run_path / "arms.json")
    mapping = read_json(run_path / "judge_map.json")
    outputs = _load_arm_outputs(run_path, arms)

    case_rows: list[dict[str, Any]] = []
    missing_judges: list[str] = []
    for case in cases:
        case_id = case["id"]
        order_rows: list[dict[str, Any]] = []
        for order in (0, 1):
            request_id = f"{case_id}__order{order}"
            response_path = _judge_response_path(run_path, request_id)
            if not response_path.exists():
                missing_judges.append(request_id)
                continue
            content = _extract_content(read_json(response_path))
            parsed = parse_judge_payload(content)
            if parsed is None:
                missing_judges.append(request_id)
                continue
            info = mapping[request_id]
            baseline_side = "A" if info["a_arm"] == "baseline" else "B"
            treatment_side = "A" if info["a_arm"] == "treatment" else "B"
            order_rows.append({
                "request_id": request_id,
                "order": order,
                "baseline_scores": parsed["scores"][baseline_side],
                "treatment_scores": parsed["scores"][treatment_side],
                "winner": (
                    "baseline" if parsed["winner"] == baseline_side.lower()
                    else "treatment" if parsed["winner"] == treatment_side.lower()
                    else "tie"
                ),
                "rationale": parsed["rationale"],
            })

        if not order_rows:
            case_rows.append({
                "case_id": case_id,
                "language": case.get("language"),
                "task_type": case.get("task_type"),
                "missing": True,
                "scores": {},
                "deterministic": {},
            })
            continue

        baseline_scores = {
            dimension: round(mean([row["baseline_scores"][dimension] for row in order_rows]), 3)
            for dimension in DIMENSIONS
        }
        treatment_scores = {
            dimension: round(mean([row["treatment_scores"][dimension] for row in order_rows]), 3)
            for dimension in DIMENSIONS
        }
        diff = round(treatment_scores["overall"] - baseline_scores["overall"], 3)
        if diff > 0.25:
            winner = "treatment"
        elif diff < -0.25:
            winner = "baseline"
        else:
            winner = "tie"

        deterministic = {}
        for arm in ("baseline", "treatment"):
            deterministic[arm] = run_deterministic_checks(case, outputs[case_id][arm])

        case_rows.append({
            "case_id": case_id,
            "language": case.get("language"),
            "task_type": case.get("task_type"),
            "winner": winner,
            "overall_diff": diff,
            "scores": {"baseline": baseline_scores, "treatment": treatment_scores},
            "orders": order_rows,
            "deterministic": deterministic,
            "prompt_lengths": {
                "baseline_words": _word_count(arms[case_id]["baseline_prompt"]),
                "treatment_words": _word_count(arms[case_id]["treatment_prompt"]),
            },
        })

    completed = [row for row in case_rows if not row.get("missing")]
    wins = sum(1 for row in completed if row["winner"] == "treatment")
    losses = sum(1 for row in completed if row["winner"] == "baseline")
    ties = sum(1 for row in completed if row["winner"] == "tie")
    diffs = [row["overall_diff"] for row in completed]
    baseline_means = _score_means(completed, "baseline")
    treatment_means = _score_means(completed, "treatment")
    baseline_overall = baseline_means["overall"]
    treatment_overall = treatment_means["overall"]
    mean_diff = round(treatment_overall - baseline_overall, 3)
    relative_gain = round((mean_diff / baseline_overall) * 100, 2) if baseline_overall else 0.0
    ci_low, ci_high = _bootstrap_ci(diffs)
    p_value = _sign_test_p_value(wins, losses)

    deterministic_summary = {}
    for arm in ("baseline", "treatment"):
        arm_rows = [row["deterministic"][arm] for row in completed]
        total = sum(1 for row in arm_rows for key, value in row.items() if not key.startswith("_"))
        passed = sum(
            1 for row in arm_rows for key, value in row.items()
            if not key.startswith("_") and value.get("passed")
        )
        deterministic_summary[arm] = {
            "passed": passed,
            "total": total,
            "rate": round(passed / total, 3) if total else 0.0,
        }

    report = {
        "schema": "npsc.ab_eval.report.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_path),
        "run_config": run_config,
        "cases_total": len(cases),
        "cases_completed": len(completed),
        "missing_judges": missing_judges,
        "pairwise": {
            "treatment_wins": wins,
            "baseline_wins": losses,
            "ties": ties,
            "sign_test_p_value": p_value,
        },
        "overall": {
            "baseline_mean": baseline_overall,
            "treatment_mean": treatment_overall,
            "mean_diff": mean_diff,
            "relative_gain_percent": relative_gain,
            "median_case_diff": round(median(diffs), 3) if diffs else 0.0,
            "bootstrap_ci_95": [ci_low, ci_high],
        },
        "dimensions": {
            dimension: {
                "baseline": baseline_means[dimension],
                "treatment": treatment_means[dimension],
                "diff": round(treatment_means[dimension] - baseline_means[dimension], 3),
            }
            for dimension in DIMENSIONS
        },
        "deterministic": deterministic_summary,
        "cases": case_rows,
    }
    write_json(run_path / "report.json", report)
    (run_path / "report.md").write_text(render_report_markdown(report), encoding="utf-8")
    return report


def render_report_markdown(report: dict[str, Any]) -> str:
    config = report["run_config"]
    lines = [
        "# NSCP A/B Prompt-Quality Benchmark",
        "",
        f"- Generated: {report['created_at']}",
        f"- Generator model: `{config['generator_model']}`",
        f"- Judge model: `{config['judge_model']}`",
        f"- Cases: {report['cases_completed']}/{report['cases_total']}",
        "- Judge policy: blind pairwise, both A/B orders averaged",
        "",
        "## Headline",
        "",
        "| Metric | Baseline (raw request) | NSCP compiled prompt | Delta |",
        "|---|---:|---:|---:|",
        (f"| Mean overall score (0-10) | {report['overall']['baseline_mean']} | {report['overall']['treatment_mean']} | "
        f"{report['overall']['mean_diff']:+} ({report['overall']['relative_gain_percent']:+}%) |"),
        (f"| Pairwise wins | {report['pairwise']['baseline_wins']} | {report['pairwise']['treatment_wins']} | "
        f"{report['pairwise']['ties']} ties |"),
        "",
        f"Sign test p-value (two-sided): **{report['pairwise']['sign_test_p_value']}**  ",
        f"Bootstrap 95% CI of mean per-case difference: **{report['overall']['bootstrap_ci_95']}**",
        "",
        "## Dimensions",
        "",
        "| Dimension | Baseline | NSCP | Delta |",
        "|---|---:|---:|---:|",
    ]
    for dimension in DIMENSIONS:
        data = report["dimensions"][dimension]
        lines.append(f"| {dimension} | {data['baseline']} | {data['treatment']} | {data['diff']:+} |")
    lines.extend([
        "",
        "## Per-case results",
        "",
        "| Case | Task | Winner | Overall delta | Baseline | NSCP |",
        "|---|---|---|---:|---:|---:|",
    ])
    for row in report["cases"]:
        if row.get("missing"):
            lines.append(f"| {row['case_id']} | {row.get('task_type','')} | missing | - | - | - |")
            continue
        lines.append(
            f"| {row['case_id']} | {row.get('task_type','')} | {row['winner']} | "
            f"{row['overall_diff']:+} | {row['scores']['baseline']['overall']} | "
            f"{row['scores']['treatment']['overall']} |"
        )
    lines.extend([
        "",
        "## Deterministic checks",
        "",
        "| Arm | Passed | Total | Rate |",
        "|---|---:|---:|---:|",
        (f"| baseline | {report['deterministic']['baseline']['passed']} | "
        f"{report['deterministic']['baseline']['total']} | {report['deterministic']['baseline']['rate']:.1%} |"),
        (f"| treatment | {report['deterministic']['treatment']['passed']} | "
        f"{report['deterministic']['treatment']['total']} | {report['deterministic']['treatment']['rate']:.1%} |"),
        "",
        "## Per-case judge rationales",
        "",
    ])
    for row in report["cases"]:
        if row.get("missing"):
            continue
        lines.append(f"### {row['case_id']}")
        lines.append("")
        for order in row.get("orders", []):
            lines.append(f"- Order {order['order']} winner: **{order['winner']}** — {order['rationale']}")
        lines.append("")
    lines.extend([
        "## Methodology",
        "",
        "1. The baseline arm is the raw user request, unchanged.",
        "2. The treatment arm is exactly what `compile_prompt()` returns as `optimized_prompt`.",
        "3. Both arms use the same generator model, temperature, max tokens, and single user message.",
        "4. A blind judge model sees both responses in both orders (A/B then B/A) and scores them",
        "   against the same rubric and case-specific requirements. The two orders are averaged.",
        "5. Deterministic checks (format, JSON validity, forbidden content, length) complement the judge.",
        "",
        "## Files",
        "",
        f"- Raw arms, requests, responses, and transcripts: `{report['run_dir']}`",
        "- Structured results: `report.json`",
    ])
    return "\n".join(lines).strip() + "\n"


# ─── optional HTTP execution (normal environments) ─────────────────────────

def _post_json(url: str, body: dict[str, Any], api_key: str, timeout: int = 300) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (NSCP-ab-eval)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {"ok": True, "status": response.status, "response": payload}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        return {"ok": False, "status": exc.code, "error": detail}
    except Exception as exc:
        return {"ok": False, "status": None, "error": f"{type(exc).__name__}: {exc}"}


def execute_requests(
    run_dir: str | Path,
    stage: str,
    base_url: str,
    api_key: str,
    timeout: int = 300,
) -> dict[str, Any]:
    run_path = Path(run_dir)
    request_dir = run_path / "requests" / stage
    response_dir = run_path / "responses" / stage
    response_dir.mkdir(parents=True, exist_ok=True)
    executed = 0
    failed = 0
    for request_path in sorted(request_dir.glob("*.json")):
        request_id = request_path.stem
        response_path = response_dir / f"{request_id}.response.json"
        if response_path.exists():
            continue
        request = read_json(request_path)
        endpoint = request.get("endpoint", "/chat/completions")
        url = base_url.rstrip("/") + endpoint
        payload = _post_json(url, request["body"], api_key, timeout=timeout)
        payload["elapsed_at"] = datetime.now(timezone.utc).isoformat()
        write_json(response_path, payload)
        executed += 1
        if not payload.get("ok"):
            failed += 1
    return {"executed": executed, "failed": failed}


# ─── CLI ───────────────────────────────────────────────────────────────────

def _run_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "generator_model": args.generator_model,
        "judge_model": args.judge_model,
        "generator_max_tokens": args.generator_max_tokens,
        "judge_max_tokens": args.judge_max_tokens,
        "generator_temperature": args.generator_temperature,
        "harness_version": "1.0",
    }


def _selected_cases(args: argparse.Namespace) -> list[dict[str, Any]]:
    cases = load_cases(args.cases)
    if args.case_ids:
        wanted = set(args.case_ids)
        cases = [case for case in cases if case["id"] in wanted]
    return cases


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NSCP A/B prompt-quality benchmark")
    parser.add_argument("stage", choices=["prepare", "judge", "report", "run", "execute"])
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--case-ids", nargs="*", default=None)
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--generator-model", default="stealth/glyph-cluster:free")
    parser.add_argument("--judge-model", default="reflection/beam:free")
    parser.add_argument("--generator-max-tokens", type=int, default=4000)
    parser.add_argument("--judge-max-tokens", type=int, default=3000)
    parser.add_argument("--generator-temperature", type=float, default=0.2)
    parser.add_argument("--base-url", default=os.environ.get("NPSC_API_BASE_URL", "https://api.commandcode.ai/provider/v1"))
    parser.add_argument("--timeout", type=int, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases = _selected_cases(args)
    run_config = _run_config(args)
    run_dir = Path(args.run_dir) if args.run_dir else DEFAULT_RUN_ROOT / now_stamp()

    if args.stage == "prepare":
        result = prepare_run(cases, run_dir, run_config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.stage == "judge":
        result = build_judge_requests(cases, run_dir, run_config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.stage == "report":
        report = build_report(cases, run_dir, run_config)
        print(render_report_markdown(report))
        return 0
    if args.stage == "execute":
        api_key = os.environ.get("NPSC_API_KEY") or os.environ.get("COMMANDCODE_API_KEY", "")
        if not api_key:
            raise SystemExit("NPSC_API_KEY or COMMANDCODE_API_KEY must be set")
        result = {}
        for stage in ("generation", "judge"):
            if (run_dir / "requests" / stage).is_dir():
                result[stage] = execute_requests(run_dir, stage, args.base_url, api_key, timeout=args.timeout)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.stage == "run":
        prepare_run(cases, run_dir, run_config)
        api_key = os.environ.get("NPSC_API_KEY") or os.environ.get("COMMANDCODE_API_KEY", "")
        if not api_key:
            raise SystemExit("NPSC_API_KEY or COMMANDCODE_API_KEY must be set for 'run'")
        execute_requests(run_dir, "generation", args.base_url, api_key, timeout=args.timeout)
        build_judge_requests(cases, run_dir, run_config)
        execute_requests(run_dir, "judge", args.base_url, api_key, timeout=args.timeout)
        report = build_report(cases, run_dir, run_config)
        print(render_report_markdown(report))
        return 0
    raise SystemExit(f"unknown stage: {args.stage}")


if __name__ == "__main__":
    raise SystemExit(main())
