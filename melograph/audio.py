"""Audio decoding.

Three ways, the first that is there wins: PyAV (FFmpeg inside Python, shipped with
the AppImage), the `ffmpeg` command of the system, and miniaudio, which needs
nothing else but only knows MP3, WAV, FLAC and Ogg Vorbis.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100

AUDIO_SUFFIXES = {
    ".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".aiff", ".aif",
    ".mp4", ".mkv", ".mov", ".webm",
}
MIDI_SUFFIXES = {".mid", ".midi"}
MINIAUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".ogg"}


class AudioError(RuntimeError):
    pass


def load_audio(path: Path) -> np.ndarray:
    """Decode any audio or video file to float32 stereo at 44.1 kHz, shape (samples, 2)."""
    if importlib.util.find_spec("av") is not None:
        return _with_pyav(path)
    if shutil.which("ffmpeg") is not None:
        return _with_ffmpeg(path)
    if path.suffix.lower() in MINIAUDIO_SUFFIXES:
        return _with_miniaudio(path)
    raise AudioError("ffmpeg")


def _with_pyav(path: Path) -> np.ndarray:
    import av

    try:
        with av.open(str(path)) as container:
            stream = next((s for s in container.streams if s.type == "audio"), None)
            if stream is None:
                raise AudioError("no audio")
            resampler = av.AudioResampler(format="flt", layout="stereo", rate=SAMPLE_RATE)
            chunks = []
            for frame in container.decode(stream):
                chunks.extend(f.to_ndarray().reshape(-1, 2) for f in resampler.resample(frame))
            chunks.extend(f.to_ndarray().reshape(-1, 2) for f in resampler.resample(None))
    except av.FFmpegError as problem:
        raise AudioError(str(problem)) from None
    if not chunks:
        raise AudioError("decode")
    return np.concatenate(chunks).astype(np.float32, copy=False)


def _with_ffmpeg(path: Path) -> np.ndarray:
    command = [
        "ffmpeg", "-v", "error", "-nostdin", "-i", str(path),
        "-vn", "-ac", "2", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-",
    ]
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0 or not result.stdout:
        raise AudioError(result.stderr.decode(errors="replace").strip() or "decode")
    samples = np.frombuffer(result.stdout, dtype=np.float32)
    return samples.reshape(-1, 2).copy()


def _with_miniaudio(path: Path) -> np.ndarray:
    import miniaudio

    try:
        sound = miniaudio.decode_file(
            str(path), output_format=miniaudio.SampleFormat.FLOAT32, nchannels=2, sample_rate=SAMPLE_RATE,
        )
    except miniaudio.DecodeError as problem:
        raise AudioError(str(problem)) from None
    return np.frombuffer(sound.samples, dtype=np.float32).reshape(-1, 2).copy()
