import json
from pathlib import Path

E = Path(__file__).parent
d = json.loads((E / "nscp_transport_real.json").read_text(encoding="utf-8"))
checks = {}
for route in ("legacy_summarize_turns", "strict_complete_summary"):
    text = d.get(route, {}).get("result") or ""
    checks[route] = {
        "status": d.get(route, {}).get("status"),
        "has_port_11435": "11435" in text,
        "has_config_service_py": "config/service.py" in text,
        "both": "11435" in text and "config/service.py" in text,
        "content": text[:400],
    }
out = {
    "source": "nscp_transport_real.json",
    "sha": d.get("sha"),
    "model": d.get("model"),
    "semantic_verdict": "PASS" if all(v["both"] and v["status"] == "PASS" for v in checks.values()) else "FAIL",
    "routes": checks,
}
(E / "transport_semantic_verification.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print(out["semantic_verdict"], {k: (v["has_port_11435"], v["has_config_service_py"]) for k, v in checks.items()})
