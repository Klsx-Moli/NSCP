# ITER08 local execution — no new downloads

Use the isolated ONNX environment from ITER07. Add CTXPrune and NLI to the
shared extras root with the targeted import commands in LOCAL_RESOURCES.md.
Then use one new output directory:

    $env:PYTHONPATH = "src"
    python tools/run_iter08_local.py --root ABSOLUTE_EXTRAS --out NEW_EVIDENCE_DIR --server ABSOLUTE_LLAMA_SERVER --ngl 99

The runner executes Kompress, CTXPrune raw scorer, NLI diagnostic, then
one optional semantic request preview using the embedding server. Models
are sequential. No current conversation data, no provider requests, no
global changes, no new downloads, no Git writes. It records failures and
does not treat execution as semantic success. The individual JSON files
contain results. Sanitize paths and logs before public research push.
If no server is supplied the embedding preview is explicitly not requested.
Only the local ONNX runtime environment needs the optional dependencies.
The NLI model is not an authorization gate.
