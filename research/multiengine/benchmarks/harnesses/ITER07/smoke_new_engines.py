"""ITER07 smoke tests: one real inference per newly available local engine."""
import json
import math
import pathlib
import sqlite3
from datetime import datetime, timezone

import numpy as np
import onnxruntime as ort
import sqlite_vec
from tokenizers import Tokenizer

BASE = pathlib.Path(r"<EVIDENCE_DIR>\ITER07-resources")
OUT = pathlib.Path(r"<EVIDENCE_DIR>\ITER07-validation")
KOMP = pathlib.Path(r"<DOWNLOADS_DIR>\kompress-int8-wo.onnx")
CTX = BASE / "downloads" / "ctxprune"
NLI = BASE / "downloads" / "nli"
KTOK = BASE / "kompress-source"

result = {"generated_at": datetime.now(timezone.utc).isoformat(),
          "runtime": {"onnxruntime": ort.__version__, "numpy": np.__version__,
                      "sqlite_vec": getattr(sqlite_vec, "__version__", "0.1.9"),
                      "providers": ort.get_available_providers()},
          "classification": "EVIDENCE_PENDING", "engines": {}, "errors": []}


def encode(tok_path, texts, max_length=128):
    tok = Tokenizer.from_file(str(tok_path))
    tok.enable_truncation(max_length=max_length)
    encodings = [tok.encode(text) for text in texts]
    ids = np.array([e.ids for e in encodings], dtype=np.int64)
    mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
    return tok, ids, mask


def smoke_kompress():
    sess = ort.InferenceSession(str(KOMP), providers=["CPUExecutionProvider"])
    tok, ids, mask = encode(KTOK / "tokenizer.json", ["The permission was revoked after the review."])
    scores = sess.run(["final_scores"], {"input_ids": ids, "attention_mask": mask})[0]
    return {"status": "INFERENCE_OK", "inputs": [i.name for i in sess.get_inputs()],
            "output_shape": list(scores.shape), "score_min": float(scores.min()),
            "score_max": float(scores.max()), "score_sample": [round(float(x), 6) for x in scores[0][:8]],
            "token_count": int(ids.shape[1]),
            "note": "final_scores observed; no semantic compression claim"}


def smoke_ctxprune():
    sess = ort.InferenceSession(str(CTX / "model_quantized.onnx"), providers=["CPUExecutionProvider"])
    tool_result = "INFO build ok; WARN retry 2; ERROR tests/test_agent_context.py missing; INFO done"
    tok, ids, mask = encode(CTX / "tokenizer.json", [tool_result])
    logits = sess.run(["logits"], {"input_ids": ids, "attention_mask": mask})[0]
    probs = 1 / (1 + np.exp(-logits[0]))
    keep = probs[:, 1] > 0.5
    kept_tokens = tok.decode([int(i) for i, k in zip(ids[0], keep) if k], skip_special_tokens=True)
    return {"status": "INFERENCE_OK", "tool_result": tool_result,
            "input_shape": list(ids.shape), "output_shape": list(logits.shape),
            "keep_ratio": round(float(keep.mean()), 4),
            "kept_text": kept_tokens[:500],
            "note": "token classifier drop/keep; heuristic threshold 0.5, not validated quality"}


def smoke_nli():
    sess = ort.InferenceSession(str(NLI / "model.onnx"), providers=["CPUExecutionProvider"])
    cfg = json.loads((NLI / "config.json").read_text(encoding="utf-8"))
    labels = cfg["id2label"]
    tok = Tokenizer.from_file(str(NLI / "tokenizer.json"))
    tok.enable_truncation(max_length=128)
    pairs = [
        ("es-entailment", "El servidor está apagado.", "El servidor no está encendido."),
        ("es-contradiction", "El servidor está apagado.", "El servidor está encendido."),
        ("es-neutral", "El servidor está apagado.", "El servidor fue comprado ayer."),
        ("en-entailment", "The permission was revoked.", "Access is no longer authorized."),
        ("en-contradiction", "The permission was revoked.", "The permission is still valid."),
        ("en-neutral", "The permission was revoked.", "The file was created yesterday."),
    ]
    rows = []
    for name, premise, hypothesis in pairs:
        enc = tok.encode(premise, hypothesis)
        ids = np.array([enc.ids], dtype=np.int64)
        mask = np.array([enc.attention_mask], dtype=np.int64)
        logits = sess.run(["logits"], {"input_ids": ids, "attention_mask": mask})[0][0]
        ex = np.exp(logits - logits.max())
        probs = ex / ex.sum()
        idx = int(probs.argmax())
        rows.append({"case": name, "premise": premise, "hypothesis": hypothesis,
                     "predicted": labels[str(idx)], "expected": name.split("-")[1],
                     "scores": {labels[str(i)]: round(float(probs[i]), 6) for i in range(len(probs))}})
    hits = sum(r["predicted"] == r["expected"] for r in rows)
    return {"status": "INFERENCE_OK", "pairs": rows, "label_hits": hits, "total": len(rows)}


def smoke_sqlite_vec():
    conn = sqlite3.connect(":memory:")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("CREATE VIRTUAL TABLE items USING vec0(embedding float[4])")
    for i, v in enumerate(([1.0, 0.0, 0.0, 0.0], [0.9, 0.1, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0])):
        conn.execute("INSERT INTO items(rowid, embedding) VALUES (?, ?)", (i + 1, sqlite_vec.serialize_float32(v)))
    rows = conn.execute("SELECT rowid, distance FROM items WHERE embedding MATCH ? ORDER BY distance LIMIT 2",
                        (sqlite_vec.serialize_float32([1.0, 0.0, 0.0, 0.0]),)).fetchall()
    conn.close()
    return {"status": "QUERY_OK", "neighbors": [[int(r[0]), round(float(r[1]), 6)] for r in rows],
            "note": "in-memory index only; no persistent DB published"}


for name, fn in (("kompress", smoke_kompress), ("ctxprune", smoke_ctxprune),
                 ("nli", smoke_nli), ("sqlite_vec", smoke_sqlite_vec)):
    try:
        result["engines"][name] = fn()
    except Exception as exc:
        result["engines"][name] = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
        result["errors"].append(name)
result["classification"] = "VERIFIED_BY_EXECUTOR" if not result["errors"] else "EVIDENCE_PENDING"
(OUT / "smoke-new-engines.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: v.get("status") for k, v in result["engines"].items()}, ensure_ascii=False))
print("nli_hits", result["engines"].get("nli", {}).get("label_hits"), "errors", result["errors"])
