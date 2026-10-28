"""Guess the local city from the OS timezone.

IP geolocation is useless behind a VPN: a Tokyo exit makes wttr.in report Tokyo
weather and pins the globe in Tokyo. The OS timezone still reflects where the
machine actually is, so it makes a much better default.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Windows timezone id -> a city wttr.in understands
WINDOWS_CITIES: dict[str, str] = {
    "China Standard Time": "Shanghai",
    "Taipei Standard Time": "Taipei",
    "Tokyo Standard Time": "Tokyo",
    "Korea Standard Time": "Seoul",
    "Singapore Standard Time": "Singapore",
    "Hong Kong Standard Time": "Hong Kong",
    "W. Europe Standard Time": "Berlin",
    "Central Europe Standard Time": "Budapest",
    "Romance Standard Time": "Paris",
    "GMT Standard Time": "London",
    "Eastern Standard Time": "New York",
    "Central Standard Time": "Chicago",
    "Mountain Standard Time": "Denver",
    "Pacific Standard Time": "Los Angeles",
    "AUS Eastern Standard Time": "Sydney",
    "India Standard Time": "Mumbai",
    "Russian Standard Time": "Moscow",
    "Arabian Standard Time": "Dubai",
    "SE Asia Standard Time": "Bangkok",
    "Malay Peninsula Standard Time": "Kuala Lumpur",
    "Atlantic Standard Time": "Halifax",
}


def city_for_windows_tz(name: str | None) -> str | None:
    """Map a Windows timezone id ("China Standard Time") to a city name."""
    return WINDOWS_CITIES.get(name) if name else None


def city_for_iana(key: str | None) -> str | None:
    """Map an IANA zone ("Asia/Shanghai") to its city ("Shanghai")."""
    if not key or "/" not in key:
        return None
    tail = key.rstrip("/").rsplit("/", 1)[1]
    if not tail or tail[0].isdigit() or tail.startswith(("GMT", "UTC")):
        return None
    return tail.replace("_", " ")


def _windows_tz() -> str | None:
    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation",
        ) as key:
            return str(winreg.QueryValueEx(key, "TimeZoneKeyName")[0])
    except OSError:
        return None


def _iana_key() -> str | None:
    env = os.environ.get("TZ")
    if env:
        return env.lstrip(":")
    link = Path("/etc/localtime")
    try:
        if link.is_symlink():
            target = os.readlink(link)
            if "zoneinfo/" in target:
                return target.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return None


def system_city() -> str | None:
    """City implied by the OS timezone, or None when it cannot be determined."""
    if sys.platform == "win32":
        return city_for_windows_tz(_windows_tz())
    return city_for_iana(_iana_key())


def parse_location(text: str) -> tuple[float, float, str] | None:
    """'31.23, 121.47, Shanghai' -> (31.23, 121.47, 'Shanghai'), None if invalid."""
    parts = [part.strip() for part in text.replace("，", ",").split(",")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if not -90.0 <= lat <= 90.0:
        return None
    lon = ((lon + 180.0) % 360.0) - 180.0
    return round(lat, 6), round(lon, 6), ",".join(parts[2:]).strip()


def format_location(cfg: object) -> str:
    """Config location dict -> the string shown in the editor."""
    if not isinstance(cfg, dict):
        return ""
    try:
        lat, lon = float(cfg["lat"]), float(cfg["lon"])
    except (KeyError, TypeError, ValueError):
        return ""
    name = str(cfg.get("name") or "").strip()
    text = f"{lat:.4f}, {lon:.4f}"
    return f"{text}, {name}" if name else text
