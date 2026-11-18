"""Remembers what was heard in a recording, so that it is only transcribed once.

Per recording (identified by its content, not its name) the cache keeps the
performance as MIDI, the beats, a waveform overview and the user's settings.
Changing the notation afterwards then takes a second instead of a minute.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

import numpy as np

from .beats import Tracked
from .model import Performance

FORMAT = 1  # bump when a stored performance can no longer be read


def root() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "melograph"


def fingerprint(path: Path) -> str:
    digest = hashlib.sha1(f"melograph-{FORMAT}".encode())
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()[:20]


def folder(key: str) -> Path:
    return root() / key


def load(key: str) -> tuple[Performance, Tracked | None] | None:
    """The performance and what the beat tracker heard (None for MIDI input, and for
    recordings remembered by an older version: their beats are then heard again)."""
    from .transcribe import read_midi

    here = folder(key)
    midi = here / "performance.mid"
    if not midi.exists():
        return None
    try:
        performance = read_midi(midi)
        info = json.loads((here / "info.json").read_text())
        performance.duration = max(performance.duration, float(info.get("duration", 0)))
        tracked = None
        if (here / "pulse.npz").exists():
            data = np.load(here / "pulse.npz")
            if len(data["beat"]):
                tracked = Tracked(data["beat"].astype(np.float32), data["downbeat"].astype(np.float32))
        os.utime(here, None)  # recently used
        return performance, tracked
    except (OSError, ValueError, KeyError):
        return None


def save(key: str, source: Path, performance: Performance, tracked: Tracked | None, peaks=None) -> None:
    from .transcribe import write_midi

    here = folder(key)
    here.mkdir(parents=True, exist_ok=True)
    write_midi(performance, here / "performance.mid")
    save_tracked(key, tracked)
    (here / "beats.npz").unlink(missing_ok=True)  # the beat list of older versions
    if peaks is not None:
        np.save(here / "peaks.npy", np.asarray(peaks, dtype=np.float32))
    info = {"source": str(source), "duration": performance.duration, "saved": time.time()}
    (here / "info.json").write_text(json.dumps(info))


def save_tracked(key: str, tracked: Tracked | None) -> None:
    """Keep what the beat tracker heard (half precision: 60 kB for five minutes)."""
    here = folder(key)
    here.mkdir(parents=True, exist_ok=True)
    empty = np.zeros(0, dtype=np.float16)
    np.savez(
        here / "pulse.npz",
        beat=tracked.beat.astype(np.float16) if tracked is not None else empty,
        downbeat=tracked.downbeat.astype(np.float16) if tracked is not None else empty,
    )


def peaks(key: str) -> np.ndarray | None:
    file = folder(key) / "peaks.npy"
    return np.load(file) if file.exists() else None


SETTINGS = 2  # version of the per-piece settings


def settings(key: str) -> dict:
    try:
        values = json.loads((folder(key) / "settings.json").read_text())
    except (OSError, ValueError):
        return {}
    if values.get("format") != SETTINGS and values.get("pedal") == "lines":
        # Stored before the pedal could be left to Melograph, when lines were simply the default.
        values["pedal"] = "auto"
    return values


def store_settings(key: str, values: dict) -> None:
    here = folder(key)
    here.mkdir(parents=True, exist_ok=True)
    (here / "settings.json").write_text(json.dumps(dict(values, format=SETTINGS), indent=1))


def size() -> int:
    total = 0
    for path in root().rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def clear() -> None:
    shutil.rmtree(root(), ignore_errors=True)


def waveform_peaks(audio: np.ndarray, columns: int = 2000) -> np.ndarray:
    """Loudness overview for drawing the waveform: one peak value per column, 0 … 1."""
    mono = np.abs(audio.mean(axis=1) if audio.ndim == 2 else audio)
    if len(mono) == 0:
        return np.zeros(columns, dtype=np.float32)
    edges = np.linspace(0, len(mono), columns + 1).astype(int)
    values = np.array([mono[a:b].max() if b > a else 0.0 for a, b in zip(edges, edges[1:])])
    top = float(np.percentile(values, 99.5)) or 1.0
    return np.clip(values / top, 0, 1).astype(np.float32)
