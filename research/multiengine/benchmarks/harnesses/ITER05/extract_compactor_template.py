"""Extract Compactor chat template and qwen35 metadata from GGUF (targeted, bounded)."""
import json
import pathlib
import struct

E = pathlib.Path(r"<EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines")
p = E / "MODEL_INVENTORY.json"
inv = json.loads(p.read_text(encoding="utf-8"))
model = inv["models"]["compactor"]["path"]
with open(model, "rb") as f:
    buf = f.read(16 * 1024 * 1024)


def val(key):
    n = key.encode()
    i = buf.find(n)
    if i < 0:
        return None
    i += len(n)
    t = struct.unpack_from("<I", buf, i)[0]
    i += 4
    if t == 8:
        ln = struct.unpack_from("<Q", buf, i)[0]
        i += 8
        if ln > 200000:
            return f"TOO_LONG:{ln}"
        return buf[i:i + ln].decode("utf-8", "replace")
    fmt = {4: "<I", 5: "<i", 6: "<f", 10: "<Q", 11: "<q", 12: "<d"}.get(t)
    return struct.unpack_from(fmt, buf, i)[0] if fmt else f"TYPE_{t}"


keys = ["tokenizer.chat_template", "tokenizer.ggml.chat_template", "tokenizer.ggml.eos_token_id",
        "qwen35.context_length", "qwen35.embedding_length", "qwen35.block_count",
        "qwen35.feed_forward_length", "qwen35.attention.head_count", "general.file_type",
        "general.quantization_version", "general.size_label"]
md = {k: val(k) for k in keys}
inv["models"]["compactor"]["targeted_metadata"].update({k: v for k, v in md.items() if v is not None})
p.write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
tmpl = md.get("tokenizer.chat_template") or md.get("tokenizer.ggml.chat_template") or ""
(E / "COMPACTOR_CHAT_TEMPLATE.txt").write_text(str(tmpl), encoding="utf-8")
print(json.dumps({k: (str(v)[:1200] if isinstance(v, str) else v) for k, v in md.items() if v is not None}, ensure_ascii=False)[:3000])
