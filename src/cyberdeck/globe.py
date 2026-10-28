"""Rotating Earth: numpy sphere renderer + Textual widget.

The renderer orthographically projects a textured sphere into an RGB pixel
buffer (2 pixels per terminal cell), light it with a fixed sun, adds an
atmosphere rim and a starfield, then the widget packs the buffer into
half-block characters (truecolor foreground + background per cell).
"""

from __future__ import annotations

import math
import time
from importlib import resources

import numpy as np
from rich.text import Text
from textual.widget import Widget

from . import theme

TILT = 18.0  # visual axial tilt, degrees


# --------------------------------------------------------------------------
# texture
# --------------------------------------------------------------------------

def _box_blur(a: np.ndarray, radius: int, passes: int = 3) -> np.ndarray:
    """Separable box blur with latitude clamping (cheap coastal softness)."""
    out = a.astype(np.float32)
    for _ in range(passes):
        # horizontal, wraps at the antimeridian
        pad = np.concatenate([out[:, -radius:], out, out[:, :radius]], axis=1)
        csum = np.cumsum(pad, axis=1, dtype=np.float32)
        csum = np.concatenate([np.zeros((csum.shape[0], 1), np.float32), csum], axis=1)
        out = (csum[:, 2 * radius + 1:] - csum[:, : -2 * radius - 1]) / (2 * radius + 1)
        # vertical, clamps at the poles
        vp = np.concatenate([np.repeat(out[:1], radius, 0), out, np.repeat(out[-1:], radius, 0)], axis=0)
        vc = np.cumsum(vp, axis=0, dtype=np.float32)
        vc = np.concatenate([np.zeros((1, vc.shape[1]), np.float32), vc], axis=0)
        out = (vc[2 * radius + 1:] - vc[: -2 * radius - 1]) / (2 * radius + 1)
    return out


class EarthTexture:
    """Equirectangular land mask + derived shallow-water and albedo detail."""

    def __init__(self, mask: np.ndarray) -> None:
        self.mask = mask.astype(np.float32)
        self.h, self.w = self.mask.shape
        self.shallow = _box_blur(self.mask, 5)

        rng = np.random.default_rng(7)
        noise = _box_blur(rng.random((self.h, self.w)).astype(np.float32), 9, passes=2)
        noise = (noise - noise.min()) / max(1e-6, noise.max() - noise.min())
        self.detail = noise.astype(np.float32)

    @classmethod
    def load(cls) -> EarthTexture:
        ref = resources.files("cyberdeck.data").joinpath("landmask.npz")
        with resources.as_file(ref) as path, np.load(path) as f:
            return cls(f["land"])

    def _sample(self, grid: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        x = u * self.w - 0.5
        y = v * self.h - 0.5
        x0 = np.floor(x).astype(np.int32)
        y0 = np.floor(y).astype(np.int32)
        fx = (x - x0).astype(np.float32)
        fy = (y - y0).astype(np.float32)
        x0 %= self.w
        x1 = (x0 + 1) % self.w
        y0c = np.clip(y0, 0, self.h - 1)
        y1c = np.clip(y0 + 1, 0, self.h - 1)
        a = grid[y0c, x0]
        b = grid[y0c, x1]
        c = grid[y1c, x0]
        d = grid[y1c, x1]
        top = a * (1 - fx) + b * fx
        bot = c * (1 - fx) + d * fx
        return top * (1 - fy) + bot * fy

    def sample(self, u: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return (
            self._sample(self.mask, u, v),
            self._sample(self.shallow, u, v),
            self._sample(self.detail, u, v),
        )


# --------------------------------------------------------------------------
# renderer
# --------------------------------------------------------------------------

def _smoothstep(x: np.ndarray, a: float, b: float) -> np.ndarray:
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


class GlobeEngine:
    def __init__(self, texture: EarthTexture | None = None) -> None:
        self.tex = texture or EarthTexture.load()
        self._grids: dict[tuple[int, int], dict[str, np.ndarray]] = {}

    def _grid(self, w: int, h: int) -> dict[str, np.ndarray]:
        key = (w, h)
        g = self._grids.get(key)
        if g is not None:
            return g

        ph = 2 * h
        px = np.arange(w, dtype=np.float32) + 0.5
        py = np.arange(ph, dtype=np.float32) + 0.5
        r = max(4.0, min(w / 2.0, h * 1.0) * 0.88)
        nx = (px[None, :] - w / 2.0) / r
        ny = (h - py[:, None]) / r
        r2 = nx * nx + ny * ny
        inside = r2 <= 1.0
        nz = np.sqrt(np.clip(1.0 - r2, 0.0, 1.0))

        dist = np.sqrt(r2)
        edge = np.clip((1.0 - dist) * r + 0.5, 0.0, 1.0)[..., None]
        out = np.clip(dist - 1.0, 0.0, None)
        halo = np.exp(-((out * 3.0) ** 2)) * 0.30 + np.exp(-out * 13.0) * 0.22
        glow = (halo * (dist > 1.0))[..., None]

        rng = np.random.default_rng(1234 + w * 7919 + h)
        star_sel = rng.random((ph, w)) > 0.9955
        star_b = (rng.random((ph, w)) ** 3 * 0.9 + 0.1).astype(np.float32)
        star_phase = (rng.random((ph, w)) * 6.283).astype(np.float32)

        g = {
            "nx": nx, "ny": ny, "nz": nz, "r2": r2, "inside": inside,
            "edge": edge, "glow": glow,
            "stars": star_sel, "star_b": star_b, "star_phase": star_phase,
        }
        if len(self._grids) > 6:  # resizing hard: keep the cache tiny
            self._grids.clear()
        self._grids[key] = g
        return g

    def render(self, w: int, h: int, yaw: float, t: float, tilt: float = TILT) -> np.ndarray:
        g = self._grid(w, h)
        p = theme.P
        nx, ny, nz = g["nx"], g["ny"], g["nz"]

        # background + twinkling stars
        bg = np.empty((2 * h, w, 3), np.float32)
        bg[...] = np.array(p.bg, np.float32)
        twinkle = 0.55 + 0.45 * np.sin(t * 1.7 + g["star_phase"])
        star = g["stars"][..., None] * (g["star_b"] * twinkle)[..., None]
        bg += star * np.array((150, 200, 255), np.float32) * 0.9

        # sphere normal -> object space
        ct, st = math.cos(math.radians(tilt)), math.sin(math.radians(tilt))
        cy, sy = math.cos(yaw), math.sin(yaw)
        y1 = ny * ct + nz * st
        z1 = -ny * st + nz * ct
        x2 = nx * cy - z1 * sy
        z2 = nx * sy + z1 * cy

        lat = np.arcsin(np.clip(y1, -1.0, 1.0))
        lon = np.arctan2(x2, z2)
        u = (lon + np.pi) / (2 * np.pi)
        v = (np.pi / 2 - lat) / np.pi
        land, shallow, detail = self.tex.sample(u, v)

        ocean = np.array(p.ocean_deep, np.float32) + (
            np.array(p.ocean_shallow, np.float32) - np.array(p.ocean_deep, np.float32)
        ) * np.clip(shallow * 3.4, 0, 1)[..., None] * 0.9
        ocean *= (0.80 + 0.42 * detail)[..., None]

        desert_belt = np.exp(-(((np.abs(lat) - 0.42) / 0.17) ** 2))
        ground = np.array(p.land, np.float32) + (
            np.array(p.desert, np.float32) - np.array(p.land, np.float32)
        ) * (desert_belt * (0.55 + 0.45 * detail))[..., None]
        ice_amt = np.clip(_smoothstep(np.abs(lat), 1.16, 1.40) + (detail - 0.5) * 0.15, 0, 1)
        ground = ground + (np.array(p.ice, np.float32) - ground) * ice_amt[..., None]

        col = ocean * (1 - land[..., None]) + ground * land[..., None]

        # sunlight: low, from the upper-left, so the terminator sweeps visibly
        lx, ly, lz = -0.72, 0.30, 0.63
        ln = math.sqrt(lx * lx + ly * ly + lz * lz)
        diff = np.clip((nx * lx + ny * ly + nz * lz) / ln, 0.0, 1.0)
        day = _smoothstep(diff, -0.02, 0.58)
        light = 0.055 + 0.98 * day

        col = col * light[..., None]
        # night side picks up a faint violet sky glow
        night = ((1 - day) * g["inside"])[..., None]
        col = col + (np.array((20, 12, 42), np.float32) - col * 0.55) * night * 0.55

        # city lights on the dark side (land only, sparse detail mask)
        city = (land * _smoothstep(detail, 0.52, 0.86) * (1 - day) ** 1.6)[..., None]
        col = col + np.array((255, 176, 96), np.float32) * city * 0.55

        # ocean specular
        spec = (diff ** 16) * (1 - land) * 110
        col = col + spec[..., None] * np.array((0.75, 0.9, 1.0), np.float32)

        # limb darkening + inner atmosphere
        col *= (0.70 + 0.30 * nz)[..., None]
        rim = (np.clip((g["r2"] - 0.62) / 0.38, 0, 1) ** 3.2)[..., None]
        col = col + np.array(p.atmo, np.float32) * rim * (0.16 + 0.34 * day)[..., None]

        edge = g["edge"]
        img = bg * (1 - edge) + col * edge
        img = img + np.array(p.atmo, np.float32) * g["glow"] * 0.55
        return np.clip(img, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------
# widget
# --------------------------------------------------------------------------

_HEX: dict[int, str] = {}


def _hex(rgb: np.ndarray) -> str:
    key = (int(rgb[0]) << 16) | (int(rgb[1]) << 8) | int(rgb[2])
    s = _HEX.get(key)
    if s is None:
        s = f"#{key:06x}"
        _HEX[key] = s
    return s


def _overlay(row: list[list[str]], text: str, col: int, fg: str, bg: str) -> None:
    for i, ch in enumerate(text):
        j = col + i
        if 0 <= j < len(row):
            row[j] = [ch, fg, bg]


def image_to_text(img: np.ndarray, caption: str | None = None, hud: list[str] | None = None) -> Text:
    """Pack an RGB image (2 pixels per cell) into a truecolor half-block Text."""
    ph, w, _ = img.shape
    h = ph // 2
    top, bot = img[0::2], img[1::2]
    bg = theme.hexc(theme.P.bg)
    rows: list[list[list[str]]] = []
    for y in range(h):
        row: list[list[str]] = []
        for x in range(w):
            row.append(["▀", _hex(top[y, x]), _hex(bot[y, x])])
        rows.append(row)

    if hud:
        for i, label in enumerate(hud):
            if i < h - 1:
                _overlay(rows[i], "  " + label, 0, theme.hexc(theme.P.cyan), bg)
    if caption and h:
        _overlay(rows[-1], caption, 0, theme.hexc(theme.P.cyan), bg)

    out = Text(no_wrap=True, end="")
    for y, row in enumerate(rows):
        run = ""
        run_style = None
        for ch, fg, bcol in row:
            style = f"{fg} on {bcol}"
            if style != run_style:
                if run:
                    out.append(run, run_style)
                run, run_style = "", style
            run += ch
        if run:
            out.append(run, run_style)
        if y != len(rows) - 1:
            out.append("\n")
    return out


class Globe(Widget):
    """Auto-spinning Earth with a starfield."""

    DEFAULT_CSS = """
    Globe { width: 1fr; height: 1fr; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.engine = GlobeEngine()
        self.yaw = -1.9
        self.speed = 0.32
        self.paused = False
        self._last = time.perf_counter()

    def on_mount(self) -> None:
        self.set_interval(1 / 16, self._tick)

    def _tick(self) -> None:
        now = time.perf_counter()
        dt = min(now - self._last, 0.25)
        self._last = now
        if not self.paused:
            self.yaw = (self.yaw + self.speed * dt) % (2 * math.pi)
        self.refresh()

    def action_toggle_spin(self) -> None:
        self.paused = not self.paused

    def action_faster(self) -> None:
        self.speed = min(2.0, self.speed + 0.12)

    def action_slower(self) -> None:
        self.speed = max(0.0, self.speed - 0.12)

    def render(self) -> Text:
        w, h = self.size.width, self.size.height
        if w < 12 or h < 6:
            return Text("地球需要更大的窗口", style=theme.hexc(theme.P.dim))
        img = self.engine.render(w, h, self.yaw, time.time())
        state = "PAUSED" if self.paused else f"{self.speed:.2f} rad/s"
        lon = (math.degrees(self.yaw) + 180) % 360 - 180
        meridian = f"{abs(lon):5.1f}°{'E' if lon >= 0 else 'W'}"
        caption = f" EARTH · TILT {TILT:.1f}° · {state} "
        return image_to_text(img, caption, hud=["ORBITAL VIEW", f"MERIDIAN {meridian}"])
