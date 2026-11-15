"""Design-system verification: token purity + WCAG contrast.

Run after any change to the visual layer:
    PYTHONPATH=src .venv/Scripts/python.exe scripts/_ui_design_verify.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\KLSX\Documents\NSCP")
GUI = ROOT / "src" / "npsc_gui"

FAILURES: list[str] = []
WARNINGS: list[str] = []


def lin(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def main() -> int:
    from npsc_gui.design import build_qss, get_theme
    from npsc_gui.design.builder import build_qss as builder_build
    from npsc_gui.theme import QSS_DARK, QSS_LIGHT, get_qss

    print("== 1. TOKEN PURITY: builder.py must contain no colours or raw sizes ==")
    builder_src = (GUI / "design" / "builder.py").read_text(encoding="utf-8")
    hexes = re.findall(r"#[0-9A-Fa-f]{3,8}\b", builder_src)
    check(not hexes, f"builder.py contains hex colours: {sorted(set(hexes))}")
    raw_sizes = re.findall(r"(?<![\w-])(\d+(?:\.\d+)?)(px|pt)\b", builder_src)
    nonzero = [(v, u) for v, u in raw_sizes if float(v) != 0]
    for v, u in nonzero:
        WARNINGS.append(f"builder.py raw size literal: {v}{u}")
    print(f"  hex colours: {len(hexes)} | raw non-zero size literals: {len(nonzero)}")

    print("\n== 2. SINGLE SOURCE: theme facade delegates to the design system ==")
    check(get_qss("dark") == build_qss(get_theme("dark")), "get_qss('dark') != build_qss")
    check(get_qss("light") == build_qss(get_theme("light")), "get_qss('light') != build_qss")
    check(QSS_DARK == build_qss(get_theme("dark")), "QSS_DARK stale")
    check(QSS_LIGHT == build_qss(get_theme("light")), "QSS_LIGHT stale")
    print("  facade matches builder for both themes")

    print("\n== 3. NO DUPLICATE SELECTORS ==")
    for name in ("dark", "light"):
        qss = get_qss(name)
        selectors = re.findall(r"^([^\n{}]+?)\s*\{", qss, re.MULTILINE)
        dups = {s.strip() for s in selectors if selectors.count(s.strip()) > 1}
        check(not dups, f"{name}: duplicate selectors {sorted(dups)}")
        print(f"  {name}: {len(selectors)} selectors, duplicates: {len(dups)}")

    print("\n== 4. WCAG CONTRAST: text pairs (target >= 4.5:1) ==")
    for theme in ("dark", "light"):
        p = get_theme(theme).palette
        surfaces = {
            "bg_base": p.bg_base,
            "bg_surface": p.bg_surface,
            "bg_raised": p.bg_raised,
            "bg_input": p.bg_input,
            "bg_sidebar": p.bg_sidebar,
        }
        for text_name, fg in (
            ("text_primary", p.text_primary),
            ("text_secondary", p.text_secondary),
            ("text_tertiary", p.text_tertiary),
            ("accent_brand", p.accent_brand),
            ("success", p.success),
            ("warning", p.warning),
            ("error", p.error),
        ):
            for surf_name, bg in surfaces.items():
                ratio = contrast(fg, bg)
                check(ratio >= 4.5, f"{theme} {text_name} on {surf_name}: {ratio:.2f}:1")
                flag = "ok " if ratio >= 4.5 else "FAIL"
                print(f"  [{flag}] {theme:5s} {text_name:14s} on {surf_name:12s} {ratio:5.2f}:1")

    print("\n== 5. WCAG CONTRAST: text on filled accents (target >= 4.5:1) ==")
    for theme in ("dark", "light"):
        p = get_theme(theme).palette
        for name, bg in (
            ("accent_primary", p.accent_primary),
            ("accent_hover", p.accent_hover),
            ("success_filled", p.success_filled),
            ("error_filled", p.error_filled),
        ):
            ratio = contrast(p.text_on_accent, bg)
            check(ratio >= 4.5, f"{theme} text_on_accent on {name}: {ratio:.2f}:1")
            flag = "ok " if ratio >= 4.5 else "FAIL"
            print(f"  [{flag}] {theme:5s} on {name:16s} {ratio:5.2f}:1")

    print("\n== 6. WCAG CONTRAST: interactive field boundaries (target >= 3:1) ==")
    for theme in ("dark", "light"):
        p = get_theme(theme).palette
        for surf_name, bg in (
            ("bg_raised", p.bg_raised),
            ("bg_input", p.bg_input),
            ("bg_surface", p.bg_surface),
            ("bg_base", p.bg_base),
        ):
            ratio = contrast(p.border_strong, bg)
            check(ratio >= 3.0, f"{theme} border_strong on {surf_name}: {ratio:.2f}:1")
            flag = "ok " if ratio >= 3.0 else "FAIL"
            print(f"  [{flag}] {theme:5s} border_strong on {surf_name:12s} {ratio:5.2f}:1")

    print("\n== 7. WIDGETS MUST NOT CARRY THEIR OWN COLOURS ==")
    for path in sorted(GUI.rglob("*.py")):
        if "design" in path.parts or path.name == "theme.py":
            continue
        src = path.read_text(encoding="utf-8")
        found = re.findall(r"#[0-9A-Fa-f]{6}\b", src)
        if found:
            WARNINGS.append(f"{path.relative_to(ROOT)}: {len(found)} hex colours")

    print("\n== 8. STATE COVERAGE ==")
    qss = get_qss("dark")
    for state in (":hover", ":pressed", ":focus", ":disabled", ":selected", ":checked"):
        count = qss.count(state)
        print(f"  {state:12s} {count:3d} rules")
        check(count > 0, f"missing state rules for {state}")

    print("\n" + "=" * 60)
    for w in WARNINGS:
        print("WARN:", w)
    if FAILURES:
        print(f"\nFAIL ({len(FAILURES)}):")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("\nPASS: design system verification green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
