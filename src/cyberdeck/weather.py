"""Weather: wttr.in client (no API key) + panel widget."""

from __future__ import annotations

import contextlib
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime

from rich.text import Text
from textual import work
from textual.widget import Widget

from . import storage, theme

FRESH_FOR = 15 * 60

# WWO weather codes -> (Chinese, palette key)
CODE_ZH: dict[int, tuple[str, str]] = {
    113: ("晴", "amber"),
    116: ("多云", "cyan"),
    119: ("阴", "dim"),
    122: ("阴天", "dim"),
    143: ("薄雾", "dim"),
    149: ("烟霾", "dim"),
    176: ("零星阵雨", "blue"),
    179: ("零星阵雪", "ice"),
    182: ("雨夹雪", "ice"),
    185: ("冻毛毛雨", "blue"),
    200: ("雷阵雨", "magenta"),
    227: ("风吹雪", "ice"),
    230: ("暴风雪", "ice"),
    248: ("雾", "dim"),
    260: ("冻雾", "dim"),
    263: ("小毛毛雨", "blue"),
    266: ("毛毛雨", "blue"),
    281: ("冻毛毛雨", "blue"),
    284: ("强冻毛毛雨", "blue"),
    293: ("小雨", "blue"),
    296: ("小雨", "blue"),
    299: ("中雨", "blue"),
    302: ("中雨", "blue"),
    305: ("大雨", "blue"),
    308: ("大雨", "blue"),
    311: ("小冻雨", "blue"),
    314: ("冻雨", "blue"),
    317: ("小冻雨", "blue"),
    320: ("冻雨", "blue"),
    323: ("小雪", "ice"),
    326: ("小雪", "ice"),
    329: ("中雪", "ice"),
    332: ("中雪", "ice"),
    335: ("大雪", "ice"),
    338: ("大雪", "ice"),
    350: ("冰粒", "ice"),
    353: ("小阵雨", "blue"),
    356: ("阵雨", "blue"),
    359: ("暴雨", "magenta"),
    362: ("小阵雪", "ice"),
    365: ("阵雪", "ice"),
    368: ("小阵雪", "ice"),
    371: ("阵雪", "ice"),
    374: ("小冰粒", "ice"),
    377: ("冰粒", "ice"),
    386: ("雷阵雨", "magenta"),
    389: ("雷暴雨", "magenta"),
    392: ("雷阵雪", "ice"),
    395: ("雷暴雪", "ice"),
}

WIND_ZH = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]


def describe(code: int) -> tuple[str, str]:
    return CODE_ZH.get(code, ("未知", "dim"))


def wind_dir(deg: float) -> str:
    return WIND_ZH[int((deg % 360) / 45 + 0.5) % 8]


@dataclass
class DayForecast:
    label: str
    code: int
    lo: int
    hi: int


@dataclass
class Weather:
    location: str
    temp: int
    feels: int
    code: int
    humidity: int
    wind_kmph: int
    wind_deg: float
    pressure: int
    visibility: int
    uv: int
    fetched: float
    days: list[DayForecast] = field(default_factory=list)
    sunrise: str = "--:--"
    sunset: str = "--:--"
    stale: bool = False


def _to24h(text: str) -> str:
    """"06:12 AM" -> "06:12"; "05:41 PM" -> "17:41"."""
    text = text.strip().upper()
    try:
        return datetime.strptime(text, "%I:%M %p").strftime("%H:%M")
    except ValueError:
        return text[:5] or "--:--"


def _parse(raw: dict, fetched: float, stale: bool = False) -> Weather:
    cur = raw["current_condition"][0]
    area = raw.get("nearest_area") or [{}]
    loc_parts = []
    for key in ("areaName", "region", "country"):
        try:
            v = area[0][key][0]["value"]
        except (KeyError, IndexError, TypeError):
            v = ""
        if v and v not in loc_parts:
            loc_parts.append(v)
    location = " · ".join(loc_parts[:2]) or "未知位置"

    days: list[DayForecast] = []
    for i, w in enumerate(raw.get("weather", [])[:3]):
        code = 113
        for h in w.get("hourly", []):
            if h.get("time") == "1200":
                code = int(h.get("weatherCode", 113))
                break
        days.append(DayForecast(("今天", "明天", "后天")[i], code,
                                int(w["mintempC"]), int(w["maxtempC"])))

    sunrise, sunset = "--:--", "--:--"
    try:
        astro = raw["weather"][0]["astronomy"][0]
        sunrise = _to24h(astro.get("sunrise", ""))
        sunset = _to24h(astro.get("sunset", ""))
    except (KeyError, IndexError):
        pass

    return Weather(
        location=location,
        temp=int(cur["temp_C"]),
        feels=int(cur["FeelsLikeC"]),
        code=int(cur["weatherCode"]),
        humidity=int(cur["humidity"]),
        wind_kmph=int(cur["windspeedKmph"]),
        wind_deg=float(cur.get("winddirDegree", 0)),
        pressure=int(cur["pressure"]),
        visibility=int(cur.get("visibility", 0)),
        uv=int(cur.get("uvIndex", 0)),
        fetched=fetched,
        days=days,
        sunrise=sunrise,
        sunset=sunset,
        stale=stale,
    )


def load_cache() -> Weather | None:
    blob = storage.load_json("weather.json")
    if not blob:
        return None
    try:
        return _parse(blob["raw"], blob["ts"], stale=True)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def fetch_weather(city: str | None = None) -> Weather | None:
    """Blocking fetch. Falls back to the on-disk cache when offline."""
    target = urllib.parse.quote(city) if city else ""
    url = f"https://wttr.in/{target}?format=j1&m"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"})
        with urllib.request.urlopen(req, timeout=9) as resp:
            raw = json.loads(resp.read().decode("utf-8", "replace"))
        ts = time.time()
        with contextlib.suppress(OSError):
            storage.save_json("weather.json", {"ts": ts, "city": city, "raw": raw})
        return _parse(raw, ts)
    except Exception:
        return load_cache()


# --------------------------------------------------------------------------


class WeatherPanel(Widget):
    DEFAULT_CSS = """
    WeatherPanel { width: 1fr; height: 16; }
    """

    def __init__(self, city: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.city = city
        self.data: Weather | None = None
        self.error: str | None = None

    def on_mount(self) -> None:
        self.data = load_cache()
        self.refresh_weather()
        self.set_interval(FRESH_FOR, self.refresh_weather)

    @work(thread=True, exclusive=True)
    def refresh_weather(self) -> None:
        data = fetch_weather(self.city)
        self.app.call_from_thread(self._apply, data)

    def _apply(self, data: Weather | None) -> None:
        self.error = None if data else "天气获取失败"
        if data:
            self.data = data
        self.refresh()
    # ------------------------------------------------------------------
    def _temp_block(self, temp: int) -> list[Text]:
        from . import bigfont

        p = theme.P
        glyphs = bigfont.rows(str(temp))
        grad = [p.amber, p.magenta]
        rows: list[Text] = []
        for r, row in enumerate(glyphs):
            color = theme.hexc(theme.ramp(grad, r / max(1, bigfont.HEIGHT - 1)))
            line = Text(no_wrap=True, end="")
            line.append(" ")
            for ch in row:
                line.append("█" if ch == "#" else " ", f"bold {color}")
            if r == 3:
                line.append(" °C", theme.hexc(p.dim))
            rows.append(line)
        return rows

    def build(self, w: int, h: int) -> Text:
        p = theme.P
        out = Text(no_wrap=True, end="")
        d = self.data

        if d is None:
            out.append(" 天气\n", f"bold {theme.hexc(p.cyan)}")
            out.append(" " + (self.error or "获取中…"), theme.hexc(p.dim))
            return out

        desc, tone = describe(d.code)
        accent = getattr(p, tone)

        if w < 26:  # narrow column: drop the pixel-font temperature
            out.append(" " + d.location[: max(4, w - 2)], f"bold {theme.hexc(p.cyan)}")
            out.append("\n")
            out.append(f" {d.temp}° ", theme.hexc(accent))
            out.append(desc, theme.hexc(p.text))
            out.append("\n")
            out.append(f" 体感{d.feels}° 湿{d.humidity}%", theme.hexc(p.dim))
            out.append("\n")
            for day in d.days[:2]:
                out.append(f" {day.label} {day.hi}/{day.lo}°", theme.hexc(p.dim))
                out.append("\n")
            return out

        out.append(" " + d.location[: max(4, w - 3)], f"bold {theme.hexc(p.cyan)}")
        if d.stale:
            out.append(" 缓存", theme.hexc(p.amber))
        out.append("\n")

        for row in self._temp_block(d.temp):
            out.append_text(row)
            out.append("\n")

        out.append(" ")
        out.append("● ", theme.hexc(accent))
        out.append(desc, f"bold {theme.hexc(p.text)}")
        out.append("   体感 ", theme.hexc(p.dim))
        out.append(f"{d.feels}°", theme.hexc(p.text))
        out.append("   湿度 ", theme.hexc(p.dim))
        out.append(f"{d.humidity}%", theme.hexc(p.text))
        out.append("\n")

        out.append(" 风 ", theme.hexc(p.dim))
        out.append(f"{wind_dir(d.wind_deg)} {d.wind_kmph}km/h", theme.hexc(p.text))
        out.append("  气压 ", theme.hexc(p.dim))
        out.append(f"{d.pressure}", theme.hexc(p.text))
        out.append("\n")

        out.append(" " + "─" * max(4, w - 3), theme.hexc(theme.mix(p.dim, p.panel, 0.45)))
        out.append("\n")

        for day in d.days:
            name, tone = describe(day.code)
            out.append(f" {day.label} ", theme.hexc(p.dim))
            out.append("● ", theme.hexc(getattr(p, tone)))
            out.append(f"{day.hi:2d}", theme.hexc(p.magenta))
            out.append("/", theme.hexc(p.dim))
            out.append(f"{day.lo:2d}°", theme.hexc(p.cyan))
            out.append(f"  {name}", theme.hexc(p.dim))
            out.append("\n")

        out.append(" " + "─" * max(4, w - 3), theme.hexc(theme.mix(p.dim, p.panel, 0.45)))
        out.append("\n")
        out.append(f" 日出 {d.sunrise}  日落 {d.sunset}", theme.hexc(p.dim))
        out.append("\n")
        age = int((time.time() - d.fetched) / 60)
        out.append(f" 更新 {datetime.fromtimestamp(d.fetched):%H:%M}", theme.hexc(theme.mix(p.dim, p.panel, 0.3)))
        if age > 60:
            out.append(f" ({age // 60}h 前)", theme.hexc(p.amber))
        return out

    def render(self) -> Text:
        w, h = self.content_size
        if w < 8 or h < 3:
            return Text("")
        return self.build(w, h)
