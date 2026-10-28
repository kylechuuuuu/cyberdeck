"""Core tests: font metrics, weather parsing, globe projection, panel layout."""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cyberdeck import bigfont, theme  # noqa: E402
from cyberdeck.clock import ClockPanel  # noqa: E402
from cyberdeck.globe import EarthTexture, GlobeEngine, image_to_text  # noqa: E402
from cyberdeck.system import Sampler, SystemPanel  # noqa: E402
from cyberdeck.weather import (  # noqa: E402
    Weather,
    WeatherPanel,
    _parse,
    _to24h,
    describe,
    wind_dir,
)

RAW = {
    "current_condition": [{
        "temp_C": "17", "FeelsLikeC": "9", "humidity": "44", "windspeedKmph": "36",
        "winddirDegree": "315", "weatherCode": "113", "pressure": "1008",
        "visibility": "10", "uvIndex": "0",
    }],
    "nearest_area": [{"areaName": [{"value": "Tokyo"}], "region": [{"value": "Tokyo"}],
                      "country": [{"value": "Japan"}]}],
    "weather": [
        {"date": "2026-10-27", "mintempC": "13", "maxtempC": "18",
         "hourly": [{"time": "1200", "weatherCode": "116"}],
         "astronomy": [{"sunrise": "05:59 AM", "sunset": "04:51 PM"}]},
        {"date": "2026-10-28", "mintempC": "12", "maxtempC": "15",
         "hourly": [{"time": "1200", "weatherCode": "119"}]},
        {"date": "2026-10-29", "mintempC": "13", "maxtempC": "20",
         "hourly": [{"time": "1200", "weatherCode": "296"}]},
    ],
}


def fake_weather() -> Weather:
    return _parse(RAW, time.time())


def test_bigfont_rectangular():
    art = bigfont.rows("23:47")
    assert len(art) == bigfont.HEIGHT
    assert len({len(r) for r in art}) == 1
    assert bigfont.width("23:47") == len(art[0])
    assert set("".join(art)) <= {".", "#", " "}


def test_weather_parse():
    w = fake_weather()
    assert w.temp == 17 and w.feels == 9
    assert w.location.startswith("Tokyo")
    assert [d.label for d in w.days] == ["今天", "明天", "后天"]
    assert w.days[2].lo == 13 and w.days[2].hi == 20
    assert (w.sunrise, w.sunset) == ("05:59", "16:51")
    assert describe(w.code)[0] == "晴"


def test_weather_helpers():
    assert describe(296)[0] == "小雨"
    assert describe(999)[0] == "未知"
    assert wind_dir(0) == "北"
    assert wind_dir(315) == "西北"
    assert wind_dir(180) == "南"
    assert _to24h("05:41 PM") == "17:41"
    assert _to24h("garbage") == "GARBA"


def test_gauge_and_sparkline():
    cells = theme.gauge(0.5, 20)
    assert len(cells) == 20
    assert all(len(ch) == 1 and style.startswith("#") for ch, style in cells)
    assert cells[0][0] == "█" and cells[-1][0] == "░"
    assert len(theme.sparkline([1, 2, 3], 10)) == 10
    assert len(theme.sparkline([], 7)) == 7
    assert theme.fmt_bytes(1536) == "1.5K"
    assert theme.fmt_uptime(0) == "00:00:00"


def marker_texture(lat: float, lon: float) -> EarthTexture:
    mask = np.zeros((360, 720), np.float32)
    r0 = int((90 - lat) / 180 * 360)
    c0 = int((lon + 180) / 360 * 720)
    mask[r0 - 4:r0 + 4, c0 - 4:c0 + 4] = 1
    return EarthTexture(mask)


@pytest.mark.parametrize("lat,lon", [(0, 0), (45, 0), (-40, 20)])
def test_globe_projection_places_markers(lat: float, lon: float):
    w, h = 120, 60
    radius = min(w / 2, h) * 0.88
    eng = GlobeEngine(marker_texture(lat, lon))
    img = eng.render(w, h, 0.0, 1.0, 0.0).astype(int)
    ref = GlobeEngine(EarthTexture(np.zeros((360, 720), np.float32))).render(w, h, 0.0, 1.0, 0.0).astype(int)
    land = np.abs(img - ref).sum(2) > 2
    ys, xs = np.nonzero(land)
    assert len(xs) > 0
    la, lo = math.radians(lat), math.radians(lon)
    assert abs(xs.mean() - (w / 2 + radius * math.cos(la) * math.sin(lo))) < 1.5
    assert abs(ys.mean() - (h - radius * math.sin(la))) < 1.5


def test_globe_frame_geometry():
    eng = GlobeEngine()
    w, h = 60, 20
    img = eng.render(w, h, 0.3, 2.0)
    assert img.shape == (2 * h, w, 3) and img.dtype == np.uint8
    assert img[h, w // 2].sum() > 60          # sphere centre is lit
    assert img[0, 0].sum() < 60               # corner is empty sky
    text = image_to_text(img, " EARTH ", hud=["HUD"])
    lines = text.plain.split("\n")
    assert len(lines) == h
    assert all(len(line) == w for line in lines)


def test_clock_panel_fits():
    panel = ClockPanel()
    text = panel.build(30, 16)
    lines = text.plain.split("\n")[:-1]
    assert 13 <= len(lines) <= 16
    assert all(theme_width(line) <= 31 for line in lines)


def theme_width(line: str) -> int:
    """Display width, counting East Asian wide characters as two cells."""
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in line)


def test_weather_panel_narrow_and_wide():
    panel = WeatherPanel()
    panel.data = fake_weather()
    wide = panel.build(38, 16).plain
    assert "Tokyo" in wide and "今天" in wide
    narrow = panel.build(20, 16).plain
    assert "17" in narrow


def test_system_panel_builds():
    sampler = Sampler()
    sampler.fast()
    time.sleep(0.05)
    sampler.fast()
    sampler.slow()
    panel = SystemPanel(sampler)
    text = panel.build(80, 42).plain
    assert "CPU" in text and "MEM" in text and "GPU" in text
    assert len(text.split("\n")) > 15
    # narrow layout must not raise
    panel.build(30, 20)


def test_palettes_are_complete():
    fields = ("cyan", "magenta", "purple", "blue", "green", "amber", "red", "dim", "text", "bg",
              "panel", "ocean_deep", "ocean_shallow", "land", "desert", "ice", "atmo")
    assert len(theme.PALETTES) == 8
    assert len({p.name for p in theme.PALETTES}) == 8
    for palette in theme.PALETTES:
        assert palette.label
        for field in fields:
            rgb = getattr(palette, field)
            assert len(rgb) == 3
            assert all(isinstance(c, int) and 0 <= c <= 255 for c in rgb)
    assert theme.palette_index("nord") == 4
    assert theme.palette_index("does-not-exist") == 0


def test_storage_roundtrip():
    from cyberdeck import storage

    assert storage.data_path("test-config.json") is not None
    assert storage.save_json("test-config.json", {"theme": "neon", "n": 1})
    assert storage.load_json("test-config.json") == {"theme": "neon", "n": 1}
    storage.data_path("test-config.json").unlink(missing_ok=True)


def test_process_table_sorting_and_layout():
    from cyberdeck.system import Proc

    sampler = Sampler()
    sampler.state.procs = [
        Proc("alpha", 10, 5.0, 100),
        Proc("bravo", 20, 1.0, 300),
        Proc("charlie", 30, 3.0, 200),
    ]
    panel = SystemPanel(sampler)
    panel.sort_key = "cpu"
    assert [p.name for p in panel._sorted_procs()] == ["alpha", "charlie", "bravo"]
    panel.sort_key = "mem"
    assert [p.name for p in panel._sorted_procs()] == ["bravo", "charlie", "alpha"]
    panel.sort_key = "pid"
    assert [p.pid for p in panel._sorted_procs()] == [10, 20, 30]
    panel.sort_key = "name"
    assert [p.name for p in panel._sorted_procs()] == ["alpha", "bravo", "charlie"]

    wide = panel.build(85, 42).plain
    assert "PROC" in wide and "│" in wide and "CPU" in wide and "GPU" in wide
    narrow = panel.build(63, 32).plain
    assert "PROC" in narrow and "MEM" in narrow
    assert all(theme_width(line) <= 86 for line in wide.split("\n"))


