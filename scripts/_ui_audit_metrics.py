"""Objective audit metrics for the NSCP GUI. Prints facts, no opinions."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(r"C:\Users\KLSX\Documents\NSCP")
GUI = ROOT / "src" / "npsc_gui"


def hex_colors(text: str) -> list[str]:
    return re.findall(r"#[0-9A-Fa-f]{6}\b", text)


def main() -> None:
    files = sorted(GUI.rglob("*.py"))
    print("== FILE INVENTORY ==")
    total = 0
    for f in files:
        loc = len(f.read_text(encoding="utf-8", errors="replace").splitlines())
        total += loc
        print(f"  {loc:5d}  {f.relative_to(ROOT)}")
    print(f"  {total:5d}  TOTAL")

    print("\n== HARDCODED HEX COLORS PER FILE ==")
    for f in files:
        cols = hex_colors(f.read_text(encoding="utf-8", errors="replace"))
        if cols:
            uniq = sorted(set(c.upper() for c in cols))
            print(f"  {f.name:28s} {len(cols):4d} occurrences, {len(uniq):3d} unique")

    print("\n== INLINE setStyleSheet / setProperty CALLS ==")
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        n = len(re.findall(r"\.setStyleSheet\(", text))
        if n:
            print(f"  {f.name:28s} {n:4d}")

    print("\n== theme.py QSS DUPLICATE SELECTORS ==")
    qss = (GUI / "theme.py").read_text(encoding="utf-8", errors="replace")
    # selectors are the text before '{' at the start of a line, comments stripped
    sels = []
    for line in qss.splitlines():
        s = line.strip()
        if not s or s.startswith("/*") or s.startswith("*") or s.endswith("{") is False:
            continue
        if "{" in s:
            sel = s.split("{")[0].strip()
            if sel and not sel.startswith("{{"):
                sels.append(sel)
    seen: dict[str, int] = {}
    for s in sels:
        seen[s] = seen.get(s, 0) + 1
    dups = {k: v for k, v in seen.items() if v > 1}
    print(f"  total selector lines: {len(sels)}")
    for k, v in sorted(dups.items(), key=lambda x: -x[1]):
        print(f"  {v}x  {k}")

    print("\n== design_tokens.py USAGE ==")
    hits = []
    for f in ROOT.rglob("*.py"):
        if ".venv" in str(f) or "build" in str(f) or "dist" in str(f):
            continue
        t = f.read_text(encoding="utf-8", errors="replace")
        if "design_tokens" in t and f.name != "design_tokens.py":
            hits.append(str(f.relative_to(ROOT)))
    print("  importers:", hits or "NONE")

    print("\n== SPANISH LITERALS IN main_window.py (not tr()) ==")
    mw = (GUI / "main_window.py").read_text(encoding="utf-8", errors="replace")
    # string literals containing accented chars or typical Spanish words
    lits = re.findall(r'"([^"\n]{3,})"', mw)
    span = [s for s in lits if re.search(r"[áéíóúñ¿¡]|Prompt|perfil|Perfil|modo|Modo|Cancelar|Limpiar|Guardar|Copiar|Resultado|Validaci", s)]
    print(f"  candidate hardcoded ES strings: {len(span)}")
    for s in span[:40]:
        print("   -", s[:70])

    print("\n== QSS HARDCODED SIZES (px/pt) ==")
    sizes = re.findall(r"\b\d+(?:\.\d+)?(?:px|pt)\b", qss)
    print(f"  {len(sizes)} hardcoded size literals in theme.py")

    print("\n== GIF ==")
    gif = ROOT / "assets" / "icons" / "intro.gif"
    print("  bytes:", gif.stat().st_size)


if __name__ == "__main__":
    main()
