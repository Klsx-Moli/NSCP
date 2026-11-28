"""Re-parse GGUF metadata with the correct llama.cpp type enum; hashes are reused, not recomputed."""
import json
import pathlib
import sys

E = pathlib.Path(r"<EVIDENCE_DIR>\2026-11-27_iter05_specialized_engines")
sys.path.insert(0, str(E))
import inventory_and_runtime as m  # noqa: E402

# GGUF_TYPE: BOOL0,UINT8 1,INT8 2,UINT16 3,INT16 4,UINT32 5,INT32 6,FLOAT32 7,
#            STRING 8,ARRAY 9,UINT64 10,INT64 11,FLOAT64 12
m.NAMES = {0: "BOOL", 1: "UINT8", 2: "INT8", 3: "UINT16", 4: "INT16", 5: "UINT32",
           6: "INT32", 7: "FLOAT32", 8: "STRING", 9: "ARRAY", 10: "UINT64",
           11: "INT64", 12: "FLOAT64"}


def fixed_string(self):
    return self.raw(self.u64()).decode("utf-8", "replace")


def fixed_value(self, t):
    if t == 8:
        return self.string()
    if t == 9:
        et = self.u32()
        n = self.u64()
        if n > 1_000_000:
            raise ValueError("implausible array")
        if et == 8:
            return [self.string() for _ in range(n)]
        return [self.value(et) for _ in range(n)]
    fmt = {0: "<?", 1: "<B", 2: "<b", 3: "<H", 4: "<h", 5: "<I", 6: "<i",
           7: "<f", 10: "<Q", 11: "<q", 12: "<d"}.get(t)
    if not fmt:
        raise ValueError(f"unknown type {t}")
    return __import__("struct").unpack(fmt, self.raw(__import__("struct").calcsize(fmt)))[0]


m.Reader.string = fixed_string
m.Reader.value = fixed_value

p = E / "MODEL_INVENTORY.json"
inv = json.loads(p.read_text(encoding="utf-8"))
for role, rec in inv["models"].items():
    rec["gguf"] = m.gguf_meta(rec["path"])
    g = rec["gguf"]
    md = g.get("metadata", {})
    print(role, g.get("parse_status"), "arch=", md.get("general.architecture"),
          "ctx=", md.get("general.context_length") or md.get("qwen3.context_length") or md.get("qwen3.rope.dimension_count"),
          "name=", md.get("general.name"), "error=", g.get("parse_error"))
p.write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
print("MODEL_INVENTORY.json metadata updated; hashes unchanged")
