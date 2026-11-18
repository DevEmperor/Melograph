"""Sound for the written notes, so they can be heard next to the recording.

With FluidSynth and a piano SoundFont on the system (MuseScore brings one)
the notes sound like a piano; otherwise a small additive synthesizer stands in.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .audio import SAMPLE_RATE

SOUNDFONT_PLACES = [
    "~/.local/share/soundfonts/*.sf[23]",
    "/usr/share/soundfonts/*.sf[23]",
    "/usr/share/sounds/sf2/*.sf[23]",
    "/usr/share/sounds/sf3/*.sf[23]",
    "/usr/share/mscore*/sound/*.sf[23]",
    "/usr/share/musescore*/sound/*.sf[23]",
    "/usr/lib/mscore*/sound/*.sf[23]",
]


def soundfont() -> Path | None:
    """The best piano SoundFont that can be found."""
    found = []
    for pattern in SOUNDFONT_PLACES:
        found.extend(Path(p) for p in glob.glob(os.path.expanduser(pattern)))
    if not found:
        return None

    def rank(path: Path) -> tuple[int, int]:
        name = path.name.lower()
        preference = next((i for i, word in enumerate(("salamander", "piano", "musescore_general", "ms basic", "fluid")) if word in name), 9)
        return preference, -path.stat().st_size
    return min(found, key=rank)


def available() -> str:
    """'fluidsynth' when real piano sound is possible, otherwise 'simple'."""
    return "fluidsynth" if shutil.which("fluidsynth") and soundfont() else "simple"


def render(events: list[tuple[float, float, int, int]], pedals: list[tuple[float, float]], length: float, path: Path) -> Path:
    """Write the notes ((start s, end s, pitch, velocity)) as a WAV file of `length` seconds."""
    if available() == "fluidsynth":
        try:
            return _fluidsynth(events, pedals, length, path)
        except (OSError, subprocess.SubprocessError, RuntimeError):
            pass
    audio = _additive(events, length)
    _write_wav(path, audio)
    return path


def _fluidsynth(events, pedals, length: float, path: Path) -> Path:
    import pretty_midi

    midi = pretty_midi.PrettyMIDI(resolution=960)
    piano = pretty_midi.Instrument(program=0)
    for start, end, pitch, velocity in events:
        piano.notes.append(pretty_midi.Note(int(max(1, min(127, velocity))), int(pitch), float(start), float(max(end, start + 0.03))))
    for down, up in pedals:
        piano.control_changes.append(pretty_midi.ControlChange(64, 127, float(down)))
        piano.control_changes.append(pretty_midi.ControlChange(64, 0, float(up)))
    midi.instruments.append(piano)
    with tempfile.TemporaryDirectory(prefix="melograph-") as folder:
        source = Path(folder) / "score.mid"
        midi.write(str(source))
        raw = Path(folder) / "score.wav"
        command = [
            "fluidsynth", "-ni", "-q", "-g", "0.7", "-r", str(SAMPLE_RATE), "-o", "synth.reverb.active=1",
            "-F", str(raw), str(soundfont()), str(source),
        ]
        subprocess.run(command, capture_output=True, timeout=600, check=True)
        if not raw.exists():
            raise RuntimeError("fluidsynth")
        audio = _read_wav(raw)
    # Same length as the recording, so both can be played side by side.
    frames = int(length * SAMPLE_RATE)
    if len(audio) < frames:
        audio = np.concatenate([audio, np.zeros((frames - len(audio), 2), dtype=np.float32)])
    _write_wav(path, audio[:frames])
    return path


def _additive(events, length: float) -> np.ndarray:
    """A plain piano-like tone: a few slightly stretched partials that fade like a struck string."""
    frames = int(length * SAMPLE_RATE) + 1
    out = np.zeros((frames, 2), dtype=np.float32)
    for start, end, pitch, velocity in events:
        f0 = 440.0 * 2 ** ((pitch - 69) / 12)
        ring = min(4.0, max(0.25, (end - start) + 0.25))
        n = int(ring * SAMPLE_RATE)
        a = int(start * SAMPLE_RATE)
        if a >= frames:
            continue
        n = min(n, frames - a)
        t = np.arange(n) / SAMPLE_RATE
        decay = np.exp(-t / (0.6 + 2.5 * (1 - (pitch - 21) / 88)))
        tone = np.zeros(n)
        for k in range(1, 7):
            fk = f0 * k * np.sqrt(1 + 0.0004 * k * k)
            if fk > SAMPLE_RATE / 2:
                break
            tone += np.sin(2 * np.pi * fk * t) / k ** 1.3 * np.exp(-t * k * 0.6)
        envelope = np.minimum(1.0, t / 0.004) * decay
        release = max(0.0, end - start)
        envelope *= np.where(t < release, 1.0, np.exp(-(t - release) / 0.08))
        level = 0.12 * (velocity / 127) ** 1.5
        pan = (pitch - 21) / 87
        signal = (tone * envelope * level).astype(np.float32)
        out[a:a + n, 0] += signal * (1.1 - pan * 0.4)
        out[a:a + n, 1] += signal * (0.7 + pan * 0.4)
    peak = float(np.abs(out).max()) or 1.0
    return out / max(peak / 0.8, 1.0)


def _read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        channels, width, rate = handle.getnchannels(), handle.getsampwidth(), handle.getframerate()
        data = handle.readframes(handle.getnframes())
    if width == 2:
        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768
    elif width == 4:
        audio = np.frombuffer(data, dtype=np.int32).astype(np.float32) / 2**31
    else:
        raise RuntimeError("wav")
    audio = audio.reshape(-1, channels)
    if channels == 1:
        audio = np.repeat(audio, 2, axis=1)
    if rate != SAMPLE_RATE:
        positions = np.arange(int(len(audio) * SAMPLE_RATE / rate)) * rate / SAMPLE_RATE
        audio = np.stack([np.interp(positions, np.arange(len(audio)), audio[:, c]) for c in range(2)], axis=1)
    return audio[:, :2].astype(np.float32)


def read_wav(path: Path) -> np.ndarray:
    return _read_wav(path)


def _write_wav(path: Path, audio: np.ndarray) -> None:
    data = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(data.tobytes())
