"""Preferences and the list of recent pieces, as small JSON files."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

PREFERENCES = {
    "language": "auto",  # "auto", "de" or "en"
    "device": "auto",
    "follow": True,  # the score follows the music while playing
    "mode": "original",
    "volume": 0.9,
    "view": "score",  # "score" or "roll"
    "sidebar": True,
    "zoom": 1.0,
    "exportFolder": "",
    "openAfterExport": False,
    "windowWidth": 1280,
    "windowHeight": 820,
    "windowMaximized": False,
}


def _config() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "melograph"


def _data() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "melograph"


def user_dir(name: str, fallback: str) -> Path:
    try:
        found = subprocess.run(["xdg-user-dir", name], capture_output=True, text=True, timeout=3).stdout.strip()
        if found and Path(found) != Path.home():
            return Path(found)
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.home() / fallback


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=1, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def load_preferences() -> dict:
    stored = _read(_config() / "settings.json", {})
    return {key: stored.get(key, default) for key, default in PREFERENCES.items()}


def save_preferences(values: dict) -> None:
    _write(_config() / "settings.json", values)


def load_history() -> list[dict]:
    entries = _read(_data() / "history.json", [])
    return [e for e in entries if isinstance(e, dict) and "path" in e]


def remember(entry: dict) -> list[dict]:
    """Put a piece at the top of the recent list (at most 30)."""
    entries = [e for e in load_history() if e.get("path") != entry["path"]]
    entry = dict(entry, opened=time.time())
    entries.insert(0, entry)
    entries = entries[:30]
    _write(_data() / "history.json", entries)
    return entries


def forget(path: str) -> list[dict]:
    entries = [e for e in load_history() if e.get("path") != path]
    _write(_data() / "history.json", entries)
    return entries
