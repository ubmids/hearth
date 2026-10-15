"""Contrast ratios for the tokens in design/DESIGN.md (WCAG 2.1 relative
luminance). Run it after changing a colour: python3 design/contrast.py
Text needs 4.5:1 (3:1 at 24 px and up, or 19 px bold); UI boundaries 3:1."""


def lum(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# Direction A, Care Card (the binding set while A is chosen).
A = {
    "light": dict(bg="#F4F5F1", surface="#FFFFFF", sunk="#E9ECE5", line="#D3D8CF",
                  line_strong="#6B7770", ink="#16201B", ink2="#46524B", ink3="#5F6B64",
                  care="#1D5C47", care_tint="#E1EFE7", on_care="#FFFFFF",
                  stop="#B42318", stop_tint="#FCEBE8",
                  caution="#7A4A00", caution_tint="#FFF0C7"),
    "dark": dict(bg="#101412", surface="#171D1A", sunk="#0B0E0D", line="#2A332E",
                 line_strong="#5F6D66", ink="#EDF1EE", ink2="#B4BFB8", ink3="#8F9B94",
                 care="#7CC9A5", care_tint="#16302A", on_care="#0B1A13",
                 stop="#FF8C7E", stop_tint="#3A1814",
                 caution="#F0C25A", caution_tint="#33280E"),
}

PAIRS = [  # (foreground, background, minimum)
    ("ink", "surface", 4.5), ("ink", "bg", 4.5), ("ink2", "surface", 4.5),
    ("ink3", "surface", 4.5), ("ink3", "bg", 4.5), ("care", "surface", 4.5),
    ("care", "care_tint", 4.5), ("on_care", "care", 4.5), ("stop", "surface", 4.5),
    ("stop", "stop_tint", 4.5), ("caution", "surface", 4.5),
    ("caution", "caution_tint", 4.5), ("line_strong", "bg", 3.0),
]

# The surfaces as they were on 15 Oct, for the audit in DESIGN.md.
BEFORE = [
    ("/alexa dim on panel", "#5f6b78", "#11151a"),
    ("/console section label", "#6f5f54", "#14100e"),
    ("card dim on card", "#8d7868", "#1a1411"),
]

if __name__ == "__main__":
    bad = 0
    for theme, p in A.items():
        for fg, bg, need in PAIRS:
            r = ratio(p[fg], p[bg])
            ok = r >= need
            bad += not ok
            print(f"A {theme:5} {fg:>12} on {bg:<12} {r:5.2f}  {'ok' if ok else 'FAIL'}")
    for name, fg, bg in BEFORE:
        print(f"before  {name:28} {ratio(fg, bg):5.2f}")
    raise SystemExit(1 if bad else 0)
