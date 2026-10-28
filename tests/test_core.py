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
from cyberdeck.extras import (  # noqa: E402
    Air,
    InfoPanel,
    Quote,
    moon_phase,
    parse_hourly,
    parse_stocks,
    time_progress,
    todo_lines,
)
from cyberdeck.globe import EarthTexture, GlobeEngine, image_to_text  # noqa: E402
from cyberdeck.system import Proc, Sampler, SystemPanel  # noqa: E402
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


def test_time_progress_and_moon():
    from datetime import datetime

    items = time_progress(datetime(2026, 10, 28, 12, 0))
    assert [label for label, _, _ in items] == ["今日", "本周", "本月", "今年"]
    assert abs(items[0][1] - 0.5) < 0.01
    assert all(0 <= frac <= 1 for _, frac, _ in items)
    name, illum = moon_phase(datetime(2026, 10, 28, 12, 0))
    assert name in ("新月", "娥眉月", "上弦月", "盈凸月", "满月", "亏凸月", "下弦月", "残月")
    assert 0 <= illum <= 1


def test_parse_stocks_and_todo():
    fields = ["0"] * 50
    fields[1] = "贵州茅台"
    fields[3] = "1340.00"
    fields[4] = "1350.00"
    fields[32] = "-0.74"
    text = 'v_sh600519="' + "~".join(fields) + '";'
    quotes = parse_stocks(text)
    assert quotes and quotes[0][0] == "贵州茅台"
    assert quotes[0][1] == "1340.00"
    assert abs(quotes[0][2] + 0.74) < 0.01

    todo = todo_lines("# header\n- [ ] 写论文\n[x] 跑实验\n- 买咖啡\n")
    assert todo == [("写论文", False), ("跑实验", True), ("买咖啡", False)]


def test_parse_hourly_skips_past_hours():
    from datetime import datetime

    raw = {"weather": [{"hourly": [
        {"time": "0", "tempC": "10", "weatherCode": "113"},
        {"time": "1200", "tempC": "20", "weatherCode": "116"},
        {"time": "1800", "tempC": "15", "weatherCode": "119"},
    ]}]}
    out = parse_hourly(raw, datetime(2026, 10, 28, 13, 0), 4)
    assert [label for label, _, _ in out] == ["18时"]
    assert out[0][1] == 15


def test_info_panel_builds():
    panel = InfoPanel({"info": {"modules": ["stocks", "media", "todo"], "stocks": [], "zones": ["UTC"]}})
    panel.state.latency = [12.0, 30.0, 18.0]
    panel.state.air = Air(79, 8)
    panel.state.quotes = [Quote("上证指数", "3658.38", 0.28), Quote("贵州茅台", "1341.30", -1.08)]
    panel.state.todo = [("写论文", False), ("跑实验", True)]
    panel._hourly = [("12时", 18, 113), ("15时", 17, 116)]
    text = panel.build(43, 53).plain
    assert "TIME" in text and "LUNAR" in text and "NET" in text
    assert "上证指数" in text and "18ms" in text
    assert "AQI" in text and "写论文" in text
    # a narrow column must not raise
    panel.build(24, 10)


def test_globe_marker():
    import math

    eng = GlobeEngine()
    lat, lon = 35.69, 139.69
    yaw = -math.radians(lon)
    img = eng.render(60, 24, yaw, 1.0, marker=(lat, lon)).astype(int)
    assert eng.marker_pos is not None
    x, y = int(eng.marker_pos[0]), int(eng.marker_pos[1])
    plain = eng.render(60, 24, yaw, 1.0).astype(int)
    assert img[y, x].sum() > plain[y, x].sum() + 150  # marker brightens the pixel
    # the same point is on the far side of the globe a half-turn later
    eng.render(60, 24, math.radians(180 - lon), 1.0, marker=(lat, lon))
    assert eng.marker_pos is None


def test_parse_symbols():
    from cyberdeck.extras import parse_symbols

    assert parse_symbols("sh600519, us.AAPL") == ["sh600519", "usAAPL"]
    assert parse_symbols("sh600519，sz399001、us.NVDA") == ["sh600519", "sz399001", "usNVDA"]
    assert parse_symbols("  sh600519  sh600519 ") == ["sh600519"]
    assert parse_symbols("us.aapl, hk.700") == ["usAAPL", "hk700"]
    assert parse_symbols("") == []


def test_media_section():
    from cyberdeck.extras import Media

    panel = InfoPanel({"info": {"modules": ["media"], "zones": ["UTC"]}})
    panel.state.media = Media("Forever Yours", "J. Brown", True, 12.0, 227.0)
    text = panel.build(43, 30).plain
    assert "音乐" in text and "Forever Yours" in text and "J. Brown" in text
    assert "0:12/3:47" in text
    # stopped playback still renders without progress
    panel.state.media = Media("", "", False)
    assert "未在播放" in panel.build(43, 30).plain


def test_long_music_titles_stay_inside_column():
    from rich.cells import cell_len

    from cyberdeck.extras import Media, trunc_cells, window_cells

    assert trunc_cells("就算我错漏百出", 6) == "就算我"
    assert cell_len(window_cells("abc就算def", 2, 6)) <= 6

    panel = InfoPanel({"info": {"modules": ["media"], "zones": ["UTC"]}})
    long_ascii = Media("A Very Long Song Title That Definitely Overflows The Column", "Artist", True, 10, 200)
    long_cjk = Media("就算我错漏百出就算我错漏百出就算我错漏百出", "歌手名字也很长很长", True, 10, 200)
    for media in (long_ascii, long_cjk):
        panel.state.media = media
        for line in panel._sec_media(43):
            assert cell_len(line.plain) <= 43, line.plain


def test_heat_and_bars():
    assert theme.heat(0.0) == theme.heat(0.0)
    assert theme.heat(1.0) != theme.heat(0.0)
    filled, empty, color = theme.bar(0.5, 10)
    assert len(filled) == 5 and len(empty) == 5
    rows, cols = theme.graph_rows([1, 2, 3, 4], 6, 2)
    assert len(rows) == 2 and all(len(r) == 6 for r in rows)
    assert len(cols) == 6



