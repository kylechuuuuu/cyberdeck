"""Palette, gradients and small text-drawing helpers."""

from __future__ import annotations

from dataclasses import dataclass

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class Palette:
    name: str
    label: str
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
    name="neon", label="赛博霓虹",
    cyan=(34, 211, 238), magenta=(244, 114, 182), purple=(168, 85, 247), blue=(56, 130, 246),
    green=(52, 211, 153), amber=(251, 191, 36), red=(251, 113, 133), dim=(124, 138, 160),
    text=(234, 240, 248), bg=(6, 9, 18), panel=(11, 17, 32),
    ocean_deep=(6, 24, 62), ocean_shallow=(16, 96, 168), land=(34, 130, 92),
    desert=(168, 142, 92), ice=(214, 236, 255), atmo=(64, 214, 255),
)

BTOP = Palette(
    name="btop", label="BTOP 绿",
    cyan=(56, 189, 248), magenta=(74, 222, 128), purple=(96, 165, 250), blue=(59, 130, 246),
    green=(74, 222, 128), amber=(251, 191, 36), red=(248, 113, 113), dim=(100, 116, 139),
    text=(226, 232, 240), bg=(6, 10, 14), panel=(10, 16, 22),
    ocean_deep=(8, 32, 48), ocean_shallow=(22, 110, 140), land=(52, 168, 110),
    desert=(170, 150, 100), ice=(220, 240, 250), atmo=(80, 200, 240),
)

AMBER = Palette(
    name="amber", label="琥珀 CRT",
    cyan=(251, 191, 36), magenta=(245, 158, 11), purple=(217, 119, 6), blue=(180, 83, 9),
    green=(234, 179, 8), amber=(253, 224, 71), red=(239, 68, 68), dim=(120, 96, 56),
    text=(253, 230, 138), bg=(8, 6, 3), panel=(18, 12, 6),
    ocean_deep=(30, 18, 4), ocean_shallow=(140, 88, 20), land=(214, 158, 46),
    desert=(240, 200, 120), ice=(255, 250, 220), atmo=(255, 190, 60),
)

MATRIX = Palette(
    name="matrix", label="矩阵绿",
    cyan=(0, 255, 130), magenta=(120, 255, 90), purple=(60, 220, 150), blue=(0, 190, 120),
    green=(140, 255, 150), amber=(190, 255, 110), red=(255, 90, 90), dim=(58, 110, 78),
    text=(198, 255, 214), bg=(2, 9, 5), panel=(6, 18, 11),
    ocean_deep=(3, 26, 15), ocean_shallow=(20, 96, 55), land=(34, 128, 62),
    desert=(126, 158, 74), ice=(206, 255, 214), atmo=(60, 255, 150),
)

NORD = Palette(
    name="nord", label="Nord",
    cyan=(136, 192, 208), magenta=(191, 97, 106), purple=(180, 142, 173), blue=(129, 161, 193),
    green=(163, 190, 140), amber=(235, 203, 139), red=(191, 97, 106), dim=(110, 120, 140),
    text=(236, 239, 244), bg=(32, 37, 47), panel=(42, 48, 60),
    ocean_deep=(36, 52, 70), ocean_shallow=(76, 118, 148), land=(122, 152, 122),
    desert=(190, 170, 126), ice=(232, 241, 250), atmo=(136, 192, 208),
)

GRUVBOX = Palette(
    name="gruvbox", label="Gruvbox",
    cyan=(142, 192, 124), magenta=(211, 134, 155), purple=(177, 98, 134), blue=(131, 165, 152),
    green=(184, 187, 38), amber=(250, 189, 47), red=(251, 73, 52), dim=(146, 131, 116),
    text=(235, 219, 178), bg=(29, 32, 33), panel=(40, 40, 40),
    ocean_deep=(30, 40, 44), ocean_shallow=(74, 104, 96), land=(120, 142, 86),
    desert=(200, 170, 100), ice=(240, 235, 210), atmo=(131, 165, 152),
)

TOKYO = Palette(
    name="tokyo", label="Tokyo Night",
    cyan=(125, 207, 255), magenta=(187, 154, 247), purple=(157, 124, 216), blue=(122, 162, 247),
    green=(158, 206, 106), amber=(224, 175, 104), red=(247, 118, 142), dim=(94, 106, 148),
    text=(192, 202, 245), bg=(26, 27, 38), panel=(36, 40, 59),
    ocean_deep=(22, 32, 62), ocean_shallow=(56, 100, 168), land=(88, 142, 118),
    desert=(190, 160, 112), ice=(222, 236, 255), atmo=(125, 207, 255),
)

SYNTH = Palette(
    name="synthwave", label="Synthwave",
    cyan=(0, 240, 255), magenta=(255, 60, 180), purple=(160, 80, 255), blue=(90, 120, 255),
    green=(0, 255, 190), amber=(255, 180, 60), red=(255, 70, 110), dim=(108, 88, 148),
    text=(240, 225, 255), bg=(14, 8, 26), panel=(26, 14, 44),
    ocean_deep=(20, 10, 54), ocean_shallow=(74, 40, 150), land=(146, 62, 190),
    desert=(255, 140, 190), ice=(255, 232, 255), atmo=(255, 60, 180),
)

PALETTES = [NEON, BTOP, AMBER, MATRIX, NORD, GRUVBOX, TOKYO, SYNTH]
P = NEON


def set_palette(index: int) -> Palette:
    global P
    P = PALETTES[index % len(PALETTES)]
    return P


def palette_index(name: str | None) -> int:
    for i, palette in enumerate(PALETTES):
        if palette.name == name:
            return i
    return 0


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


# --- text helpers -----------------------------------------------------------

def gauge(value: float, width: int, stops: list[RGB] | None = None,
          empty: str = "░", filled: str = "█") -> list[tuple[str, str]]:
    """Return (char, style) cells for a horizontal bar."""
    stops = stops or [P.cyan, P.purple, P.magenta]
    width = max(1, width)
    n = round(max(0.0, min(1.0, value)) * width)
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


def heat(value: float) -> RGB:
    """Colour ramp for a 0..1 load: cool at idle, hot at saturation."""
    return ramp([P.cyan, P.blue, P.purple, P.magenta, P.red], value)


def bar(value: float, width: int, filled: str = "█", empty: str = "░") -> tuple[str, str, RGB]:
    """(filled text, empty text, colour) for a solid load bar."""
    ratio = max(0.0, min(1.0, value))
    n = min(width, max(0, round(ratio * width)))
    return filled * n, empty * (width - n), heat(ratio)


def graph_rows(values: list[float], width: int, height: int = 2) -> tuple[list[str], list[float]]:
    """Rows of block characters for a tiny bar chart, plus normalised columns."""
    vals = list(values)[-width:]
    if not vals:
        vals = [0.0]
    hi = max(vals) or 1.0
    cols = [min(1.0, v / hi) for v in vals]
    cols += [0.0] * (width - len(cols))
    levels = [max(1, int(round(c * height * 8))) for c in cols]
    chars = " ▁▂▃▄▅▆▇█"
    rows: list[str] = []
    for r in range(height):
        base = (height - 1 - r) * 8
        rows.append("".join(chars[max(0, min(8, lv - base))] for lv in levels))
    return rows, cols


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
