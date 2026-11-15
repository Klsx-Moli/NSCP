"""Run UI Binder's heuristic vision over the NSCP screenshots (local, offline).

Creates one UIBinder workspace per screen, imports the screenshot as the
reference image, runs the heuristic analyzer and stores the resulting UI AST
plus the analysis notes. This gives an objective, OCR-free structural read of
the current interface (regions, panels, controls, containment hierarchy).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

API = "http://127.0.0.1:8799/api"
SHOTS = Path(r"C:\Users\KLSX\Documents\NSCP\screenshots\audit_before")
OUT = Path(r"C:\Users\KLSX\Documents\NSCP\.uibinder_audit\reports")
OUT.mkdir(parents=True, exist_ok=True)

SCREENS = [
    "01_simple_home_idle",
    "02_simple_loading",
    "03_simple_result_success",
    "04_extreme_dashboard",
    "05_extreme_compiler",
    "06_extreme_results",
    "07_extreme_validation",
    "08_extreme_glossary",
    "09_extreme_settings",
    "10_extreme_advanced",
    "11_simple_light_theme",
    "12_simple_error",
]

client = httpx.Client(base_url=API, timeout=120.0)
summary = []

for name in SCREENS:
    img = SHOTS / f"{name}.png"
    if not img.exists():
        print("skip (missing)", name)
        continue

    ws = client.post("/workspaces", json={"name": f"NSCP-{name}"}).json()
    ws_id = ws["id"]
    client.post(f"/workspaces/{ws_id}/snapshots", json={"label": "pre-edicion"})

    with open(img, "rb") as fh:
        rec = client.post(
            f"/workspaces/{ws_id}/images",
            params={"role": "reference"},
            files={"file": (img.name, fh, "image/png")},
        ).json()

    res = client.post(
        f"/workspaces/{ws_id}/analyze-ui",
        json={"image_id": rec["id"], "provider": "heuristic"},
    ).json()

    ui = client.get(f"/workspaces/{ws_id}/ui").json()
    (OUT / f"{name}.ui.json").write_text(json.dumps(ui, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / f"{name}.notes.json").write_text(
        json.dumps({"notes": res.get("notes"), "tokens": res.get("tokens")}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    comps = ui.get("ui", {}).get("components", [])
    types: dict[str, int] = {}
    for c in comps:
        t = c.get("type", "?")
        types[t] = types.get(t, 0) + 1
    summary.append(
        {
            "screen": name,
            "image_size": [rec.get("width"), rec.get("height")],
            "components": len(comps),
            "types": types,
            "notes": res.get("notes"),
            "ws_id": ws_id,
        }
    )
    print(f"{name}: {len(comps)} components {types}")

(OUT / "_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
print("\nwrote", OUT / "_summary.json")
