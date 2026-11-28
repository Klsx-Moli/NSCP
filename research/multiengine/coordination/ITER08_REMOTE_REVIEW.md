# ITER08 remote review

Research source b6f7da45587f3b6590218f691fb0bf98bf26b10a; code 5fbdd030ec5571039159534a413ff8b44fe3dc45.
CI run 46114412740 completed success: 703 full, 10 subtests, 231 targeted, Ruff pass.

VERIFIED_BY_ME: inspected saved checkpoint, ONNX case results, NLI raw scores, pytest log. Reconstructed fixture in independent Python with canonical JSON and UTF-8 estimator. Original 3808, marker-only 313, saved six excerpts 1242. All six source SHA256 values and reference b07703fd7f4365a539accb3b5a620a1a187bc6041fde32acad9064459ab8dd14 matched. Five excerpts had identical text. Removing four duplicate copies from the saved plan yields projected 643 estimated tokens, target literal still visible. This is arithmetic replay of saved selection, not the new selector's measured output. New code scores unique texts only, retains all occurrence IDs, rejects preview enlargement, and verifies original offsets.

REPORTED_BY_EXECUTOR: both Kompress and CTXPrune preserved 4/6 literals, exactly the same 4 as deterministic equal-score baseline; neither demonstrated incremental benefit. Unicode and semantic cases missed. NLI 15/21; incorrect high scores on unrelated scopes and proposed vs executed; no permission, semantic gate or calibrated confidence claim. Six-model inventory and 51 tests/1 skip reported; local binary rehash and new runtime replay NOT_EXECUTED by remote agent.

New development candidate 98f96fa9ec7a6dba7a46d26aeb8481597e9e0976. See feature docs/ITER09_LOCAL_EXECUTION.md. Main remains unchanged. Real host hook qualification, measured new dedup replay, GUI on Windows, candidate compactor and full task continuity still need local evidence. No production release or activation.
