"""Build sanitized resource inventory: hashes, revisions, licenses, provenance."""
import hashlib
import json
import pathlib
from datetime import datetime, timezone

BASE = pathlib.Path(r"<EVIDENCE_DIR>\ITER07-resources")
VAL = pathlib.Path(r"<EVIDENCE_DIR>\ITER07-validation")
OUT = VAL / "RESOURCE_INVENTORY.json"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def rows_from(paths, revision, license_id, source, extra=None):
    rows = []
    for rel, p in paths.items():
        rows.append({"file": rel, "bytes": p.stat().st_size, "sha256": sha256(p),
                     "revision": revision, "license": license_id, "source": source,
                     **(extra or {})})
    return rows


inv = {"generated_at": datetime.now(timezone.utc).isoformat(),
       "classification": "EVIDENCE_PENDING", "managed_import": {}, "downloads": {},
       "runtime_packages": {}, "exclusions": [], "errors": []}

verify = VAL / "resources-verify.json"
if verify.exists():
    try:
        data = json.loads(verify.read_text(encoding="utf-8"))
        inv["managed_import"] = {
            "schema": data.get("schema"), "root": "<REPO_ROOT>/extras",
            "models": [{"model_id": m["model_id"], "function": m["function"],
                        "availability": m["availability"],
                        "files": [{"path": f["path"], "bytes": f.get("bytes"),
                                   "sha256": f.get("sha256", "")[:16] + "...[trimmed]"}
                                  for f in m["files"]]} for m in data.get("models", [])],
            "note": "Full SHA256 values retained in local resources-verify.json; short prefix published",
        }
    except Exception as exc:
        inv["errors"].append(f"verify_parse: {type(exc).__name__}: {exc}")
else:
    inv["errors"].append("resources-verify.json not present")

ctx = BASE / "downloads" / "ctxprune"
nli = BASE / "downloads" / "nli"
komp = BASE / "kompress-source"
inv["downloads"]["ctxprune-small"] = {
    "revision": "bb52cb4eedcbd0961bed89bce3cf508e78e01418", "license": "apache-2.0",
    "source": "https://huggingface.co/darioooooo0o/ctxprune-small",
    "files": rows_from({p.name: p for p in ctx.iterdir() if p.is_file()},
                       "bb52cb4eedcbd0961bed89bce3cf508e78e01418", "apache-2.0",
                       "huggingface.co/darioooooo0o/ctxprune-small")}
inv["downloads"]["mnli_xnli"] = {
    "revision": "0a71e92a985b6e1ad1828cf67ce9c459639c1dca", "license": "mit",
    "source": "https://huggingface.co/MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli",
    "files": rows_from({p.name: p for p in nli.iterdir() if p.is_file()},
                       "0a71e92a985b6e1ad1828cf67ce9c459639c1dca", "mit",
                       "huggingface.co/MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli")}
komp_manifest = json.loads((pathlib.Path(r"<USERPROFILE>\AppData\Local\hermes\cache\scratch\kompress-zip") / "manifest.json").read_text(encoding="utf-8"))
inv["downloads"]["kompress-v2-base-jsons"] = {
    "revision": komp_manifest["revision"], "license": "apache-2.0",
    "source": "https://huggingface.co/chopratejas/kompress-v2-base",
    "verification": "git blob SHA1 checked by downloader for all four JSON files",
    "files": rows_from({p.name: p for p in komp.iterdir() if p.is_file() and p.suffix == ".json"},
                       komp_manifest["revision"], "apache-2.0",
                       "huggingface.co/chopratejas/kompress-v2-base",
                       {"git_blob_sha1_expected": {f["name"]: f["git_blob_sha1"] for f in komp_manifest["files"]}})}
local_zip = pathlib.Path(r"<DOWNLOADS_DIR>\ctxprune-main.zip")
if local_zip.exists():
    inv["downloads"]["ctxprune_source_zip"] = {
        "revision": "e49a1de270e0dc74090f5dfa0b4e79100c5421e7",
        "license": "see archive LICENSE", "source": "local Downloads/ctxprune-main.zip",
        "files": rows_from({"ctxprune-main.zip": local_zip}, "e49a1de270e0dc74090f5dfa0b4e79100c5421e7",
                           "see archive LICENSE", "local pre-existing download")}

p2 = BASE / "downloads" / "priority2"
if p2.exists():
    inv["downloads"]["priority2_source_archives"] = {
        "source": "github.com/rtk-ai/rtk, github.com/chopratejas/headroom",
        "revision": "download snapshot 2026-11-28; not executed or audited",
        "license": "see archives",
        "files": rows_from({p.name: p for p in p2.iterdir() if p.is_file()},
                           "snapshot-2026-11-28", "see archives", "github codeload snapshots"),
    }
inv["not_downloaded"] = {
    "llmlingua-2-multilingual": "NOT_DOWNLOADED: no ONNX artifact in upstream repo; PyTorch not installed; not needed for ITER07 smoke tests",
    "rtk_develop_branch": "master snapshot downloaded; default develop branch not fetched",
}
inv["runtime_packages"] = {
    "onnxruntime": "1.32.0", "numpy": "2.5.5", "tokenizers": "0.23.3", "sqlite-vec": "0.1.9",
    "installation": "isolated venv under ITER07-resources/.venv; no global install",
}
inv["exclusions"] = [
    "GGUF/ONNX weights not published", "extras/ excluded via .git/info/exclude before copy",
    "import plan with private paths kept local only", "sqlite-vec test DB is in-memory only",
    "no venv, cache, credential or session published",
]
inv["classification"] = "VERIFIED_BY_EXECUTOR" if not inv["errors"] else "EVIDENCE_PENDING"
OUT.write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
print(inv["classification"], "errors", inv["errors"], "download_groups", len(inv["downloads"]))
