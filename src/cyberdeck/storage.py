"""Config / cache locations with graceful fallbacks.

macOS uses ~/Library, Windows usually gives us %LOCALAPPDATA% (which can be
locked down by policy), and Linux follows XDG. We probe a few places and keep
the first one we can actually write to.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

APP = "cyberdeck"
_resolved: dict[str, Path | None] = {}


def _candidate_dirs(name: str) -> list[Path]:
    dirs: list[Path] = []
    home = Path.home()
    if sys.platform == "darwin":
        # weather.json is a cache; everything else is user state
        if name == "weather.json":
            dirs.append(home / "Library" / "Caches" / APP)
        dirs.append(home / "Library" / "Application Support" / APP)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / APP)
    config = os.environ.get("XDG_CONFIG_HOME")
    if config:
        dirs.append(Path(config) / APP)
    cache = os.environ.get("XDG_CACHE_HOME")
    if cache:
        dirs.append(Path(cache) / APP)
    dirs += [home / ".config" / APP, home / ".cache" / APP]
    if os.environ.get("TEMP"):
        dirs.append(Path(os.environ["TEMP"]))
    dirs.append(Path(tempfile.gettempdir()))
    dirs.append(Path.cwd() / f".{APP}")
    # keep order, drop duplicates
    seen: set[Path] = set()
    out: list[Path] = []
    for folder in dirs:
        if folder not in seen:
            seen.add(folder)
            out.append(folder)
    return out


def data_path(name: str) -> Path | None:
    """First writable path for `name`, or None when nothing is writable."""
    if name in _resolved:
        return _resolved[name]
    for folder in _candidate_dirs(name):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".probe"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            _resolved[name] = folder / name
            return _resolved[name]
        except OSError:
            continue
    _resolved[name] = None
    return None


def load_json(name: str) -> dict[str, Any] | None:
    path = data_path(name)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def save_json(name: str, payload: dict[str, Any]) -> bool:
    path = data_path(name)
    if path is None:
        return False
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return False
    return True
