"""Non-hardware info column: time progress, world clocks, lunar, air, hourly, custom.

Everything degrades gracefully: network sections show N/A instead of blocking the UI.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import re
import socket
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from rich.text import Text
from textual import work
from textual.widget import Widget

from . import storage, theme
from .weather import describe

try:  # optional: lunar calendar
    from lunar_python import Solar

    HAS_LUNAR = True
except Exception:  # pragma: no cover - optional dependency
    HAS_LUNAR = False

IS_WIN = False
try:
    import sys

    IS_WIN = sys.platform == "win32"
except Exception:  # pragma: no cover
    pass


# --------------------------------------------------------------------------
# pure helpers
# --------------------------------------------------------------------------

CN_WEEK = ["一", "二", "三", "四", "五", "六", "日"]
MOON_NAMES = ["新月", "娥眉月", "上弦月", "盈凸月", "满月", "亏凸月", "下弦月", "残月"]


def time_progress(now: datetime) -> list[tuple[str, float, str]]:
    """(label, fraction, remaining text) for day / week / month / year."""
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=now.weekday())
    month_start = day_start.replace(day=1)
    year_start = day_start.replace(month=1, day=1)
    next_year = year_start.replace(year=year_start.year + 1)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)

    def frac(start, end):
        return (now - start) / (end - start)

    def left(end):
        delta = end - now
        hours, rem = divmod(int(delta.total_seconds()), 3600)
        minutes = rem // 60
        if hours >= 24:
            return f"{hours // 24}d{hours % 24:02d}h"
        return f"{hours}h{minutes:02d}m"

    return [
        ("今日", frac(day_start, day_start + timedelta(days=1)), left(day_start + timedelta(days=1))),
        ("本周", frac(week_start, week_start + timedelta(days=7)), left(week_start + timedelta(days=7))),
        ("本月", frac(month_start, next_month), left(next_month)),
        ("今年", frac(year_start, next_year), left(next_year)),
    ]


def moon_phase(now: datetime) -> tuple[str, float]:
    """Approximate phase name and illuminated fraction."""
    known_new = datetime(2000, 1, 6, 18, 14)
    days = (now - known_new).total_seconds() / 86400.0
    phase = (days % 29.530588853) / 29.530588853
    illum = (1 - math.cos(2 * math.pi * phase)) / 2
    index = int(phase * 8 + 0.5) % 8
    return MOON_NAMES[index], illum


def lunar_info(now: datetime) -> dict[str, str]:
    out: dict[str, str] = {}
    if not HAS_LUNAR:
        return out
    try:
        lunar = Solar.fromDate(now).getLunar()
        out["date"] = f"{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}"
        out["year"] = f"{lunar.getYearInGanZhi()}年 · {lunar.getYearShengXiao()}"
        today_term = lunar.getJieQi()
        if today_term:
            out["term"] = today_term
        nxt = lunar.getNextJieQi(True)
        if nxt:
            solar = nxt.getSolar()
            out["next_term"] = f"{nxt.getName()} {solar.getMonth():02d}-{solar.getDay():02d}"
        festivals = lunar.getFestivals() + Solar.fromDate(now).getFestivals()
        if festivals:
            out["festival"] = " · ".join(festivals)
    except Exception:
        return {}
    return out


def parse_stocks(text: str) -> list[tuple[str, str, float]]:
    """Tencent quote payload -> [(name, price, change_pct)]."""
    quotes: list[tuple[str, str, float]] = []
    for line in text.splitlines():
        match = re.search(r'v_([\w.]+)="([^"]*)"', line)
        if not match:
            continue
        fields = match.group(2).split("~")
        if len(fields) < 5:
            continue
        name = fields[1] or match.group(1)
        price = fields[3]
        pct = 0.0
        if len(fields) > 32 and fields[32]:
            with contextlib.suppress(ValueError):
                pct = float(fields[32])
        elif fields[4]:
            with contextlib.suppress(ValueError):
                prev = float(fields[4])
                if prev:
                    pct = (float(price) - prev) / prev * 100
        quotes.append((name, price, pct))
    return quotes


def parse_symbols(text: str) -> list[str]:
    """Split 'sh600519, us.AAPL' (commas, Chinese commas, spaces) into symbols."""
    cleaned = text.replace("，", ",").replace("、", ",").replace(";", ",").replace(" ", ",")
    out: list[str] = []
    for part in cleaned.split(","):
        symbol = part.strip()
        if symbol and symbol not in out:
            out.append(symbol)
    return out[:12]


def todo_lines(text: str, limit: int = 8) -> list[tuple[str, bool]]:
    out: list[tuple[str, bool]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for bullet in ("- ", "* ", "• "):
            if line.startswith(bullet):
                line = line[len(bullet):].strip()
                break
        done = False
        if line[:3].lower() == "[x]":
            done, line = True, line[3:].strip()
        elif line[:3] == "[ ]":
            line = line[3:].strip()
        if line:
            out.append((line, done))
        if len(out) >= limit:
            break
    return out


def parse_hourly(raw: dict, now: datetime, count: int = 6) -> list[tuple[str, int, int]]:
    """Upcoming hours from a wttr.in j1 payload: (label, temp, weather code)."""
    out: list[tuple[str, int, int]] = []
    try:
        days = raw["weather"]
    except (KeyError, TypeError):
        return out
    for day_index, day in enumerate(days[:2]):
        for block in day.get("hourly", []):
            try:
                hour = int(str(block.get("time", "0")).zfill(4)[:-2])
            except ValueError:
                continue
            if day_index == 0 and hour < now.hour:
                continue
            out.append((f"{hour:02d}时", int(block.get("tempC", 0)), int(block.get("weatherCode", 113))))
            if len(out) >= count:
                return out
    return out


def _get_json(url: str, timeout: float = 8) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cyberdeck/0.2"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


def latency_once(host: str = "223.5.5.5", port: int = 53) -> float | None:
    """TCP handshake round-trip in ms (ICMP needs privileges on Windows)."""
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=1.2):
            return (time.perf_counter() - start) * 1000
    except OSError:
        return None


def aqi_level(aqi: float) -> tuple[str, str]:
    if aqi <= 50:
        return "优", "green"
    if aqi <= 100:
        return "良", "cyan"
    if aqi <= 150:
        return "轻度", "amber"
    if aqi <= 200:
        return "中度", "amber"
    if aqi <= 300:
        return "重度", "red"
    return "严重", "red"


def _location() -> tuple[float, float, str] | None:
    blob = storage.load_json("weather.json")
    try:
        area = blob["raw"]["nearest_area"][0]
        lat, lon = area["latitude"], area["longitude"]
        if isinstance(lat, list):
            lat = lat[0]["value"]
        if isinstance(lon, list):
            lon = lon[0]["value"]
        name = area.get("areaName", [{"value": ""}])[0].get("value", "")
        return float(lat), float(lon), str(name)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return None


def _coords_from_weather() -> tuple[float, float] | None:
    loc = _location()
    return (loc[0], loc[1]) if loc else None


def location_marker() -> tuple[float, float, str] | None:
    """(lat, lon, city name) for the globe marker."""
    return _location()


def _weather_raw() -> dict | None:
    blob = storage.load_json("weather.json")
    return blob.get("raw") if blob else None


# --------------------------------------------------------------------------
# remote fetchers (called from worker threads)
# --------------------------------------------------------------------------

@dataclass
class Quote:
    name: str
    price: str
    pct: float


@dataclass
class Air:
    aqi: float
    pm25: float


@dataclass
class Media:
    title: str
    artist: str
    playing: bool


def fetch_stocks(symbols: list[str]) -> list[Quote]:
    if not symbols:
        return []
    url = "https://qt.gtimg.cn/q=" + ",".join(symbols)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cyberdeck/0.2"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            raw = resp.read().decode("gbk", "replace")
    except Exception:
        return []
    return [Quote(name, price, pct) for name, price, pct in parse_stocks(raw)]


def fetch_air(lat: float, lon: float) -> Air | None:
    url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat:.3f}&longitude={lon:.3f}&current=pm2_5,us_aqi"
    )
    blob = _get_json(url)
    try:
        cur = blob["current"]
        return Air(float(cur["us_aqi"]), float(cur["pm2_5"]))
    except (KeyError, TypeError, ValueError):
        return None


def fetch_media() -> Media | None:
    if not IS_WIN:
        return None
    try:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager,
        )
    except Exception:
        return None

    async def read() -> Media | None:
        manager = await Manager.request_async()
        session = manager.get_current_session()
        if session is None:
            return None
        props = await session.try_get_media_properties_async()
        status = session.get_playback_info().playback_status
        return Media(props.title or "", props.artist or "", int(status) == 4)

    try:
        return asyncio.run(read())
    except Exception:
        return None


# --------------------------------------------------------------------------
# widget
# --------------------------------------------------------------------------

@dataclass
class InfoState:
    quotes: list[Quote] = field(default_factory=list)
    air: Air | None = None
    media: Media | None = None
    latency: list[float] = field(default_factory=list)
    loss: int = 0
    todo: list[tuple[str, bool]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class InfoPanel(Widget):
    DEFAULT_CSS = """
    InfoPanel { width: 46; height: 1fr; padding: 0 1; }
    """

    def __init__(self, config: dict | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        cfg = (config or {}).get("info", {}) if isinstance(config, dict) else {}
        self.cfg = cfg
        self.modules: list[str] = list(cfg.get("modules") or ["stocks", "media", "todo", "notes"])
        self.stocks: list[str] = list(cfg.get("stocks") or ["sh000001", "sz399001", "sh600519"])
        self.zones: list[str] = list(cfg.get("zones") or [
            "UTC", "America/New_York", "Europe/London", "Asia/Tokyo", "Asia/Singapore", "Australia/Sydney",
        ])
        todo_path = cfg.get("todo_file")
        self.todo_path = Path(todo_path).expanduser() if todo_path else None
        notes_path = cfg.get("notes_file")
        self.notes_path = Path(notes_path).expanduser() if notes_path else None
        self.state = InfoState()
        self._last_slow = 0.0
        self._last_air = 0.0
        self._hourly: list[tuple[str, int, int]] = []
        self._todo_mtime = 0.0
        self._notes_mtime = 0.0

    def on_mount(self) -> None:
        self._load_todo()
        self.set_interval(2.0, self._tick)
        self.set_interval(5.0, self._poll_latency)
        self.set_interval(60.0, self._poll_stocks)
        self.set_interval(10.0, self._poll_media)
        self.set_interval(600.0, self._poll_air)
        self.set_timer(0.5, self._poll_stocks)
        self.set_timer(0.6, self._poll_media)
        self.set_timer(0.7, self._poll_air)
        self.set_timer(0.8, self._poll_latency)

    # -- data ------------------------------------------------------------
    def _tick(self) -> None:
        raw = _weather_raw()
        if raw:
            self._hourly = parse_hourly(raw, datetime.now(), 8)
        if self.state.air is None and time.monotonic() - self._last_air > 30:
            self._last_air = time.monotonic()
            self._poll_air()
        self._load_todo()
        self.refresh()

    def _todo_file(self) -> Path | None:
        if self.todo_path:
            return self.todo_path
        return storage.data_path("todo.txt")

    def _load_todo(self) -> None:
        path = self._todo_file()
        mtime = 0.0
        if path is not None:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
        if mtime != self._todo_mtime:
            self._todo_mtime = mtime
            if path is None or not path.exists():
                self.state.todo = []
            else:
                try:
                    self.state.todo = todo_lines(path.read_text(encoding="utf-8", errors="replace"), 14)
                except OSError:
                    self.state.todo = []

        notes = self._notes_file()
        ntime = 0.0
        if notes is not None:
            try:
                ntime = notes.stat().st_mtime
            except OSError:
                ntime = 0.0
        if ntime != self._notes_mtime:
            self._notes_mtime = ntime
            if notes is None or not notes.exists():
                self.state.notes = []
            else:
                try:
                    text = notes.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    text = ""
                self.state.notes = [line.strip() for line in text.splitlines() if line.strip()][:12]

    def _notes_file(self) -> Path | None:
        if self.notes_path:
            return self.notes_path
        return storage.data_path("notes.txt")

    @work(thread=True, exclusive=True)
    def _poll_latency(self) -> None:
        if not self.app.screen.has_class("info"):
            return
        ms = latency_once()
        self.app.call_from_thread(self._push_latency, ms)

    def _push_latency(self, ms: float | None) -> None:
        if ms is None:
            self.state.loss = min(99, self.state.loss + 1)
        else:
            self.state.latency = (self.state.latency + [ms])[-40:]
            self.state.loss = max(0, self.state.loss - 1)
        self.refresh()

    @work(thread=True, exclusive=True)
    def _poll_stocks(self) -> None:
        if not self.app.screen.has_class("info"):
            return
        quotes = fetch_stocks(self.stocks)
        self.app.call_from_thread(self._push_stocks, quotes)

    def _push_stocks(self, quotes: list[Quote]) -> None:
        if quotes:
            self.state.quotes = quotes
        self.refresh()

    @work(thread=True, exclusive=True)
    def _poll_media(self) -> None:
        if not self.app.screen.has_class("info"):
            return
        media = fetch_media()
        self.app.call_from_thread(self._push_media, media)

    def _push_media(self, media: Media | None) -> None:
        self.state.media = media
        self.refresh()

    @work(thread=True, exclusive=True)
    def _poll_air(self) -> None:
        if not self.app.screen.has_class("info"):
            return
        coords = _coords_from_weather()
        air = fetch_air(*coords) if coords else None
        self.app.call_from_thread(self._push_air, air)

    def _push_air(self, air: Air | None) -> None:
        if air:
            self.state.air = air
        self.refresh()
    # -- rendering -------------------------------------------------------
    def render(self) -> Text:
        w, h = self.content_size
        return self.build(w, h)

    def build(self, w: int, h: int) -> Text:
        if w < 24 or h < 8:
            return Text("")
        out = Text(no_wrap=True, end="")
        blocks: list[Text] = []
        blocks += self._sec_time(w)
        blocks.append(Text(""))
        blocks += self._sec_lunar(w)
        blocks.append(Text(""))
        blocks += self._sec_weather(w)
        blocks.append(Text(""))
        blocks += self._sec_network(w)
        blocks.append(Text(""))
        blocks += self._sec_custom(w)
        notes = self._sec_notes(w)
        if notes:
            blocks.append(Text(""))
            blocks += notes

        for i, line in enumerate(blocks):
            if i >= h:
                break
            out.append_text(line)
            out.append("\n")
        return out

    def _style(self) -> dict[str, str]:
        p = theme.P
        return {
            "dim": theme.hexc(p.dim), "text": theme.hexc(p.text), "cyan": theme.hexc(p.cyan),
            "mag": theme.hexc(p.magenta), "pur": theme.hexc(p.purple), "amb": theme.hexc(p.amber),
            "green": theme.hexc(p.green), "red": theme.hexc(p.red),
        }

    def _header(self, title: str, extra: str = "") -> Text:
        c = self._style()
        line = Text(no_wrap=True, end="")
        line.append("◤ ", c["cyan"])
        line.append(title, f"bold {c['cyan']}")
        if extra:
            line.append("  " + extra, c["dim"])
        return line

    def _sec_time(self, w: int) -> list[Text]:
        c = self._style()
        lines = [self._header("TIME")]
        for label, frac, remaining in time_progress(datetime.now()):
            row = Text(no_wrap=True, end="")
            row.append(f" {label} ", c["dim"])
            for ch, color in theme.gauge(frac, max(4, w - 20), [theme.P.cyan, theme.P.purple, theme.P.magenta]):
                row.append(ch, color)
            row.append(f" {frac * 100:3.0f}%", c["text"])
            row.append(f" 剩{remaining}", c["dim"])
            lines.append(row)
        for pair in (self.zones[:2], self.zones[2:4], self.zones[4:6]):
            if not pair:
                continue
            row = Text(no_wrap=True, end="")
            for zone in pair:
                try:
                    local = datetime.now(ZoneInfo(zone))
                    label = zone.split("/")[-1].replace("_", " ")[:8]
                    row.append(f" {label:<8}", c["dim"])
                    row.append(local.strftime("%H:%M"), c["cyan"])
                except Exception:
                    row.append(f" {zone[:8]:<8}", c["dim"])
                    row.append("--:--", c["dim"])
            lines.append(row)
        return lines

    def _sec_lunar(self, w: int) -> list[Text]:
        c = self._style()
        info = lunar_info(datetime.now())
        lines = [self._header("LUNAR")]
        if not info:
            lines.append(Text(" 农历库未安装", style=c["dim"]))
            return lines
        row = Text(no_wrap=True, end="")
        row.append(" 农历 ", c["dim"])
        row.append(info.get("date", "--"), c["text"])
        if info.get("year"):
            row.append("  " + info["year"], c["dim"])
        lines.append(row)
        if info.get("festival"):
            fest = Text(no_wrap=True, end="")
            fest.append(" 节日 ", c["dim"])
            fest.append(info["festival"], f"bold {c['mag']}")
            lines.append(fest)
        row = Text(no_wrap=True, end="")
        row.append(" 节气 ", c["dim"])
        row.append(info.get("term") or info.get("next_term", "--"), c["text"])
        name, illum = moon_phase(datetime.now())
        row.append(f"   月相 {name} {illum * 100:.0f}%", c["dim"])
        lines.append(row)
        return lines

    def _sec_weather(self, w: int) -> list[Text]:
        c = self._style()
        lines = [self._header("逐时")]
        if not self._hourly:
            lines.append(Text(" 等待天气数据…", style=c["dim"]))
            return lines
        row = Text(no_wrap=True, end="")
        for i, (label, temp, code) in enumerate(self._hourly):
            name, tone = describe(code)
            row.append(f" {label} ", c["dim"])
            row.append(f"{temp:3d}°", c["text"])
            row.append(f" {name}", theme.hexc(getattr(theme.P, tone)))
            if i % 2 == 1:
                lines.append(row)
                row = Text(no_wrap=True, end="")
        if row.plain.strip():
            lines.append(row)
        if len(self._hourly) > 2:
            temps = [temp for _, temp, _ in self._hourly]
            trend = Text(no_wrap=True, end="")
            trend.append(" 温度 ", c["dim"])
            trend.append(theme.sparkline(temps, max(4, min(len(temps), w - 12))), c["pur"])
            trend.append(f" {min(temps):.0f}~{max(temps):.0f}°", c["dim"])
            lines.append(trend)
        return lines

    def _sec_network(self, w: int) -> list[Text]:
        c = self._style()
        lines = [self._header("NET")]
        row = Text(no_wrap=True, end="")
        if self.state.latency:
            last = self.state.latency[-1]
            avg = sum(self.state.latency[-10:]) / len(self.state.latency[-10:])
            row.append(" 延迟 ", c["dim"])
            row.append(f"{last:4.0f}ms", c["text"])
            row.append(f" 均 {avg:3.0f}ms", c["dim"])
        else:
            row.append(" 延迟 --", c["dim"])
        row.append(f" 丢包 {self.state.loss}%", c["dim"])
        lines.append(row)
        if self.state.latency:
            spark = Text(no_wrap=True, end="")
            spark.append(" " + theme.sparkline(self.state.latency, max(6, w - 4)), c["pur"])
            lines.append(spark)
        air = self.state.air
        row = Text(no_wrap=True, end="")
        if air:
            label, tone = aqi_level(air.aqi)
            row.append(" AQI ", c["dim"])
            row.append(f"{air.aqi:3.0f} ", c["text"])
            row.append(label, theme.hexc(getattr(theme.P, tone)))
            row.append(f"  PM2.5 {air.pm25:.0f}", c["dim"])
        else:
            row.append(" AQI --", c["dim"])
        lines.append(row)
        return lines

    def _sec_custom(self, w: int) -> list[Text]:
        c = self._style()
        lines = [self._header("自选", " ".join(m.upper() for m in self.modules))]
        if "stocks" in self.modules:
            if self.state.quotes:
                for q in self.state.quotes[:8]:
                    row = Text(no_wrap=True, end="")
                    row.append(f" {q.name[:8]:<8}", c["text"])
                    row.append(f"{q.price:>10}", c["text"])
                    tone = c["red"] if q.pct < 0 else c["green"]
                    arrow = "▼" if q.pct < 0 else "▲"
                    row.append(f" {arrow}{abs(q.pct):.2f}%", tone)
                    lines.append(row)
            else:
                lines.append(Text(" 行情 --", style=c["dim"]))
        if "media" in self.modules:
            media = self.state.media
            row = Text(no_wrap=True, end="")
            if media and media.title:
                row.append(" ♪ ", c["mag"] if media.playing else c["dim"])
                row.append(media.title[: max(4, w - 12)], c["text"])
                if media.artist:
                    row.append(" — " + media.artist[:10], c["dim"])
            else:
                row.append(" ♪ 未在播放", c["dim"])
            lines.append(row)
        if "todo" in self.modules:
            todo = self.state.todo
            path = self._todo_file()
            if todo:
                for text, done in todo[:14]:
                    row = Text(no_wrap=True, end="")
                    row.append(" ○ " if not done else " ● ", c["green"] if done else c["dim"])
                    row.append(
                        text[: max(4, w - 4)],
                        theme.hexc(theme.mix(theme.P.dim, theme.P.text, 0.3)) if done else theme.hexc(theme.P.text),
                    )
                    lines.append(row)
            elif path:
                hint = Text(no_wrap=True, end="")
                hint.append(" 待办 ", c["dim"])
                hint.append(path.name, theme.hexc(theme.mix(theme.P.dim, theme.P.panel, 0.1)))
                hint.append(" 空", c["dim"])
                lines.append(hint)
        return lines

    def _sec_notes(self, w: int) -> list[Text]:
        if "notes" not in self.modules or not self.state.notes:
            return []
        c = self._style()
        lines = [self._header("笔记")]
        for text in self.state.notes[:10]:
            row = Text(no_wrap=True, end="")
            row.append(" · ", c["dim"])
            row.append(text[: max(4, w - 4)], c["text"])
            lines.append(row)
        return lines











