"""Bake an equirectangular land mask from Natural Earth 110m land polygons.

Output: src/cyberdeck/data/landmask.npz with float16 array `land` of shape
(H, W), values 0..1 (0 = ocean, 1 = full land). Row 0 is 90N.

Run:  uv run python tools/build_landmask.py
"""

from __future__ import annotations

import json
import pathlib
import urllib.request

import numpy as np

H, W = 360, 720  # 0.5 degree grid
SUPERSAMPLE = 2  # rasterize at 2x then box-filter for soft coastlines
GEOJSON = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson"
OUT = pathlib.Path(__file__).resolve().parents[1] / "src" / "cyberdeck" / "data" / "landmask.npz"
CACHE = pathlib.Path(__file__).resolve().parent / "ne_110m_land.geojson"


def load_geojson() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    req = urllib.request.Request(GEOJSON, headers={"User-Agent": "cyberdeck-landmask"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    CACHE.write_text(raw, encoding="utf-8")
    return json.loads(raw)


def rings(geometry: dict) -> list[np.ndarray]:
    """Return all polygon rings as (n, 2) lon/lat arrays."""
    out: list[np.ndarray] = []
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    for poly in polys:
        for ring in poly:
            arr = np.asarray(ring, dtype=np.float64)
            if arr.shape[0] >= 3:
                out.append(arr[:, :2])
    return out


def scanline_fill(mask: np.ndarray, ring: np.ndarray, lats: np.ndarray, lons: np.ndarray) -> None:
    """Even-odd scanline fill of one ring into `mask` (XOR)."""
    x1, y1 = ring[:-1, 0], ring[:-1, 1]
    x2, y2 = ring[1:, 0], ring[1:, 1]
    for i, lat in enumerate(lats):
        # half-open vertical span test avoids double counting vertices
        cross = ((y1 <= lat) & (y2 > lat)) | ((y2 <= lat) & (y1 > lat))
        if not cross.any():
            continue
        t = (lat - y1[cross]) / (y2[cross] - y1[cross])
        xs = np.sort(x1[cross] + t * (x2[cross] - x1[cross]))
        for a, b in zip(xs[0::2], xs[1::2]):
            lo = np.searchsorted(lons, a, side="left")
            hi = np.searchsorted(lons, b, side="right")
            if hi > lo:
                mask[i, lo:hi] ^= True


def main() -> None:
    data = load_geojson()
    hh, ww = H * SUPERSAMPLE, W * SUPERSAMPLE
    mask = np.zeros((hh, ww), dtype=bool)
    lats = (90.0 - (np.arange(hh) + 0.5) * (180.0 / hh))
    lons = (-180.0 + (np.arange(ww) + 0.5) * (360.0 / ww))

    n = 0
    for feat in data["features"]:
        for ring in rings(feat["geometry"]):
            scanline_fill(mask, ring, lats, lons)
            n += 1

    land = mask.reshape(H, SUPERSAMPLE, W, SUPERSAMPLE).mean(axis=(1, 3)).astype(np.float16)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT, land=land)
    print(f"rings={n}  land fraction={(land > 0.5).mean():.3f}  -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
