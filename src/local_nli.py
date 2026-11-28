"""Optional local NLI diagnostics; never authorizes actions or certifies truth."""
from __future__ import annotations

import json
import math
from pathlib import Path

from nscp_resources import file_hash

LABELS = frozenset({"entailment", "neutral", "contradiction"})


def nli_scores(logits, labels):
    if (not isinstance(labels, dict) or set(labels) != {"0", "1", "2"}
            or any(not isinstance(v, str) for v in labels.values())
            or set(labels.values()) != LABELS):
        raise ValueError("Expected explicit three-class NLI label mapping")
    if (not isinstance(logits, list) or len(logits) != 1 or not isinstance(logits[0], list)
            or len(logits[0]) != 3 or any(type(x) not in (float, int) for x in logits[0])):
        raise ValueError("Unexpected NLI logits")
    try:
        vals = [float(x) for x in logits[0]]
    except OverflowError as exc:
        raise ValueError("Non-finite NLI logits") from exc
    if any(not math.isfinite(x) for x in vals):
        raise ValueError("Non-finite NLI logits")
    weights = [math.exp(x - max(vals)) for x in vals]
    scores = {labels[str(i)]: x / sum(weights) for i, x in enumerate(weights)}
    best = max(scores.values())
    tied = [label for label, score in scores.items() if score == best]
    return {"scores": scores, "label": tied[0] if len(tied) == 1 else None,
            "calibrated": False, "authority": "none"}


class LocalNLI:
    def __init__(self, model, tokenizer, config, *, max_tokens=256):
        if type(max_tokens) is not int or not 1 <= max_tokens <= 512:
            raise ValueError("Invalid diagnostic token limit")
        model, tokenizer, config = (Path(p).resolve(strict=True) for p in (model, tokenizer, config))
        labels = json.loads(config.read_text(encoding="utf-8"))["id2label"]
        nli_scores([[0, 0, 0]], labels)
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.np, self.labels, self.max_tokens = np, labels, max_tokens
        self.identity = {"model_sha256": file_hash(model), "tokenizer_sha256": file_hash(tokenizer),
                         "config_sha256": file_hash(config), "onnxruntime": ort.__version__}
        self.tokenizer = Tokenizer.from_file(str(tokenizer))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model), sess_options=opts, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.session.get_inputs()}
        if self.inputs not in ({"input_ids", "attention_mask"},
                               {"input_ids", "attention_mask", "token_type_ids"}):
            raise ValueError("Unexpected NLI input signature")
        if "logits" not in {o.name for o in self.session.get_outputs()}:
            raise ValueError("Unexpected NLI output signature")

    def classify(self, premise, hypothesis):
        if any(not isinstance(s, str) or not s.strip() or len(s) > 8192 for s in (premise, hypothesis)):
            raise ValueError("Invalid NLI text pair")
        enc = self.tokenizer.encode(premise, hypothesis)
        if not 0 < len(enc.ids) <= self.max_tokens:
            raise ValueError("NLI pair exceeds token budget; no truncation")
        # Verify both source segments survived pair encoding, without assuming
        # a BERT-specific token_type_ids pattern for XLM-R-style tokenizers.
        if not {0, 1}.issubset(set(enc.sequence_ids)):
            raise ValueError("Tokenizer omitted a source segment")
        data = {"input_ids": enc.ids, "attention_mask": enc.attention_mask,
                "token_type_ids": enc.type_ids}
        payload = {key: self.np.array([data[key]], dtype=self.np.int64) for key in self.inputs}
        output = self.session.run(["logits"], payload)[0].tolist()
        return {"token_count": len(enc.ids), **nli_scores(output, self.labels)}
