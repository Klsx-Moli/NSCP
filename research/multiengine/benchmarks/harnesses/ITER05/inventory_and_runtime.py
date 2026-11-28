"""ITER05 phase 0/1: real model inventory + runtime facts. No inference, no global changes."""
import hashlib
import json
import os
import pathlib
import struct
import subprocess
import sys
from datetime import datetime, timezone

E = pathlib.Path(r"<EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines")
(E / "logs").mkdir(parents=True, exist_ok=True)
SERVER = r"<USERPROFILE>\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe"
MODELS = {
    "embedding": r"<MODELS_DIR>\Qwen3-Embedding-0.6B-Q8_0.gguf",
    "reranker": r"<MODELS_DIR>\qwen3-reranker-0.6b-q8_0.gguf",
    "compactor": r"<MODELS_DIR>\Compactor-Qwen3.5-4B.Q4_K_M.gguf",
}
NAMES = {0: "BOOL8", 1: "UINT8", 2: "INT8", 3: "UINT16", 4: "INT16", 5: "UINT32",
         6: "INT32", 7: "FLOAT32", 8: "BOOL", 9: "STRING", 10: "ARRAY",
         11: "UINT64", 12: "INT64", 13: "FLOAT64"}


class Reader:
    def __init__(self, fh):
        self.f = fh

    def raw(self, n):
        b = self.f.read(n)
        if len(b) != n:
            raise ValueError("unexpected EOF")
        return b

    def u32(self):
        return struct.unpack("<I", self.raw(4))[0]

    def u64(self):
        return struct.unpack("<Q", self.raw(8))[0]

    def string(self):
        return self.raw(self.u64()).decode("utf-8", "replace")

    def value(self, t):
        if t == 9:
            return self.string()
        if t == 10:
            et = self.u32()
            n = self.u64()
            if n > 1_000_000:
                raise ValueError("implausible array")
            if et == 9:
                return [self.string() for _ in range(n)]
            return [self.value(et) for _ in range(n)]
        fmt = {0: "<?", 1: "<B", 2: "<b", 3: "<H", 4: "<h", 5: "<I", 6: "<i",
               7: "<f", 8: "<?", 11: "<Q", 12: "<q", 13: "<d"}.get(t)
        if not fmt:
            raise ValueError(f"unknown type {t}")
        return struct.unpack(fmt, self.raw(struct.calcsize(fmt)))[0]


def gguf_meta(path):
    out = {"parse_status": "UNKNOWN"}
    with open(path, "rb") as f:
        head = f.read(24)
        if len(head) < 24 or head[:4] != b"GGUF":
            out["parse_status"] = "NOT_GGUF"
            return out
        version, tensors, nkv = struct.unpack("<IQQ", head[4:24])
        out.update(gguf_version=version, tensor_count=tensors, kv_count=nkv)
        r = Reader(f)
        kv = {}
        try:
            for _ in range(nkv):
                key = r.string()
                if not key or len(key) > 200 or not key.isprintable():
                    raise ValueError(f"corrupt key at offset {f.tell()}: {key!r}")
                t = r.u32()
                kv[key] = r.value(t)
            out["parse_status"] = "PARSED" if len(kv) == nkv else "PARTIAL"
        except Exception as exc:
            out["parse_status"] = "PARSE_ERROR"
            out["parse_error"] = f"{type(exc).__name__}: {exc}"
        out["metadata"] = kv
        return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(4 * 1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def run(cmd, capture=True):
    try:
        p = subprocess.run(cmd, capture_output=capture, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        return {"returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    except Exception as exc:
        return {"returncode": None, "error": f"{type(exc).__name__}: {exc}"}


def main():
    inventory = {"generated_at": datetime.now(timezone.utc).isoformat(), "models": {}}
    for role, path in MODELS.items():
        p = pathlib.Path(path)
        rec = {"role": role, "path": str(p), "exists": p.is_file()}
        if rec["exists"]:
            rec["size_bytes"] = p.stat().st_size
            rec["sha256"] = sha256(p)
            rec["gguf"] = gguf_meta(p)
        inventory["models"][role] = rec
        print(f"{role}: {rec.get('size_bytes')} sha={rec.get('sha256','')[:16]} gguf={rec.get('gguf',{}).get('parse_status')}", flush=True)
    (E / "MODEL_INVENTORY.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")

    help_out = run([SERVER, "--help"])
    (E / "logs" / "llama-server-help.txt").write_text(
        f"cmd: {SERVER} --help\nrc: {help_out['returncode']}\n{help_out.get('stdout','')}\n{help_out.get('stderr','')}",
        encoding="utf-8")
    ver_out = run([SERVER, "--version"])
    (E / "logs" / "llama-server-version.txt").write_text(json.dumps(ver_out, indent=2), encoding="utf-8")

    tasklist = run(["tasklist"], capture=True)
    procs = [ln.strip() for ln in tasklist.get("stdout", "").splitlines()
             if any(k in ln.lower() for k in ("ollama", "llama-server"))]
    netstat = run(["netstat", "-ano"], capture=True)
    ports = [ln.strip() for ln in netstat.get("stdout", "").splitlines()
             if any(f":{p} " in ln for p in (11434, 8080, 8081, 8082, 18081, 18082, 18083))]
    env_keys = sorted(k for k in os.environ if k.startswith(("OLLAMA_", "GGML_", "HIP_", "HSA_", "CUDA_", "VK_", "GGUF_")))
    env_snapshot = {k: os.environ[k] for k in env_keys}
    runtime = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "llama_server": {"path": SERVER, "exists": pathlib.Path(SERVER).is_file(),
                         "version": ver_out, "help_chars": len(help_out.get("stdout", ""))},
        "ollama_processes": procs,
        "relevant_ports": ports,
        "isolated_env_vars": env_snapshot,
        "global_changes_made": False,
        "notes": [
            "No Ollama configuration, PATH, models store or Hermes config modified.",
            "Inference processes must be started per-process with explicit isolated env and sequential execution.",
            "help_chars>0 means --help was actually captured in this session.",
        ],
    }
    (E / "RUNTIME_COMPATIBILITY.json").write_text(json.dumps(runtime, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"help_chars={runtime['llama_server']['help_chars']} procs={len(procs)} ports={len(ports)}", flush=True)

    checkpoint = {
        "campaign": "NSCP_ITER05_SPECIALIZED_ENGINES",
        "phase": "01_MODEL_IDENTITY_AND_RUNTIME_BASELINE",
        "status": "EXECUTED",
        "evidence_dir": str(E),
        "baseline_sha": "97ea9e987656bf64234cfc56ee3a89196a3b579d",
        "remote_sha_verified": "97ea9e987656bf64234cfc56ee3a89196a3b579d",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": ["MODEL_INVENTORY.json", "RUNTIME_COMPATIBILITY.json", "logs/llama-server-help.txt"],
        "next": [
            "Read llama-server --help for embedding/pooling/rerank flags from the ACTUAL installed version",
            "Start embedding model in isolated sequential process; POST /v1/embeddings with one short phrase",
            "Validate vector: non-empty, constant dim, finite, norm, repeatability, semantic contrast, Unicode, ES/EN",
            "Then reranker, then compactor; never three models simultaneously",
        ],
        "constraints": ["no downloads", "no global PATH/Ollama/Hermes changes", "no push", "no main edits",
                        "no three models at once", "preserve checkpoints", "no paid providers"],
        "classification": "VERIFIED_BY_ME for hashes/help/process snapshot; STATICALLY_INSPECTED for GGUF metadata until runtime confirms",
    }
    (E / "CHECKPOINT.json").write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False), encoding="utf-8")
    print("CHECKPOINT written", flush=True)


if __name__ == "__main__":
    main()
