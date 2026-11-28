"""Local resource catalog and no-clobber import for NSCP.

No downloads, model execution, external configuration changes or recursive
personal-file discovery. All write operations are explicit and local.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

CATALOG = {
    "qwen3-embedding-0.6b-q8": ("embedding", "Qwen3-Embedding-0.6B-Q8_0.gguf"),
    "qwen3-reranker-0.6b-q8": ("reranking", "qwen3-reranker-0.6b-q8_0.gguf"),
    "compactor-qwen3.5-4b-q4": ("compaction", "Compactor-Qwen3.5-4B.Q4_K_M.gguf"),
    "kompress-v2-base-int8": ("extraction", "kompress-int8-wo.onnx"),
    "ctxprune-small-int8": ("extraction", "model_quantized.onnx"),
    "multilingual-minilm-nli-onnx": ("nli", "model.onnx"),
}
KOMPRESS_FILES = ("config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json")
BUNDLE_CONFIGS = {
    "kompress-v2-base-int8": KOMPRESS_FILES,
    "ctxprune-small-int8": ("config.json", "tokenizer.json", "tokenizer_config.json"),
    "multilingual-minilm-nli-onnx": (*KOMPRESS_FILES, "sentencepiece.bpe.model"),
}
SCHEMA = "nscp/local-resources/v1"


def root_path(explicit=None):
    """CLI > process environment > checkout-local extras.

    Installed wheels require an explicit root or NSCP_EXTRAS_DIR/NSCP_HOME.
    Do not write next to an installed Python module by accident.
    """
    value = explicit or os.environ.get("NSCP_EXTRAS_DIR")
    if not value and os.environ.get("NSCP_HOME"):
        value = Path(os.environ["NSCP_HOME"]) / "extras"
    if not value:
        checkout = Path(__file__).resolve().parents[1]
        if not (checkout / "pyproject.toml").is_file() or not (checkout / ".git").exists():
            raise ValueError("Set --root or NSCP_EXTRAS_DIR for installed usage")
        value = checkout / "extras"
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Resource root must be absolute")
    return path.resolve()


def _child(root, *parts):
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root):
        raise ValueError("Resource path escapes root")
    # Existing symlink/junction components are not an implicit install target.
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError("Linked resource path rejected")
    return path


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def model_files(model_id):
    category, filename = CATALOG[model_id]
    base = ("models", category, model_id)
    if model_id in BUNDLE_CONFIGS:
        return [(*base, "onnx", filename), *[(*base, f) for f in BUNDLE_CONFIGS[model_id]]]
    return [(*base, filename)]


def inventory(root, *, verify=False):
    rows = []
    for mid in CATALOG:
        files = []
        for parts in model_files(mid):
            path = _child(root, *parts)
            item = {"path": Path(*parts).as_posix(), "exists": path.is_file()}
            if item["exists"]:
                item["bytes"] = path.stat().st_size
                if verify:
                    item["sha256"] = file_hash(path)
            files.append(item)
        present = sum(f["exists"] and f.get("bytes", 0) > 0 for f in files)
        rows.append({"model_id": mid, "function": CATALOG[mid][0],
                     "availability": ("PRESENT" if present == len(files) else
                                      "PARTIAL" if present else "MISSING"),
                     "files": files, "source_integrity": "not_verified",
                     "inference": "not_verified"})
    return {"schema": SCHEMA, "models": rows}


def plan_import(root, source_dirs, *, model_ids=None):
    """Search only the supplied directories and the known native ONNX folder."""
    dirs = [Path(p).expanduser().resolve(strict=True) for p in source_dirs]
    if any(not d.is_dir() for d in dirs):
        raise ValueError("Import sources must be directories")
    selected = list(CATALOG) if model_ids is None else list(model_ids)
    if len(set(selected)) != len(selected) or any(mid not in CATALOG for mid in selected):
        raise ValueError("Invalid model selection")
    result = []
    for mid in selected:
        paths = model_files(mid)
        # Multi-file bundles must come from one explicit source directory,
        # never mix tokenizer/config files found in unrelated folders.
        for directory in dirs:
            candidates = []
            for parts in paths:
                dest = _child(root, *parts)
                name = parts[-1]
                src = directory / "onnx" / name if parts[-2] == "onnx" else directory / name
                if not src.is_file() and parts[-2] == "onnx":
                    src = directory / name
                if not src.is_file() or src.stat().st_size == 0:
                    break
                if src.is_symlink() or not src.resolve().is_relative_to(directory):
                    raise ValueError("Linked or external source rejected")
                candidates.append((src, dest))
            if len(candidates) != len(paths):
                continue
            for src, dest in candidates:
                digest = file_hash(src)
                action = "copy"
                if dest.exists():
                    action = ("reuse" if dest.is_file() and file_hash(dest) == digest
                              else "conflict")
                result.append({"model_id": mid, "source": str(src), "target": str(dest),
                               "bytes": src.stat().st_size, "sha256": digest, "action": action})
            break
    return result


def apply_import(root, rows, *, min_free_bytes=25 * 1024**3):
    """Verify source and copied bytes; never replace a destination.

    Hard-link publication is atomic and fails if a destination already exists.
    The link is to a private temporary copy, never to the user's original.
    A partially completed multi-file import remains PARTIAL and can be resumed.
    """
    if any(r["action"] not in ("copy", "reuse") for r in rows):
        raise ValueError("Import conflicts; no writes made")
    root.mkdir(parents=True, exist_ok=True)
    required = sum(r["bytes"] for r in rows if r["action"] == "copy")
    if shutil.disk_usage(root).free < required + min_free_bytes:
        raise ValueError("Insufficient free space")
    for row in rows:
        source = Path(row["source"])
        target = Path(row["target"])
        parts = target.relative_to(root).parts
        if _child(root, *parts) != target:
            raise ValueError("Invalid target")
        if tuple(parts) not in model_files(row["model_id"]):
            raise ValueError("Unexpected model destination")
        if file_hash(source) != row["sha256"]:
            raise ValueError("Source changed since planning")
        if row["action"] == "reuse":
            if not target.is_file() or file_hash(target) != row["sha256"]:
                raise ValueError("Existing resource changed since planning")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        _child(root, *parts)
        fd, tmp_name = tempfile.mkstemp(prefix=".nscp-import-", dir=target.parent)
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as out, source.open("rb") as inp:
                shutil.copyfileobj(inp, out)
                out.flush()
                os.fsync(out.fileno())
            if tmp.stat().st_size != row["bytes"] or file_hash(tmp) != row["sha256"]:
                raise ValueError("Copied resource failed integrity check")
            os.link(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
    return inventory(root)


def run_cli(argv=None):
    parser = argparse.ArgumentParser(prog="nscp-resources")
    parser.add_argument("--root", help="Absolute local shared extras directory")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("verify")
    imp = sub.add_parser("import-local")
    imp.add_argument("--from-dir", action="append", required=True)
    imp.add_argument("--model-id", action="append", choices=tuple(CATALOG),
                     help="Limit import to an explicit model, repeatable")
    imp.add_argument("--apply", action="store_true", help="Without this flag, read-only plan")
    args = parser.parse_args(argv)
    try:
        root = root_path(args.root)
        if args.command == "import-local":
            rows = plan_import(root, args.from_dir, model_ids=args.model_id)
            if args.apply:
                result = apply_import(root, rows)
            else:
                result = {"schema": SCHEMA, "mode": "read_only", "plan": rows}
        else:
            result = inventory(root, verify=args.command == "verify")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
