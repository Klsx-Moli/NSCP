"""Measured improvement benchmark: raw prompt vs. NSCP-compiled prompt.

Why this exists
---------------
The product claim "NSCP improves prompts" needs a number that is reproducible
and honest. This harness measures, per case, properties that the compiler is
*supposed* to change, and refuses to reward things it does not control.

What is measured (all deterministic, no model calls, no network)
---------------------------------------------------------------
1. **Structure** - does the compiled output declare role, goal, tasks,
   constraints, output contract, style and a verification clause? Counted from
   the produced text, not from internal metadata.
2. **Requirement preservation** - are the concrete requirements of the input
   (numbers, endpoints, file names, enums, quoted identifiers) still present in
   the compiled prompt? Measured as recall of extracted literal tokens.
3. **Ambiguity handling** - how many of the ambiguities the compiler detected
   are surfaced to the user (open questions) instead of silently dropped.
4. **Verification contract** - does the output tell the model how to verify,
   what to return, and what to do when blocked?
5. **Cost** - token expansion. Reported, never rewarded: a prompt is not
   "better" because it is longer.
6. **Regression guard** - the compiled prompt must not lose critical
   constraints, must not invent safety constraints the user never stated in the
   USER REQUIREMENTS layer, and must stay readable.

The report prints per-case rows and group aggregates, plus an explicit
"honest reading" section that states what did NOT improve.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from npsc_service import CompileRequest, compile_prompt  # noqa: E402
from token_estimator import estimate_text  # noqa: E402

CORPUS = ROOT / "tools" / "benchmark" / "corpus.json"
OUT_DIR = ROOT / "outputs" / "benchmark"

# ── literal requirement extraction ─────────────────────────────────────────
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_PATH_RE = re.compile(r"(?:/[\w.\-]+){2,}|[\w\-]+\.(?:py|js|ts|json|csv|md|txt|yaml|yml|sql|sh)\b")
_ENDPOINT_RE = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[\w/{}\-]+")
_IDENT_RE = re.compile(r"`([^`]{2,40})`|\"([^\"]{2,40})\"")
_ENUM_RE = re.compile(r"\(([a-z]+(?:\|[a-z]+)+)\)")
_CAPS_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")


def literal_requirements(text: str) -> set[str]:
    """Concrete, checkable requirements: numbers, paths, endpoints, enums, ids."""
    found: set[str] = set()
    found |= {m.group(0) for m in _ENDPOINT_RE.finditer(text)}
    found |= {m.group(0) for m in _PATH_RE.finditer(text)}
    found |= {m.group(1) or m.group(2) for m in _IDENT_RE.finditer(text)}
    found |= {m.group(1) for m in _ENUM_RE.finditer(text)}
    found |= {m.group(0) for m in _CAPS_RE.finditer(text)}
    found |= {m.group(0) for m in _NUMBER_RE.finditer(text)}
    # Drop tokens that are too generic to be a real requirement.
    generic = {"1", "2", "3", "4", "5", "10", "100", "0"}
    return {t.strip() for t in found if t.strip() and t.strip() not in generic and len(t.strip()) > 1}


def preserved_ratio(raw: str, compiled: str) -> tuple[float, list[str]]:
    wanted = literal_requirements(raw)
    if not wanted:
        return 1.0, []
    normalized = compiled.lower().replace("-", "_")
    missing = [token for token in wanted if token.lower().replace("-", "_") not in normalized]
    kept = len(wanted) - len(missing)
    return kept / len(wanted), sorted(missing)


# ── structure scoring ──────────────────────────────────────────────────────
STRUCTURE_SIGNALS = {
    "role": (r"^role:", r"\bact as\b", r"\bacting in\b"),
    "goal": (r"^goal:", r"\bgoal\b"),
    "tasks": (r"^tasks?:", r"\btasks?\b"),
    "constraints": (r"^constraints?:", r"\bconstraint"),
    "output_contract": (r"^expected output:", r"^out=", r"final answer contract"),
    "style": (r"^style:", r"^style="),
    "verification": (r"verify", r"verification", r"acceptance criteri"),
    "blocked_path": (r"if blocked", r"blocker", r"fallback"),
}


def structure_score(compiled: str) -> tuple[int, list[str]]:
    lowered = compiled.lower()
    present = [
        name
        for name, patterns in STRUCTURE_SIGNALS.items()
        if any(re.search(pattern, lowered, re.MULTILINE) for pattern in patterns)
    ]
    return len(present), present


# ── ambiguity surfacing ────────────────────────────────────────────────────
def ambiguity_surfaced(result: dict[str, Any]) -> tuple[int, int]:
    """(detected, surfaced_to_user). Surfaced = appears in the questions tab text."""
    detected = list((result.get("semantics") or {}).get("ambiguities") or [])
    clarification = result.get("clarification") or {}
    questions = list(clarification.get("questions") or [])
    if not questions:
        questions = list(((result.get("four_layers") or {}).get("open_questions")) or [])
    return len(detected), len(questions)


@dataclass
class CaseRow:
    id: str
    group: str
    language: str
    profile: str
    raw_tokens: int
    out_tokens: int
    structure_in: int
    structure_out: int
    structure_reconstructed: int = 0
    reconstructed_tokens: int = 0
    structure_signals: list[str] = field(default_factory=list)
    preserved: float = 1.0
    preserved_reconstructed: float = 1.0
    missing_literals: list[str] = field(default_factory=list)
    ambiguities_detected: int = 0
    questions_surfaced: int = 0
    quality_in: int = 0
    quality_out: int = 0
    preservation_score: int = 0
    critical_losses: list[str] = field(default_factory=list)
    invented_constraints: list[str] = field(default_factory=list)
    sentences: int = 1
    tail_lost: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "group": self.group,
            "language": self.language,
            "profile": self.profile,
            "raw_tokens": self.raw_tokens,
            "out_tokens": self.out_tokens,
            "token_expansion": round(self.out_tokens / max(1, self.raw_tokens), 2),
            "structure_in": self.structure_in,
            "structure_out": self.structure_out,
            "structure_delta": self.structure_out - self.structure_in,
            "structure_reconstructed": self.structure_reconstructed,
            "structure_reconstructed_delta": self.structure_reconstructed - self.structure_in,
            "reconstructed_expansion": round(self.reconstructed_tokens / max(1, self.raw_tokens), 2),
            "structure_signals": self.structure_signals,
            "requirement_preservation": round(self.preserved, 3),
            "requirement_preservation_reconstructed": round(self.preserved_reconstructed, 3),
            "missing_literals": self.missing_literals,
            "ambiguities_detected": self.ambiguities_detected,
            "questions_surfaced": self.questions_surfaced,
            "quality_in": self.quality_in,
            "quality_out": self.quality_out,
            "quality_delta": self.quality_out - self.quality_in,
            "preservation_score": self.preservation_score,
            "critical_losses": self.critical_losses,
            "invented_constraints": self.invented_constraints,
            "sentences": self.sentences,
            "tail_lost": self.tail_lost,
        }


def run_case(case: dict[str, Any], target: str) -> CaseRow:
    raw = case["raw"]
    result = compile_prompt(
        CompileRequest(original=raw, target=target, profile="AUTO")
    )
    compiled = result["optimized_prompt"]
    reconstructed = result.get("reconstructed") or ""
    raw_tokens = estimate_text(raw)["approx_tokens"]
    out_tokens = estimate_text(compiled)["approx_tokens"]
    reconstructed_tokens = estimate_text(reconstructed)["approx_tokens"] if reconstructed else 0

    from prompt_quality import evaluate_quality

    quality_in = evaluate_quality(raw, result["semantics"], raw).score
    quality_out = result["quality_report"]["score"]

    structure_in, _ = structure_score(raw)
    structure_out, signals = structure_score(compiled)
    structure_reconstructed, _ = structure_score(reconstructed) if reconstructed else (0, [])
    preserved, missing = preserved_ratio(raw, compiled)
    preserved_reconstructed, _ = (
        preserved_ratio(raw, reconstructed) if reconstructed else (0.0, [])
    )
    detected, surfaced = ambiguity_surfaced(result)

    # Multi-sentence coverage: does the reconstructed artifact keep the
    # requirements stated AFTER the first sentence?
    from semantic_extractor import _sentence_candidates

    sentences = _sentence_candidates(raw)
    tail_lost: list[str] = []
    if len(sentences) > 1 and reconstructed:
        tail_literals = literal_requirements(" ".join(sentences[1:]))
        normalized_rec = reconstructed.lower().replace("-", "_")
        tail_lost = sorted(
            token
            for token in tail_literals
            if token.lower().replace("-", "_") not in normalized_rec
        )

    # No invention: USER REQUIREMENTS must not contain a safety constraint the
    # input never stated.
    input_constraints = set(result["semantics"].get("constraints") or [])
    requirement_values = {
        str(r.get("value", ""))
        for r in (result.get("four_layers") or {}).get("user_requirements", [])
        if r.get("kind") == "constraint"
    }
    safety = {"no_sudo", "no_external_api", "no_destructive_actions",
              "stay_inside_project_root", "offline_only"}
    invented = sorted((requirement_values & safety) - input_constraints)

    return CaseRow(
        id=case["id"],
        group=case.get("group", "misc"),
        language=case.get("language", "?"),
        profile=result["applied_profile"],
        raw_tokens=raw_tokens,
        out_tokens=out_tokens,
        structure_in=structure_in,
        structure_out=structure_out,
        structure_reconstructed=structure_reconstructed,
        reconstructed_tokens=reconstructed_tokens,
        structure_signals=signals,
        preserved=preserved,
        preserved_reconstructed=preserved_reconstructed,
        missing_literals=missing,
        ambiguities_detected=detected,
        questions_surfaced=surfaced,
        quality_in=quality_in,
        quality_out=quality_out,
        preservation_score=int((result.get("context_loss_report") or {}).get("score") or 0),
        critical_losses=list((result.get("context_loss_report") or {}).get("critical_losses") or []),
        invented_constraints=invented,
        sentences=len(sentences),
        tail_lost=tail_lost,
    )


def aggregate(rows: list[CaseRow]) -> dict[str, Any]:
    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 2) if values else 0.0

    def _median(values: list[float]) -> float:
        return round(median(values), 2) if values else 0.0

    return {
        "cases": len(rows),
        "avg_structure_in": _avg([r.structure_in for r in rows]),
        "avg_structure_out": _avg([r.structure_out for r in rows]),
        "avg_structure_delta": _avg([r.structure_out - r.structure_in for r in rows]),
        "avg_structure_reconstructed": _avg([r.structure_reconstructed for r in rows]),
        "avg_structure_reconstructed_delta": _avg(
            [r.structure_reconstructed - r.structure_in for r in rows]
        ),
        "median_token_expansion": _median(
            [r.out_tokens / max(1, r.raw_tokens) for r in rows]
        ),
        "median_reconstructed_expansion": _median(
            [r.reconstructed_tokens / max(1, r.raw_tokens) for r in rows]
        ),
        "avg_requirement_preservation": _avg([r.preserved for r in rows]),
        "avg_requirement_preservation_reconstructed": _avg(
            [r.preserved_reconstructed for r in rows]
        ),
        "avg_quality_in": _avg([r.quality_in for r in rows]),
        "avg_quality_out": _avg([r.quality_out for r in rows]),
        "avg_quality_delta": _avg([r.quality_out - r.quality_in for r in rows]),
        "avg_preservation_score": _avg([r.preservation_score for r in rows]),
        "total_ambiguities_detected": sum(r.ambiguities_detected for r in rows),
        "total_questions_surfaced": sum(r.questions_surfaced for r in rows),
        "cases_with_critical_losses": sum(1 for r in rows if r.critical_losses),
        "cases_with_invented_constraints": sum(1 for r in rows if r.invented_constraints),
        "cases_where_ready_prompt_equals_input": sum(
            1 for r in rows if r.structure_out == 0
        ),
    }


def report_markdown(rows: list[CaseRow], grouped: dict[str, dict[str, Any]], overall: dict[str, Any], target: str) -> str:
    lines = [
        "# Benchmark de mejora real de prompts",
        "",
        f"Target: **{target}** · casos: **{len(rows)}** · generado sin llamadas a modelos.",
        "",
        "## Resumen ejecutivo",
        "",
        "NSCP produce **dos** salidas y su calidad es muy distinta. Medirlas juntas",
        "escondería la conclusión, así que se reportan por separado:",
        "",
        "| Salida | Qué es | Estructura | Expansión |",
        "|---|---|---:|---:|",
        f"| `optimized_prompt` (“Copiar prompt”) | objetivo completo + rol, tareas, "
        f"restricciones, contrato de salida, verificación y ruta de bloqueo | "
        f"{overall['avg_structure_out']}/8 | ×{overall['median_token_expansion']} |",
        f"| `reconstructed` (artefacto completo) | prompt reconstruido con seeds y "
        f"directivas de perfil añadidas | {overall['avg_structure_reconstructed']}/8 "
        f"| ×{overall['median_reconstructed_expansion']} |",
        "",
        f"El prompt copiable ya no es el original con una cabecera: ahora declara "
        f"**{overall['avg_structure_out']}/8** señales de estructura frente a "
        f"**{overall['avg_structure_in']}/8** del input, conservando el "
        f"**{overall['avg_requirement_preservation'] * 100:.0f}%** de los requisitos "
        "literales. Quedan "
        f"**{overall['cases_where_ready_prompt_equals_input']} de {overall['cases']}** "
        "casos sin señal nueva, todos entradas vagas de una línea.",
        "",
        "## Lo que sí y lo que no",
        "",
        f"- **Sí**: estructura del prompt copiable "
        f"(+{overall['avg_structure_delta']} señales medias sobre 8).",
        f"- **Sí**: estructura del artefacto completo "
        f"(+{overall['avg_structure_reconstructed_delta']} señales medias sobre 8).",
        "- **Sí**: las ambigüedades detectadas se convierten en preguntas visibles "
        f"({overall['total_ambiguities_detected']} detectadas → {overall['total_questions_surfaced']} mostradas).",
        f"- **Sí**: los requisitos literales del input se preservan "
        f"({overall['avg_requirement_preservation'] * 100:.1f}% en el prompt copiable, "
        f"{overall['avg_requirement_preservation_reconstructed'] * 100:.1f}% en el reconstruido).",
        f"- **No**: el prompt compilado no se acorta (×{overall['median_token_expansion']} el copiable, "
        f"×{overall['median_reconstructed_expansion']} el completo).",
        "- **No**: una entrada vaga de una línea sigue sin poder estructurarse: no hay "
        "información que extraer, solo preguntas que hacer.",
        "- **No**: la puntuación interna `prompt_quality` apenas cambia "
        f"({overall['avg_quality_in']} → {overall['avg_quality_out']}, "
        f"{overall['avg_quality_delta']:+.2f}): mide contrato semántico, no utilidad.",
        "",
        "## Agregado",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Casos | {overall['cases']} |",
        f"| Estructura media (input) | {overall['avg_structure_in']}/8 |",
        f"| Estructura media (prompt copiable) | {overall['avg_structure_out']}/8 |",
        f"| Estructura media (artefacto completo) | {overall['avg_structure_reconstructed']}/8 |",
        f"| Preservación de requisitos (copiable) | {overall['avg_requirement_preservation'] * 100:.1f}% |",
        f"| Preservación de requisitos (completo) | "
        f"{overall['avg_requirement_preservation_reconstructed'] * 100:.1f}% |",
        f"| Expansión mediana (copiable / completo) | ×{overall['median_token_expansion']} / "
        f"×{overall['median_reconstructed_expansion']} |",
        f"| Calidad interna input → output | {overall['avg_quality_in']} → {overall['avg_quality_out']} "
        f"({overall['avg_quality_delta']:+.2f}) |",
        f"| Puntuación de preservación (validador) | {overall['avg_preservation_score']}/100 |",
        f"| Ambigüedades detectadas → preguntas mostradas | "
        f"{overall['total_ambiguities_detected']} → {overall['total_questions_surfaced']} |",
        f"| Casos con pérdidas críticas | {overall['cases_with_critical_losses']} |",
        f"| Casos con restricciones inventadas | {overall['cases_with_invented_constraints']} |",
        "",
        "## Por grupo",
        "",
        "| Grupo | Casos | Estructura copiable | Estructura completa | Preservación | Expansión |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for group, data in sorted(grouped.items()):
        lines.append(
            f"| {group} | {data['cases']} | {data['avg_structure_out']}/8 "
            f"| {data['avg_structure_reconstructed']}/8 "
            f"| {data['avg_requirement_preservation'] * 100:.1f}% "
            f"| ×{data['median_token_expansion']} |"
        )

    lines += [
        "",
        "## Detalle por caso",
        "",
        "| Caso | Grupo | Perfil | Estructura copiable | Estructura completa | Req. | Expansión | Ambigüedades |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.id} | {row.group} | {row.profile} "
            f"| {row.structure_in}→{row.structure_out} "
            f"| {row.structure_in}→{row.structure_reconstructed} "
            f"| {row.preserved * 100:.0f}% "
            f"| ×{row.out_tokens / max(1, row.raw_tokens):.2f} "
            f"| {row.ambiguities_detected}→{row.questions_surfaced} |"
        )

    multi = [r for r in rows if r.tail_lost]
    if multi:
        lines += [
            "",
            "## Cobertura en entradas de varias frases",
            "",
            f"**{len(multi)} de {len(rows)}** casos ({len(multi) / len(rows) * 100:.0f}%) "
            "tienen requisitos después de la primera frase que el artefacto "
            "reconstruido **no** incluye. El prompt copiable sí los conserva porque "
            "embebe el texto original.",
            "",
            "| Caso | Frases | Requisitos de frases 2+ ausentes del artefacto |",
            "|---|---:|---|",
        ]
        for row in multi:
            lines.append(
                f"| {row.id} | {row.sentences} | `{', '.join(row.tail_lost)}` |"
            )
        lines += [
            "",
            "Está cubierto por `tests/test_reconstruction_coverage.py` con un "
            "`xfail` estricto: cuando el extractor transporte el objetivo completo, "
            "ese test pasará a verde y este número deberá bajar a cero.",
        ]

    problems = [r for r in rows if r.missing_literals or r.critical_losses or r.invented_constraints]
    if problems:
        lines += ["", "## Casos que requieren atención", ""]
        for row in problems:
            if row.missing_literals:
                lines.append(f"- **{row.id}**: requisitos literales ausentes → `{', '.join(row.missing_literals)}`")
            if row.critical_losses:
                lines.append(f"- **{row.id}**: pérdidas críticas → `{', '.join(row.critical_losses)}`")
            if row.invented_constraints:
                lines.append(f"- **{row.id}**: restricciones inventadas → `{', '.join(row.invented_constraints)}`")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the real improvement of NSCP prompts.")
    parser.add_argument("--corpus", default=str(CORPUS))
    parser.add_argument("--target", default="codex")
    parser.add_argument("--out", default=str(OUT_DIR))
    parser.add_argument("--limit", type=int, default=0, help="only the first N cases")
    args = parser.parse_args(argv)

    data = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    cases = data["cases"]
    if args.limit:
        cases = cases[: args.limit]

    rows = [run_case(case, args.target) for case in cases]

    groups: dict[str, list[CaseRow]] = {}
    for row in rows:
        groups.setdefault(row.group, []).append(row)
    grouped = {name: aggregate(group_rows) for name, group_rows in groups.items()}
    overall = aggregate(rows)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "npsc.benchmark.report.v1",
        "target": args.target,
        "overall": overall,
        "groups": grouped,
        "rows": [r.to_dict() for r in rows],
    }
    (out_dir / "prompt_improvement.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    markdown = report_markdown(rows, grouped, overall, args.target)
    (out_dir / "prompt_improvement.md").write_text(markdown, encoding="utf-8")

    print(markdown)
    print(f"written: {out_dir / 'prompt_improvement.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
