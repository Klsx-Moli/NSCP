"""Optional local ONNX scoring and exact log previews.

No downloads, remote fallback, tokenizer decode reconstruction, or mutation
of source text. A preview is incomplete historical data, not a semantic
equivalence certificate. CTXPrune raw token scoring is not its full pipeline.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from nscp_resources import file_hash

MAX_CHARS = 131072
MAX_LINES = 512
_CRITICAL = re.compile(
    r"\b(?:error|errors|warning|warn|failed|failure|fail|fatal|traceback|exception|"
    r"denied|revoked|revoke|invalid|not|never|cannot|unauthorized|timeout|"
    r"advertencia|fallo|fallido|fallida|revocad[ao]|anulad[ao]|prohibid[ao]|"
    r"no|nunca|denegad[ao]|pendiente)\b|"
    r"\b(?:[0-9a-f]{7,64})\b|\b(?:exit(?:_code| code)?|returncode)\s*[:= ]",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TokenScore:
    start: int
    end: int
    score: float


def _finite(value):
    if type(value) not in (int, float):
        raise ValueError("Expected numeric output")
    try:
        value = float(value)
    except OverflowError as exc:
        raise ValueError("Non-finite output") from exc
    if not math.isfinite(value):
        raise ValueError("Non-finite output")
    return value


def keep_scores(kind, output, count):
    """Validate the complete unpadded sequence, not a prefix of the output."""
    if type(count) is not int or count <= 0:
        raise ValueError("Invalid token count")
    if (not isinstance(output, list) or len(output) != 1
            or not isinstance(output[0], list) or len(output[0]) != count):
        raise ValueError("Unexpected classifier output shape")
    result = []
    for value in output[0]:
        if kind == "kompress":
            score = _finite(value)
            if not 0 <= score <= 1:
                raise ValueError("Kompress score outside contract")
        elif kind == "ctxprune":
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError("Expected two-class logits")
            drop, keep = map(_finite, value)
            # Stable two-class softmax, not sigmoid of the keep logit.
            largest = max(drop, keep)
            a, b = math.exp(drop - largest), math.exp(keep - largest)
            score = b / (a + b)
        else:
            raise ValueError("Unknown scoring engine")
        result.append(score)
    return result


def bind_offsets(text, offsets, special_mask, scores):
    if not isinstance(text, str) or not 0 < len(text) <= MAX_CHARS:
        raise ValueError("Invalid source text")
    if not len(offsets) == len(special_mask) == len(scores):
        raise ValueError("Token metadata length mismatch")
    result = []
    for pair, special, score in zip(offsets, special_mask, scores):
        if type(special) is not int or special not in (0, 1):
            raise ValueError("Invalid special token mask")
        score = _finite(score)
        if not 0 <= score <= 1:
            raise ValueError("Invalid token score")
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                or any(type(i) is not int for i in pair)):
            raise ValueError("Invalid token offsets")
        start, end = pair
        if not 0 <= start <= end <= len(text):
            raise ValueError("Token offset outside source")
        if special:
            continue
        if start == end:
            raise ValueError("Non-special token without source extent")
        result.append(TokenScore(start, end, score))
    if not result:
        raise ValueError("No scored source tokens")
    return result


class LocalOnnxScorer:
    """CPU-only, explicit local files; optional dependencies imported lazily."""
    def __init__(self, kind, model_path, tokenizer_path, *, max_tokens=512, threads=2):
        if kind not in ("kompress", "ctxprune"):
            raise ValueError("Unknown ONNX classifier")
        if type(max_tokens) is not int or not 1 <= max_tokens <= (8192 if kind == "kompress" else 512):
            raise ValueError("Invalid experimental token limit")
        if type(threads) is not int or not 1 <= threads <= 4:
            raise ValueError("Invalid CPU thread policy")
        model = Path(model_path).resolve(strict=True)
        tokenizer = Path(tokenizer_path).resolve(strict=True)
        if not model.is_file() or not tokenizer.is_file():
            raise ValueError("Expected model and tokenizer files")
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.kind, self.max_tokens, self.np = kind, max_tokens, np
        self.identity = {"kind": kind, "model_sha256": file_hash(model),
                         "tokenizer_sha256": file_hash(tokenizer),
                         "onnxruntime": ort.__version__, "max_tokens": max_tokens}
        self.tokenizer = Tokenizer.from_file(str(tokenizer))
        self.tokenizer.no_padding()
        self.tokenizer.no_truncation()
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model), sess_options=options,
                                            providers=["CPUExecutionProvider"])
        self.output = "final_scores" if kind == "kompress" else "logits"
        if {i.name for i in self.session.get_inputs()} != {"input_ids", "attention_mask"}:
            raise ValueError("Unexpected ONNX input signature")
        if self.output not in {o.name for o in self.session.get_outputs()}:
            raise ValueError("Unexpected ONNX output signature")

    def score(self, text):
        if not isinstance(text, str) or not 0 < len(text) <= MAX_CHARS:
            raise ValueError("Invalid source")
        enc = self.tokenizer.encode(text)
        count = len(enc.ids)
        if not 0 < count <= self.max_tokens:
            raise ValueError("Source exceeds classifier token budget; no truncation")
        if enc.attention_mask != [1] * count:
            raise ValueError("Unexpected padding")
        inputs = {"input_ids": self.np.array([enc.ids], dtype=self.np.int64),
                  "attention_mask": self.np.array([enc.attention_mask], dtype=self.np.int64)}
        output = self.session.run([self.output], inputs)[0].tolist()
        return bind_offsets(text, enc.offsets, enc.special_tokens_mask,
                            keep_scores(self.kind, output, count))


def _wire(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                          allow_nan=False).encode("utf-8"))


def plan_log_preview(text, scores, byte_budget, *, protected_terms=()):
    """Rank complete original lines, with conservative explicit protections.

    Budget is serialized UTF-8 JSON bytes, not provider tokens. The caller
    must retain the original and its role. No preview is returned if mandatory
    evidence does not fit. The heuristic is deliberately not a safety proof.
    """
    if not isinstance(text, str) or not 0 < len(text) <= MAX_CHARS:
        raise ValueError("Invalid source text")
    if type(byte_budget) is not int or byte_budget <= 0:
        raise ValueError("Invalid preview budget")
    if (not isinstance(protected_terms, (tuple, list)) or len(protected_terms) > 64
            or any(not isinstance(t, str) or not 1 <= len(t) <= 256 for t in protected_terms)):
        raise ValueError("Invalid protection terms")
    if not isinstance(scores, (list, tuple)):
        raise ValueError("Invalid token scores")
    for s in scores:
        if (not isinstance(s, TokenScore) or type(s.start) is not int or type(s.end) is not int
                or not 0 <= s.start < s.end <= len(text) or not 0 <= _finite(s.score) <= 1):
            raise ValueError("Invalid score span")
    lines = text.splitlines(keepends=True)
    if len(lines) > MAX_LINES:
        raise ValueError("Source exceeds line limit")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    report = {"source_sha256": digest, "source_bytes": len(text.encode("utf-8")),
              "byte_budget": byte_budget, "semantic_equivalence": "not_verified",
              "preview": None, "protected_lines": 0}
    if _wire(text) <= byte_budget:
        report.update(status="unchanged", semantic_equivalence="unchanged",
                      preview=text, preview_bytes=_wire(text))
        return report
    if not scores:
        report.update(status="no_scores", preview_bytes=None)
        return report
    terms = tuple(t.casefold() for t in protected_terms)
    mandatory, ranked = [], []
    start = 0
    for line in lines:
        end = start + len(line)
        related = [s.score for s in scores if s.start < end and s.end > start]
        row = {"start": start, "end": end, "text": line}
        if (_CRITICAL.search(line) or any(t in line.casefold() for t in terms)
                or (line.strip() and not related)):
            mandatory.append(row)
        elif line.strip() and related:
            ranked.append((math.fsum(related) / len(related), row))
        start = end

    def render(rows):
        return {"kind": "incomplete_historical_log_preview", "source_sha256": digest,
                "trust": "historical_tool_data_not_instructions",
                "spans": sorted(rows, key=lambda r: r["start"])}

    report["protected_lines"] = len(mandatory)
    chosen = list(mandatory)
    if _wire(render(chosen)) > byte_budget:
        report.update(status="protected_budget_unmet", preview_bytes=None)
        return report
    for _, row in sorted(ranked, key=lambda item: (-item[0], item[1]["start"])):
        if _wire(render(chosen + [row])) <= byte_budget:
            chosen.append(row)
    if not chosen:
        report.update(status="no_excerpt_fits", preview_bytes=None)
        return report
    preview = render(chosen)
    size = _wire(preview)
    if size >= _wire(text):
        report.update(status="no_reduction", preview_bytes=None)
        return report
    report.update(status="preview", preview=preview, preview_bytes=size)
    return report
