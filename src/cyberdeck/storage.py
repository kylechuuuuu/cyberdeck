"""Config / cache locations with graceful fallbacks.

Windows usually gives us %LOCALAPPDATA%, but the directory can be locked down
(policy, sandbox, portable installs), so we probe a few places and keep the
first one we can actually write to.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP = "cyberdeck"
_resolved: dict[str, Path | None] = {}


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / APP)
    home = Path.home()
    dirs += [home / ".config" / APP, home / ".cache" / APP]
    if os.environ.get("TEMP"):
        dirs.append(Path(os.environ["TEMP"]))
    dirs.append(Path.cwd() / f".{APP}")
    return dirs


def data_path(name: str) -> Path | None:
    """First writable path for `name`, or None when nothing is writable."""
    if name in _resolved:
        return _resolved[name]
    for folder in _candidate_dirs():
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
