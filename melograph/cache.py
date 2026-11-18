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

from .model import Performance

FORMAT = 1  # bump when what is stored changes


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


def load(key: str) -> tuple[Performance, np.ndarray | None, np.ndarray | None] | None:
    from .transcribe import read_midi

    here = folder(key)
    midi = here / "performance.mid"
    if not midi.exists():
        return None
    try:
        performance = read_midi(midi)
        info = json.loads((here / "info.json").read_text())
        performance.duration = max(performance.duration, float(info.get("duration", 0)))
        beats = downbeats = None
        if (here / "beats.npz").exists():
            data = np.load(here / "beats.npz")
            beats, downbeats = data["beats"], data["downbeats"]
            if len(beats) == 0:
                beats = downbeats = None
        os.utime(here, None)  # recently used
        return performance, beats, downbeats
    except (OSError, ValueError, KeyError):
        return None


def save(key: str, source: Path, performance: Performance, beats, downbeats, peaks=None) -> None:
    from .transcribe import write_midi

    here = folder(key)
    here.mkdir(parents=True, exist_ok=True)
    write_midi(performance, here / "performance.mid")
    np.savez(
        here / "beats.npz",
        beats=np.asarray(beats if beats is not None else [], dtype=float),
        downbeats=np.asarray(downbeats if downbeats is not None else [], dtype=float),
    )
    if peaks is not None:
        np.save(here / "peaks.npy", np.asarray(peaks, dtype=np.float32))
    info = {"source": str(source), "duration": performance.duration, "saved": time.time()}
    (here / "info.json").write_text(json.dumps(info))


def peaks(key: str) -> np.ndarray | None:
    file = folder(key) / "peaks.npy"
    return np.load(file) if file.exists() else None


def settings(key: str) -> dict:
    try:
        return json.loads((folder(key) / "settings.json").read_text())
    except (OSError, ValueError):
        return {}


def store_settings(key: str, values: dict) -> None:
    here = folder(key)
    here.mkdir(parents=True, exist_ok=True)
    (here / "settings.json").write_text(json.dumps(values, indent=1))


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
