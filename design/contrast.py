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


# Direction C, Pharmacy Label (chosen 15 Oct 2026).
C = {
    "light": dict(desk="#ECECE7", paper="#FFFFFF", line="#D2D2CB", rule="#111111",
                  ink="#0B0B0B", ink2="#3A3A3A", ink3="#595954",
                  red="#C8201A", on_red="#FFFFFF", red_tint="#FCE9E7",
                  yellow="#FFD43B", on_yellow="#0B0B0B",
                  blue="#1F4FB5", on_blue="#FFFFFF", blue_tint="#E6EDFA",
                  green="#006B47", on_green="#FFFFFF", green_tint="#E2F2EA"),
    "dark": dict(desk="#0B0B0B", paper="#161616", line="#34342F", rule="#EDEDE8",
                 ink="#F5F5F0", ink2="#C8C8C2", ink3="#A0A09A",
                 red="#FF5A4E", on_red="#140303", red_tint="#3A1411",
                 yellow="#FFD43B", on_yellow="#0B0B0B",
                 blue="#8DB0FF", on_blue="#0B0B0B", blue_tint="#16213A",
                 green="#4FD19A", on_green="#04140D", green_tint="#0F2A1F"),
}

PAIRS = [  # (foreground, background, minimum)
    ("ink", "paper", 4.5), ("ink", "desk", 4.5), ("ink2", "paper", 4.5),
    ("ink3", "paper", 4.5), ("ink3", "desk", 4.5), ("rule", "paper", 3.0),
    ("red", "paper", 4.5), ("on_red", "red", 4.5), ("red", "red_tint", 4.5),
    ("on_yellow", "yellow", 4.5), ("blue", "paper", 4.5), ("on_blue", "blue", 4.5),
    ("blue", "blue_tint", 4.5), ("green", "paper", 4.5), ("on_green", "green", 4.5),
    ("green", "green_tint", 4.5), ("ink", "red_tint", 4.5), ("ink", "blue_tint", 4.5),
]

# The surfaces as they were on 15 Oct, for the audit in DESIGN.md.
BEFORE = [
    ("/alexa dim on panel", "#5f6b78", "#11151a"),
    ("/console section label", "#6f5f54", "#14100e"),
    ("card dim on card", "#8d7868", "#1a1411"),
]

if __name__ == "__main__":
    bad = 0
    for theme, p in C.items():
        for fg, bg, need in PAIRS:
            r = ratio(p[fg], p[bg])
            ok = r >= need
            bad += not ok
            print(f"C {theme:5} {fg:>12} on {bg:<12} {r:5.2f}  {'ok' if ok else 'FAIL'}")
    for name, fg, bg in BEFORE:
        print(f"before  {name:28} {ratio(fg, bg):5.2f}")
    raise SystemExit(1 if bad else 0)
