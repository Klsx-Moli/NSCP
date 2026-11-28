"""Targeted GGUF scalar metadata extraction (avoids full-KV desync; no huge byte dumps)."""
import json
import pathlib
import struct

E = pathlib.Path(r"<EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines")
KEYS = [
    "general.architecture", "general.name", "general.author", "general.version",
    "general.file_type", "general.quantization_version", "general.size_label",
    "qwen3.context_length", "qwen3.embedding_length", "qwen3.block_count",
    "qwen3.pooling_type", "qwen3.feed_forward_length", "qwen3.attention.head_count",
    "qwen3.rope.dimension_count", "qwen3.rope.freq_base",
    "tokenizer.ggml.model", "tokenizer.ggml.pre",
]
# Verified against raw bytes: 4=UINT32 (context_length 0x8000, pooling_type 3),
# 6=FLOAT32 (rope.freq_base 0x49742400 == 1e6), 8=STRING, 9=ARRAY.
FMT = {0: "<?", 1: "<B", 2: "<b", 3: "<H", 4: "<I", 5: "<i",
       6: "<f", 10: "<Q", 11: "<q", 12: "<d"}


def extract(buf, key):
    needle = key.encode()
    pos = buf.find(needle)
    if pos < 0:
        return None
    i = pos + len(needle)
    if i + 4 > len(buf):
        return "TRUNCATED_TYPE"
    t = struct.unpack_from("<I", buf, i)[0]
    i += 4
    try:
        if t == 8:  # STRING
            n = struct.unpack_from("<Q", buf, i)[0]
            i += 8
            if n > 10000:
                return f"STRING_TOO_LONG:{n}"
            return buf[i:i + n].decode("utf-8", "replace")
        fmt = FMT.get(t)
        if not fmt:
            return f"TYPE_{t}_NOT_SCALAR"
        return struct.unpack_from(fmt, buf, i)[0]
    except Exception as exc:
        return f"ERROR:{type(exc).__name__}"


p = E / "MODEL_INVENTORY.json"
inv = json.loads(p.read_text(encoding="utf-8"))
for role, rec in inv["models"].items():
    with open(rec["path"], "rb") as f:
        buf = f.read(8 * 1024 * 1024)
    md = {k: extract(buf, k) for k in KEYS}
    rec["targeted_metadata"] = md
    rec["metadata_method"] = "targeted key scan on first 8 MiB; full-KV parse desynced on GGUF v3 tokenizer array"
    print(role, json.dumps({k: v for k, v in md.items() if v is not None}, ensure_ascii=False))
p.write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
print("updated MODEL_INVENTORY.json")
