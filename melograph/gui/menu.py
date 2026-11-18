"""Melograph's entry in the application menu, made from inside the program.

An AppImage is a single file the desktop knows nothing about; with one switch in
the preferences it gets a menu entry (and opens audio files from the file manager).
The entry points at the AppImage, or at melograph.sh in a copy of the sources.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

APP_ID = "net.devemperor.Melograph"
HERE = Path(__file__).parent
MARK = "X-Melograph-Made-By=preferences"


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def entry_path() -> Path:
    return _data_home() / "applications" / f"{APP_ID}.desktop"


def icon_path() -> Path:
    return _data_home() / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg"


def launcher() -> str | None:
    """What the entry starts: this AppImage, melograph.sh of this source copy, or the `melograph` command."""
    appimage = os.environ.get("APPIMAGE")
    if appimage and os.path.isfile(appimage):
        return appimage
    script = HERE.parents[1] / "melograph.sh"
    if script.is_file():
        return str(script)
    return shutil.which("melograph")


def installed() -> bool:
    return entry_path().is_file()


def _quoted(path: str) -> str:
    """A path as one argument of an Exec line (Desktop Entry Specification)."""
    if not any(c in path for c in ' \t"\'\\><~|&;$*?#()`'):
        return path
    return '"' + "".join("\\" + c if c in '"`$\\' else c for c in path) + '"'


def _entry(command: str) -> str:
    lines = []
    for line in (HERE / f"{APP_ID}.desktop").read_text(encoding="utf-8").splitlines():
        if line.startswith("Exec="):
            line = f"Exec={_quoted(command)} --gui %F"
        lines.append(line)
        if line.startswith("Exec="):
            lines.append(f"TryExec={command}")  # the entry disappears with the file it starts
    lines.append(MARK)
    return "\n".join(lines) + "\n"


def install() -> None:
    command = launcher()
    if command is None:
        raise OSError("no launcher")
    entry_path().parent.mkdir(parents=True, exist_ok=True)
    icon_path().parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / "icons" / f"{APP_ID}.svg", icon_path())
    temporary = entry_path().with_suffix(".tmp")
    temporary.write_text(_entry(command), encoding="utf-8")
    temporary.replace(entry_path())
    _refresh_menu()


def remove() -> None:
    entry_path().unlink(missing_ok=True)
    icon_path().unlink(missing_ok=True)
    _refresh_menu()


def follow_move() -> None:
    """After an update or a move, point an existing entry from the preferences at this AppImage."""
    appimage = os.environ.get("APPIMAGE")
    if not appimage or not installed():
        return
    try:
        text = entry_path().read_text(encoding="utf-8")
    except OSError:
        return
    if MARK in text and f"TryExec={appimage}\n" not in text:
        try:
            install()
        except OSError:
            pass


def _refresh_menu() -> None:
    if shutil.which("update-desktop-database"):
        try:
            subprocess.run(["update-desktop-database", str(entry_path().parent)], capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
