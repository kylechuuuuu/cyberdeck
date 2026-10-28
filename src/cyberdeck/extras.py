"""Non-hardware info column: time progress, world clocks, lunar, air, hourly, custom.

Everything degrades gracefully: network sections show N/A instead of blocking the UI.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import re
import shutil
import socket
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from rich.cells import cell_len
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
IS_MAC = False
IS_LINUX = False
try:
    import sys

    IS_WIN = sys.platform == "win32"
    IS_MAC = sys.platform == "darwin"
    IS_LINUX = sys.platform.startswith("linux")
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
    """Split 'sh600519, us.AAPL' into Tencent-style symbols (us./hk. dots removed)."""
    cleaned = text.replace("，", ",").replace("、", ",").replace(";", ",").replace(" ", ",")
    out: list[str] = []
    for part in cleaned.split(","):
        symbol = part.strip()
        if not symbol:
            continue
        prefix, dot, ticker = symbol.partition(".")
        if dot and prefix.lower() in ("us", "hk"):
            symbol = prefix.lower() + ticker.upper()
        if symbol not in out:
            out.append(symbol)
    return out[:12]


def trunc_cells(text: str, limit: int) -> str:
    """Cut a string without splitting a wide (CJK) glyph."""
    from rich.cells import cell_len

    out: list[str] = []
    used = 0
    for ch in text:
        width = cell_len(ch)
        if used + width > limit:
            break
        out.append(ch)
        used += width
    return "".join(out)


def window_cells(text: str, start: int, width: int) -> str:
    """Substring covering `width` cells starting at cell offset `start`."""
    from rich.cells import cell_len

    out: list[str] = []
    pos = used = 0
    for ch in text:
        w = cell_len(ch)
        if pos + w <= start:
            pos += w
            continue
        if pos >= start and used + w <= width:
            out.append(ch)
            used += w
        pos += w
    return "".join(out)


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


def _configured_location() -> tuple[float, float, str] | None:
    """Exact pin from config.json: {"location": {"lat": .., "lon": .., "name": ".."}}."""
    cfg = (storage.load_json("config.json") or {}).get("location") or {}
    if not isinstance(cfg, dict):
        return None
    try:
        lat, lon = float(cfg["lat"]), float(cfg["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0):
        return None
    name = str(cfg.get("name") or "").strip()
    return lat, ((lon + 180.0) % 360.0) - 180.0, name


def _location() -> tuple[float, float, str] | None:
    """(lat, lon, name): config wins, else the nearest weather station from wttr.in.

    wttr.in reports the closest *station*, which can sit tens of kilometres away,
    so a fixed dashboard should pin itself with explicit coordinates.
    """
    pinned = _configured_location()
    blob = storage.load_json("weather.json")
    try:
        area = blob["raw"]["nearest_area"][0]
        lat, lon = area["latitude"], area["longitude"]
        if isinstance(lat, list):
            lat = lat[0]["value"]
        if isinstance(lon, list):
            lon = lon[0]["value"]
        name = area.get("areaName", [{"value": ""}])[0].get("value", "")
        # prefer the city the user asked wttr.in for over the nearest sub-district
        city = str(blob.get("city") or name or "")
        if pinned:
            return pinned[0], pinned[1], pinned[2] or name or "HERE"
        return float(lat), float(lon), city
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        if pinned:
            return pinned[0], pinned[1], pinned[2] or "HERE"
        return None


def _coords_from_weather() -> tuple[float, float] | None:
    loc = _location()
    return (loc[0], loc[1]) if loc else None


def location_marker() -> tuple[float, float, str] | None:
    """(lat, lon, city name) for the globe marker."""
    return _location()


_WEATHER_RAW: tuple[float, dict | None] = (-1.0, None)


def _weather_raw() -> dict | None:
    """Cached wttr.in payload; re-read only when weather.json changes."""
    global _WEATHER_RAW
    path = storage.data_path("weather.json")
    if path is None:
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if mtime != _WEATHER_RAW[0]:
        blob = storage.load_json("weather.json")
        _WEATHER_RAW = (mtime, blob.get("raw") if blob else None)
    return _WEATHER_RAW[1]


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
    position: float = 0.0
    duration: float = 0.0
    album: str = ""
    cover: bytes | None = None
    stamp: float = 0.0


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


def parse_mac_media(text: str, duration_ms: bool = False) -> Media | None:
    """Parse `osascript` output: title, artist, album, position, duration, state."""
    lines = [line.strip() for line in text.strip().splitlines()]
    if len(lines) < 6 or not lines[0]:
        return None
    title, artist, album, pos, dur, state = lines[:6]
    try:
        position = max(0.0, float(pos.replace(",", ".")))
        duration = max(0.0, float(dur.replace(",", ".")))
    except ValueError:
        return None
    if duration_ms and duration > 1000:  # Spotify reports milliseconds
        duration /= 1000.0
    if duration > 0:
        position = min(position, duration)
    return Media(
        title=title,
        artist=artist,
        playing=state.lower() == "playing",
        position=position,
        duration=duration,
        album=album,
        cover=None,
        stamp=time.monotonic(),
    )


_MAC_COVERS: dict[str, bytes] = {}

_MAC_MUSIC_SCRIPT = """
if application "Music" is running then
  tell application "Music"
    if player state is not stopped then
      set tr to current track
      return (name of tr) & linefeed & (artist of tr) & linefeed & (album of tr) & linefeed & (player position as string) & linefeed & (duration of tr as string) & linefeed & (player state as string)
    end if
  end tell
end if
return ""
"""

_MAC_SPOTIFY_SCRIPT = """
if application "Spotify" is running then
  tell application "Spotify"
    if player state is not stopped then
      set tr to current track
      set art to ""
      try
        set art to artwork url of tr
      end try
      return (name of tr) & linefeed & (artist of tr) & linefeed & (album of tr) & linefeed & (player position as string) & linefeed & (duration of tr as string) & linefeed & (player state as string) & linefeed & art
    end if
  end tell
end if
return ""
"""


def _download_cover(url: str, limit: int = 800_000) -> bytes | None:
    if not url.lower().startswith(("http://", "https://")):
        return None
    if url in _MAC_COVERS:
        return _MAC_COVERS[url]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cyberdeck/0.2"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = resp.read(limit + 1)
    except Exception:
        return None
    if not data or len(data) > limit:
        return None
    if len(_MAC_COVERS) > 8:
        _MAC_COVERS.clear()
    _MAC_COVERS[url] = data
    return data


def fetch_mac_media() -> Media | None:
    """Now playing from Music.app / Spotify via AppleScript (no extra tools)."""
    exe = shutil.which("osascript")
    if not exe:
        return None
    players = [
        ("Spotify", ("/Applications/Spotify.app", str(Path.home() / "Applications" / "Spotify.app")), True, True),
        ("Music", ("/System/Applications/Music.app", "/Applications/Music.app"), False, False),
    ]
    found: list[Media] = []
    for _name, paths, duration_ms, has_art in players:
        if not any(Path(path).exists() for path in paths):
            continue
        script = _MAC_SPOTIFY_SCRIPT if has_art else _MAC_MUSIC_SCRIPT
        try:
            proc = subprocess.run(
                [exe, "-e", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=4,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0 and has_art:  # older Spotify dictionaries may not have `artwork url`
            fallback = _MAC_MUSIC_SCRIPT.replace('"Music"', '"Spotify"')
            try:
                proc = subprocess.run(
                    [exe, "-e", fallback],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=4,
                    check=False,
                )
                has_art = False
            except (OSError, subprocess.SubprocessError):
                continue
        if proc.returncode != 0 or not proc.stdout.strip():
            continue
        media = parse_mac_media(proc.stdout, duration_ms)
        if media is None:
            continue
        if has_art:
            lines = proc.stdout.strip().splitlines()
            if len(lines) > 6:
                media.cover = _download_cover(lines[6].strip())
        found.append(media)
    if not found:
        return None
    for media in found:
        if media.playing:
            return media
    return found[0]


def parse_linux_media(text: str) -> Media | None:
    """Parse `playerctl` output; position/length are in microseconds."""
    lines = [line.strip() for line in text.strip().splitlines()]
    if len(lines) < 6 or not lines[0]:
        return None
    title, artist, album, pos, dur, state = lines[:6]

    def seconds(raw: str) -> float:
        try:
            return max(0.0, float(raw)) / 1_000_000.0
        except ValueError:
            return 0.0  # some players report an empty length

    position = seconds(pos)
    duration = seconds(dur)
    if duration > 0:
        position = min(position, duration)
    return Media(
        title=title,
        artist=artist,
        playing=state.lower() == "playing",
        position=position,
        duration=duration,
        album=album,
        cover=None,
        stamp=time.monotonic(),
    )


def fetch_linux_media() -> Media | None:
    """Now playing via `playerctl` when installed; silently skip otherwise."""
    exe = shutil.which("playerctl")
    if not exe:
        return None
    fmt = "{{title}}\n{{artist}}\n{{album}}\n{{position}}\n{{mpris:length}}\n{{status}}"
    try:
        proc = subprocess.run(
            [exe, "metadata", "--format", fmt],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return parse_linux_media(proc.stdout)


def fetch_media() -> Media | None:
    if IS_MAC:
        return fetch_mac_media()
    if IS_LINUX:
        return fetch_linux_media()
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
        timeline = session.get_timeline_properties()
        position = getattr(timeline, "position", None)
        end = getattr(timeline, "end_time", None)
        cover: bytes | None = None
        try:
            ref = props.thumbnail
            if ref is not None:
                stream = await ref.open_read_async()
                size = int(stream.size)
                if 0 < size <= 800_000:
                    from winrt.windows.storage.streams import DataReader

                    reader = DataReader(stream)
                    await reader.load_async(size)
                    buffer = bytearray(size)
                    reader.read_bytes(buffer)
                    cover = bytes(buffer)
        except Exception:
            cover = None
        return Media(
            props.title or "",
            props.artist or "",
            int(status) == 4,
            position.total_seconds() if position else 0.0,
            end.total_seconds() if end else 0.0,
            props.album_title or "",
            cover,
            time.monotonic(),
        )

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
        self.stocks: list[str] = list(cfg.get("stocks") or [
            "sh000001", "sz399001", "sh600519",
            "usNVDA", "usAAPL", "usGOOGL", "usMSFT",
        ])
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
        self._raw_weather: dict | None = None
        self._hourly_hour = -1
        self._last_minute = -1
        self._cover_cache: tuple[int, list[Text]] | None = None
        self._quotes_at = 0.0  # last successful market fetch, for the staleness hint

    def on_mount(self) -> None:
        self._load_todo()
        self.set_interval(1.0, self._tick)
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
        changed = False
        now = datetime.now()
        raw = _weather_raw()
        if raw is not None and (raw is not self._raw_weather or now.hour != self._hourly_hour):
            self._raw_weather = raw
            self._hourly_hour = now.hour
            hourly = parse_hourly(raw, now, 8)
            if hourly != self._hourly:
                self._hourly = hourly
                changed = True
        if self.state.air is None and time.monotonic() - self._last_air > 30:
            self._last_air = time.monotonic()
            self._poll_air()
        if self._load_todo():
            changed = True
        # the column only needs a repaint when a clock digit / progress bar moves,
        # or once a second while the music progress bar is running
        playing = bool(self.state.media and self.state.media.playing)
        if changed or playing or now.minute != self._last_minute:
            self._last_minute = now.minute
            self.refresh()

    def _todo_file(self) -> Path | None:
        if self.todo_path:
            return self.todo_path
        return storage.data_path("todo.txt")

    def _load_todo(self) -> bool:
        changed = False
        path = self._todo_file()
        mtime = 0.0
        if path is not None:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
        if mtime != self._todo_mtime:
            self._todo_mtime = mtime
            changed = True
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
            changed = True
            if notes is None or not notes.exists():
                self.state.notes = []
            else:
                try:
                    text = notes.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    text = ""
                self.state.notes = [line.strip() for line in text.splitlines() if line.strip()][:12]
        return changed

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
            self._quotes_at = time.time()
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
        media = self._sec_media(w)
        if media:
            blocks += media
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

    def _sec_media(self, w: int) -> list[Text]:
        if "media" not in self.modules:
            return []
        c = self._style()
        m = self.state.media
        playing = bool(m and m.playing)
        bars = "▁▂▃▄▅▆▇█"
        if playing:
            now = time.monotonic()
            eq = "".join(bars[1 + int((math.sin(now * 3.1 + i * 1.27) + 1) * 3)] for i in range(5))
        else:
            eq = "▁▁▁▁▁"

        head = Text(no_wrap=True, end="")
        head.append("◤ ", c["cyan"])
        head.append("音乐", f"bold {c['cyan']}")
        head.append("  " + eq, c["mag"] if playing else c["dim"])
        if m:
            head.append("   ▶" if playing else "   ❚❚", c["dim"])
        if not m or not m.title:
            return [head, Text(" 未在播放", style=c["dim"])]

        art_w = 12 if w >= 40 and m.cover else 0
        text_w = max(10, w - art_w - (3 if art_w else 0))

        title = m.title
        avail = max(6, text_w - 3)
        if cell_len(title) > avail:
            if playing:
                padded = title + "   "
                period = max(1, cell_len(padded))
                offset = int(time.monotonic() * 4) % period
                title = window_cells(padded + padded, offset, avail)
            else:
                title = trunc_cells(title, avail)
        else:
            title = trunc_cells(title, avail)

        rows: list[Text] = []
        line = Text(no_wrap=True, end="")
        line.append(" ♪ ", c["mag"] if playing else c["dim"])
        line.append(title, f"bold {c['text']}")
        rows.append(line)
        if m.artist:
            artist = Text(no_wrap=True, end="")
            artist.append("   " + trunc_cells(m.artist, avail), c["dim"])
            rows.append(artist)
        if m.album and m.album != m.title:
            album = Text(no_wrap=True, end="")
            album.append("   " + trunc_cells(m.album, avail), c["dim"])
            rows.append(album)

        pos = self._position(m)
        if m.duration > 1:
            ratio = max(0.0, min(1.0, pos / m.duration))
            bar_w = max(8, text_w - 14)
            filled = int(round(ratio * (bar_w - 1)))
            progress = Text(no_wrap=True, end="")
            progress.append("   ")
            for i in range(bar_w):
                if i < filled:
                    progress.append("━", theme.hexc(theme.ramp([theme.P.red, theme.P.magenta],
                                                               i / max(1, bar_w - 1))))
                elif i == filled:
                    progress.append("●", f"bold {theme.hexc(theme.P.magenta)}")
                else:
                    progress.append("─", theme.hexc(theme.mix(theme.P.dim, theme.P.panel, 0.5)))
            progress.append(f" {int(pos) // 60}:{int(pos) % 60:02d}", c["text"])
            progress.append(f"/{int(m.duration) // 60}:{int(m.duration) % 60:02d}", c["dim"])
            rows.append(progress)

        out = [head]
        art = self._cover_lines(m, art_w, min(5, max(3, len(rows)))) if art_w else []
        for i in range(max(len(rows), len(art))):
            line = Text(no_wrap=True, end="")
            if art:
                line.append(" ")
                if i < len(art):
                    line.append_text(art[i])
                else:
                    line.append(" " * art_w)
                line.append("  ")
            if i < len(rows):
                line.append_text(rows[i])
            out.append(line)
        return out

    def _position(self, media: Media) -> float:
        pos = media.position
        if media.playing and media.stamp:
            pos += max(0.0, time.monotonic() - media.stamp)
        if media.duration > 0:
            pos = min(pos, media.duration)
        return pos

    def _cover_lines(self, media: Media, w: int, h: int) -> list[Text]:
        if not media.cover:
            return []
        key = hash(media.cover)
        if self._cover_cache is not None and self._cover_cache[0] == key:
            return self._cover_cache[1]
        lines: list[Text] = []
        try:
            import io

            from PIL import Image, ImageOps

            with Image.open(io.BytesIO(media.cover)) as img:
                rgb = img.convert("RGB")
                rgb = ImageOps.fit(rgb, (w, h * 2), method=Image.LANCZOS, centering=(0.5, 0.5))
                px = np.asarray(rgb, dtype=np.uint8)
            for y in range(h):
                line = Text(no_wrap=True, end="")
                for x in range(w):
                    fg = "#{:02x}{:02x}{:02x}".format(*(int(v) for v in px[y * 2, x]))
                    bg = "#{:02x}{:02x}{:02x}".format(*(int(v) for v in px[y * 2 + 1, x]))
                    line.append("▀", f"{fg} on {bg}")
                lines.append(line)
        except Exception:
            lines = []
        self._cover_cache = (key, lines)
        return lines

    def _sec_custom(self, w: int) -> list[Text]:
        c = self._style()
        mods = [m.upper() for m in self.modules if m != "media"]
        extra = " ".join(mods)
        age = time.time() - self._quotes_at if self._quotes_at else 0.0
        if self.state.quotes and age > 180:  # 24/7: say so instead of showing stale numbers
            extra += f" · {age / 60:.0f}m前"
        lines = [self._header("自选", extra)]
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












