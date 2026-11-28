"""Bounded bilingual NLI diagnostic, not a safety gate or holdout benchmark."""
import argparse
import json
from pathlib import Path

from local_nli import LocalNLI

# Exact scopes in pairs; no generalizing from permission to unrelated access.
CASES = (
    ("es1", "El servidor A está apagado.", "El servidor A está encendido.", "contradiction"),
    ("es2", "El servidor A está apagado.", "El servidor A no está encendido.", "entailment"),
    ("es3", "El servidor A está apagado.", "El servidor B está apagado.", "neutral"),
    ("es4", "Se revocó el permiso de escritura en el archivo A.", "El permiso de escritura en el archivo A sigue vigente.", "contradiction"),
    ("es5", "Solo se permite leer el archivo A.", "Se permite leer el archivo A.", "entailment"),
    ("es6", "El archivo A existe.", "El archivo A está cifrado.", "neutral"),
    ("es7", "Las tres pruebas fallaron.", "Al menos una prueba falló.", "entailment"),
    ("es8", "Todas las pruebas fallaron.", "Todas las pruebas pasaron.", "contradiction"),
    ("es9", "Se propuso ejecutar la prueba.", "La prueba fue ejecutada.", "neutral"),
    ("en1", "Server A is off.", "Server A is on.", "contradiction"),
    ("en2", "Server A is off.", "Server A is not on.", "entailment"),
    ("en3", "Server A is off.", "Server B is off.", "neutral"),
    ("en4", "Write permission for file A was revoked.", "Write permission for file A is still valid.", "contradiction"),
    ("en5", "Only reading file A is permitted.", "Reading file A is permitted.", "entailment"),
    ("en6", "File A exists.", "File A is encrypted.", "neutral"),
    ("en7", "All three tests failed.", "At least one test failed.", "entailment"),
    ("en8", "All tests failed.", "All tests passed.", "contradiction"),
    ("en9", "A test run was proposed.", "The test was executed.", "neutral"),
    ("cross1", "El servidor A está apagado.", "Server A is on.", "contradiction"),
    ("cross2", "File A exists.", "El archivo A existe.", "entailment"),
    ("cross3", "El archivo A existe.", "File B is encrypted.", "neutral"),
)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("model", "tokenizer", "config", "out"):
        p.add_argument("--" + arg, required=True, type=Path)
    args = p.parse_args(argv)
    if args.out.exists():
        p.error("Output already exists")
    model = LocalNLI(args.model, args.tokenizer, args.config)
    rows = []
    for cid, premise, hypothesis, expected in CASES:
        row = {"case": cid, "premise": premise, "hypothesis": hypothesis, "expected": expected}
        try:
            row.update(model.classify(premise, hypothesis))
        except Exception as exc:
            row["error_type"] = type(exc).__name__
        rows.append(row)
    report = {"schema": "nscp/nli-diagnostic/v1", "identity": model.identity,
              "cases": rows, "expected_cases": len(CASES),
              "measured_cases": sum("label" in r for r in rows),
              "hits": sum(r.get("label") == r["expected"] for r in rows),
              "authority": "none", "semantic_gate": "not_validated"}
    with args.out.open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
    return 2 if report["measured_cases"] != len(CASES) else 0


if __name__ == "__main__":
    raise SystemExit(main())
