"""Second-pass objective audit metrics: QSS duplicates, contrast, i18n, GIF."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(r"C:\Users\KLSX\Documents\NSCP")
GUI = ROOT / "src" / "npsc_gui"


def srgb_to_lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return 0.2126 * srgb_to_lin(r) + 0.7152 * srgb_to_lin(g) + 0.0722 * srgb_to_lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def main() -> None:
    theme = (GUI / "theme.py").read_text(encoding="utf-8", errors="replace")

    print("== QSS SELECTOR OCCURRENCE COUNT (generated form) ==")
    # In the f-string the emitted QSS has "Selector\n{{". Count "X\n{{" patterns.
    sels = re.findall(r"^([A-Za-z][^\n{]*?)\s*\n\s*\{\{", theme, re.MULTILINE)
    counts: dict[str, int] = {}
    for s in sels:
        s = s.strip()
        if s.startswith("/*") or s.startswith("*"):
            continue
        counts[s] = counts.get(s, 0) + 1
    print(f"  selector entries: {len(sels)}")
    for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        if v > 1:
            print(f"  {v}x  {k}")

    print("\n== CONTRAST RATIOS (WCAG) ==")
    pairs_dark = [
        ("text_primary on bg_base", "#E8EAED", "#0B0D10"),
        ("text_primary on bg_card", "#E8EAED", "#1A1D22"),
        ("text_secondary on bg_card", "#A4A8AE", "#1A1D22"),
        ("text_muted on bg_card", "#6C717A", "#1A1D22"),
        ("text_muted on bg_base", "#6C717A", "#0B0D10"),
        ("text_on_accent on accent", "#FFFFFF", "#2B8BC8"),
        ("accent_brand on bg_card", "#4CB8F5", "#1A1D22"),
        ("state_success on bg_card", "#30B87A", "#1A1D22"),
        ("state_error on bg_card", "#E04E65", "#1A1D22"),
        ("state_warning on bg_card", "#E5A51A", "#1A1D22"),
        ("border_subtle vs bg_card", "#363A42", "#1A1D22"),
        ("border_input vs bg_card", "#4A5060", "#1A1D22"),
    ]
    pairs_light = [
        ("text_primary on bg_card", "#1A1D20", "#FFFFFF"),
        ("text_secondary on bg_card", "#5A5E64", "#FFFFFF"),
        ("text_muted on bg_card", "#8A8E94", "#FFFFFF"),
        ("text_on_accent on accent", "#FFFFFF", "#2B8BC8"),
        ("border_subtle vs bg_card", "#D0D2D4", "#FFFFFF"),
    ]
    for label, a, b in pairs_dark + [("LIGHT " + l, x, y) for l, x, y in pairs_light]:
        r = contrast(a, b)
        verdict = "AA-body" if r >= 4.5 else ("AA-large/UI" if r >= 3.0 else "FAIL")
        print(f"  {label:34s} {r:5.2f}:1  {verdict}")

    print("\n== i18n: hardcoded Spanish literals in main_window.py ==")
    mw = (GUI / "main_window.py").read_text(encoding="utf-8", errors="replace")
    lits = re.findall(r'"([^"\n]{2,})"', mw)
    ident = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
    es_words = re.compile(r"[áéíóúñÁÉÍÓÚÑ¿¡]|(^|\s)(de|del|la|el|los|las|un|una|con|para|por|que|se|no|si|al|lo)(\s|$)", re.I)
    hardcoded = []
    for s in lits:
        if ident.match(s):
            continue  # object names / ids
        if es_words.search(s):
            hardcoded.append(s)
    print(f"  {len(hardcoded)} hardcoded Spanish/user-facing literals")
    for s in hardcoded[:25]:
        print("   -", s[:64].replace("\n", " "))

    print("\n== GIF properties ==")
    from PySide6.QtGui import QImageReader

    r = QImageReader(str(ROOT / "assets" / "icons" / "intro.gif"))
    print("  size:", r.size().width(), "x", r.size().height(), "| frames:", r.imageCount())

    print("\n== FONT AVAILABILITY (native QPA) ==")
    from PySide6.QtGui import QFontDatabase

    fams = set(QFontDatabase.families())
    for want in ("Inter", "Segoe UI", "Noto Sans", "Cascadia Code", "JetBrains Mono", "Consolas"):
        print(f"  {want:16s} {'FOUND' if want in fams else 'MISSING'}")

    print("\n== IDLE VISIBILITY CHECK (simple mode) ==")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    from PySide6.QtWidgets import QApplication

    from npsc_gui.main_window import MainWindow

    app = QApplication([])
    w = MainWindow()
    checks = [
        ("simple_health (metric dashboard)", getattr(w, "simple_health", None)),
        ("simple_scan_container", getattr(w, "simple_scan_container", None)),
        ("simple_scan_ring", getattr(w, "simple_scan_ring", None)),
        ("simple_progress", getattr(w, "simple_progress", None)),
        ("simple_cancel_btn", getattr(w, "simple_cancel_btn", None)),
        ("adv_frame", getattr(w, "adv_frame", None)),
    ]
    for label, widget in checks:
        if widget is None:
            print(f"  {label:34s} MISSING")
        else:
            print(f"  {label:34s} visible={widget.isVisible()} (children={widget.findChildren(object).__len__()})")
    w.close()
    app.quit()


if __name__ == "__main__":
    main()
