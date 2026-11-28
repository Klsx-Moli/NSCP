# Experimental ONNX log scoring

ITER07 proves inference, not compression quality. The original CTXPrune smoke
used a sigmoid of one logit for a two-class head and kept no decoded text.
The upstream compress.py at e49a1de270e0dc74090f5dfa0b4e79100c5421e7
uses class-1 softmax; Kompress's model card specifies final_scores in [0,1].
This adapter uses those output contracts, strict shape/finite checks and
untruncated tokenizer offsets. It scores complete original lines and renders
explicit incomplete previews within a serialized UTF-8 byte budget. It is
not the upstream CTXPrune atom/window pipeline or a provider token meter.
The protection rules are heuristic; a protected budget failure emits no
preview. The caller must retain canonical original data and tool roles.

Optional runtime: the isolated ITER07 ONNX environment. No extra downloads
or dependencies in the core package. Run from feature checkout:

    python tools/benchmark_onnx_context.py --kind kompress --model PATH --tokenizer PATH --out NEW_REPORT.json
    python tools/benchmark_onnx_context.py --kind ctxprune --model PATH --tokenizer PATH --out NEW_REPORT.json

Set PYTHONPATH=src. Use actual installed model/tokenizer paths and trusted
local files. The benchmark compares six synthetic evidence cases against
equal-score deterministic selection; it does not establish task success.
No automatic integration with Hermes.
