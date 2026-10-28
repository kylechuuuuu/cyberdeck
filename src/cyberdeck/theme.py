"""Palette, gradients and small text-drawing helpers."""

from __future__ import annotations

from dataclasses import dataclass

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class Palette:
    name: str
    cyan: RGB
    magenta: RGB
    purple: RGB
    blue: RGB
    green: RGB
    amber: RGB
    red: RGB
    dim: RGB
    text: RGB
    bg: RGB
    panel: RGB
    # globe
    ocean_deep: RGB
    ocean_shallow: RGB
    land: RGB
    desert: RGB
    ice: RGB
    atmo: RGB


NEON = Palette(
    name="neon",
    cyan=(34, 211, 238),
    magenta=(244, 114, 182),
    purple=(168, 85, 247),
    blue=(56, 130, 246),
    green=(52, 211, 153),
    amber=(251, 191, 36),
    red=(251, 113, 133),
    dim=(100, 116, 139),
    text=(226, 232, 240),
    bg=(5, 8, 18),
    panel=(9, 14, 28),
    ocean_deep=(6, 24, 62),
    ocean_shallow=(16, 96, 168),
    land=(34, 130, 92),
    desert=(168, 142, 92),
    ice=(214, 236, 255),
    atmo=(64, 214, 255),
)

BTOP = Palette(
    name="btop",
    cyan=(56, 189, 248),
    magenta=(74, 222, 128),
    purple=(96, 165, 250),
    blue=(59, 130, 246),
    green=(74, 222, 128),
    amber=(251, 191, 36),
    red=(248, 113, 113),
    dim=(100, 116, 139),
    text=(226, 232, 240),
    bg=(6, 10, 14),
    panel=(10, 16, 22),
    ocean_deep=(8, 32, 48),
    ocean_shallow=(22, 110, 140),
    land=(52, 168, 110),
    desert=(170, 150, 100),
    ice=(220, 240, 250),
    atmo=(80, 200, 240),
)

AMBER = Palette(
    name="amber",
    cyan=(251, 191, 36),
    magenta=(245, 158, 11),
    purple=(217, 119, 6),
    blue=(180, 83, 9),
    green=(234, 179, 8),
    amber=(253, 224, 71),
    red=(239, 68, 68),
    dim=(120, 96, 56),
    text=(253, 230, 138),
    bg=(8, 6, 3),
    panel=(18, 12, 6),
    ocean_deep=(30, 18, 4),
    ocean_shallow=(140, 88, 20),
    land=(214, 158, 46),
    desert=(240, 200, 120),
    ice=(255, 250, 220),
    atmo=(255, 190, 60),
)

PALETTES = [NEON, BTOP, AMBER]
P = NEON


def set_palette(index: int) -> Palette:
    global P
    P = PALETTES[index % len(PALETTES)]
    return P


def hexc(c: RGB) -> str:
    return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"


def mix(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def ramp(stops: list[RGB], t: float) -> RGB:
    """Sample a multi-stop gradient at 0..1."""
    t = max(0.0, min(1.0, t))
    if len(stops) == 1:
        return stops[0]
    pos = t * (len(stops) - 1)
    i = min(int(pos), len(stops) - 2)
    return mix(stops[i], stops[i + 1], pos - i)


def blend_bg(fg: RGB, bg: RGB, alpha: float) -> RGB:
    return mix(bg, fg, alpha)


# --- text helpers -----------------------------------------------------------

def gauge(value: float, width: int, stops: list[RGB] | None = None,
          empty: str = "░", filled: str = "█") -> list[tuple[str, str]]:
    """Return (char, style) cells for a horizontal bar."""
    stops = stops or [P.cyan, P.purple, P.magenta]
    width = max(1, width)
    n = int(round(max(0.0, min(1.0, value)) * width))
    out: list[tuple[str, str]] = []
    for i in range(width):
        if i < n:
            out.append((filled, hexc(ramp(stops, i / max(1, width - 1)))))
        else:
            out.append((empty, hexc(mix(P.dim, P.panel, 0.35))))
    return out


def sparkline(values: list[float], width: int) -> str:
    chars = "▁▂▃▄▅▆▇█"
    if not values:
        return "▁" * width
    vals = values[-width:]
    hi = max(vals) or 1.0
    s = "".join(chars[min(7, int(v / hi * 7.99))] for v in vals)
    return s.rjust(width, "▁")


def fmt_bytes(n: float) -> str:
    for unit in ("B", "K", "M", "G", "T"):
        if abs(n) < 1024 or unit == "T":
            return f"{n:3.1f}{unit}" if unit != "B" else f"{int(n)}B"
        n /= 1024
    return f"{n:.1f}T"


def fmt_rate(bps: float) -> str:
    return fmt_bytes(bps) + "/s"


def fmt_uptime(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}d {h:02d}:{m:02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"
