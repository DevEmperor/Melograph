"""Playing the recording and the written notes, and recording from a microphone.

miniaudio talks directly to PipeWire, PulseAudio or ALSA and needs nothing
else on the system.  The recording and the sound of the notes are mixed here,
sample for sample, so that both can be heard at once and stay in step.
"""

from __future__ import annotations

import os
import threading
import time
import wave
from pathlib import Path

import numpy as np
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

RATE = 44100
LATENCY = 0.08  # seconds of audio in the device buffer


def _muted() -> bool:
    """Automatic tests run silently: no sound device is opened, time just runs on.

    (miniaudio's null device is no substitute: it asks for audio as fast as it can
    be made and keeps the interpreter too busy for anything else.)
    """
    return bool(os.environ.get("MELOGRAPH_MUTE"))


class Player(QObject):
    positionChanged = Signal()
    playingChanged = Signal()
    durationChanged = Signal()
    modeChanged = Signal()
    volumeChanged = Signal()
    readyChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._original: np.ndarray | None = None
        self._score: np.ndarray | None = None
        self._frame = 0
        self._playing = False
        self._mode = "original"  # "original", "score" or "both"
        self._volume = 0.9
        self._device = None
        self._started_at = 0.0
        self._started_frame = 0
        self._loading = 0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    # -- sources ------------------------------------------------------------

    def load_original(self, path: str) -> None:
        """Decode the recording in the background."""
        self.stop_device()
        self._original = None
        self._loading += 1
        token = self._loading

        def work():
            from ..audio import load_audio

            try:
                audio = load_audio(Path(path))
            except Exception:
                audio = None
            if token == self._loading:
                self._original = audio
                self.readyChanged.emit()
                self.durationChanged.emit()

        threading.Thread(target=work, daemon=True).start()

    def load_score(self, path: str) -> None:
        def work():
            from ..synth import read_wav

            try:
                self._score = read_wav(Path(path))
            except Exception:
                self._score = None
            self.readyChanged.emit()
            self.durationChanged.emit()

        threading.Thread(target=work, daemon=True).start()

    def clear(self) -> None:
        self.stop_device()
        self._loading += 1
        self._original = self._score = None
        self._frame = 0
        self.positionChanged.emit()
        self.readyChanged.emit()
        self.durationChanged.emit()

    def clear_score(self) -> None:
        self._score = None
        self.readyChanged.emit()

    # -- properties ---------------------------------------------------------

    def _get_position(self) -> float:
        if self._playing:
            elapsed = time.monotonic() - self._started_at
            return max(0.0, min(self._started_frame / RATE + elapsed - LATENCY, self._length() / RATE))
        return self._frame / RATE

    position = Property(float, _get_position, notify=positionChanged)

    def _length(self) -> int:
        lengths = [len(a) for a in (self._original, self._score) if a is not None]
        return max(lengths) if lengths else 0

    @Property(float, notify=durationChanged)
    def duration(self) -> float:
        return self._length() / RATE

    @Property(bool, notify=playingChanged)
    def playing(self) -> bool:
        return self._playing

    @Property(bool, notify=readyChanged)
    def originalReady(self) -> bool:
        return self._original is not None

    @Property(bool, notify=readyChanged)
    def scoreReady(self) -> bool:
        return self._score is not None

    def _get_mode(self) -> str:
        return self._mode

    def _set_mode(self, mode: str) -> None:
        if mode != self._mode:
            self._mode = mode
            self.modeChanged.emit()

    mode = Property(str, _get_mode, _set_mode, notify=modeChanged)

    def _get_volume(self) -> float:
        return self._volume

    def _set_volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, value))
        self.volumeChanged.emit()

    volume = Property(float, _get_volume, _set_volume, notify=volumeChanged)

    # -- control ------------------------------------------------------------

    @Slot()
    def toggle(self) -> None:
        self.pause() if self._playing else self.play()

    @Slot()
    def play(self) -> None:
        if self._playing or self._length() == 0:
            return
        if self._frame >= self._length() - RATE // 10:
            self._frame = 0
        if not _muted():
            import miniaudio

            try:
                self._device = miniaudio.PlaybackDevice(
                    output_format=miniaudio.SampleFormat.FLOAT32, nchannels=2, sample_rate=RATE,
                    buffersize_msec=int(LATENCY * 1000), app_name="Melograph",
                )
                stream = self._stream()
                next(stream)
                self._device.start(stream)
            except Exception:
                self._device = None
                return
        self._started_frame, self._started_at = self._frame, time.monotonic()
        self._playing = True
        self._timer.start()
        self.playingChanged.emit()

    @Slot()
    def pause(self) -> None:
        if not self._playing:
            return
        self._frame = int(self._get_position() * RATE)
        self.stop_device()
        self.positionChanged.emit()

    def stop_device(self) -> None:
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None
        if self._playing:
            self._playing = False
            self._timer.stop()
            self.playingChanged.emit()

    @Slot(float)
    def seek(self, seconds: float) -> None:
        frame = int(max(0.0, min(seconds, self._length() / RATE)) * RATE)
        if self._playing:
            self._frame = frame
            self._started_frame, self._started_at = frame, time.monotonic() + LATENCY
        else:
            self._frame = frame
        self.positionChanged.emit()

    @Slot(float)
    def skip(self, seconds: float) -> None:
        self.seek(self._get_position() + seconds)

    def _tick(self) -> None:
        self.positionChanged.emit()
        if self._get_position() >= self._length() / RATE - 0.01:
            self._frame = self._length()
            self.stop_device()
            self._frame = 0
            self.positionChanged.emit()

    def _stream(self):
        frames = yield b""
        while True:
            start = self._frame
            end = start + frames
            out = np.zeros((frames, 2), dtype=np.float32)
            gains = {"original": (1.0, 0.0), "score": (0.0, 1.0), "both": (0.75, 0.7)}[self._mode]
            for source, gain in ((self._original, gains[0]), (self._score, gains[1])):
                if source is not None and gain > 0 and start < len(source):
                    piece = source[start:end]
                    out[:len(piece)] += piece * gain
            self._frame = end
            frames = yield out * self._volume


class Recorder(QObject):
    """Records from the default microphone into a WAV file, with a level meter."""

    recordingChanged = Signal()
    levelChanged = Signal()
    elapsedChanged = Signal()
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._device = None
        self._chunks: list[np.ndarray] = []
        self._level = 0.0
        self._started = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    @Property(bool, notify=recordingChanged)
    def recording(self) -> bool:
        return self._device is not None

    @Property(float, notify=levelChanged)
    def level(self) -> float:
        return self._level

    @Property(float, notify=elapsedChanged)
    def elapsed(self) -> float:
        return time.monotonic() - self._started if self._device is not None else 0.0

    @Slot()
    def start(self) -> None:
        if self._device is not None:
            return
        self._chunks = []
        if _muted():  # tests: no microphone; stop() writes silence of the time that passed
            self._device = "muted"
            self._started = time.monotonic()
            self._timer.start()
            self.recordingChanged.emit()
            return
        import miniaudio


        def collect():
            while True:
                data = yield
                block = np.frombuffer(data, dtype=np.int16).reshape(-1, 2).copy()
                self._chunks.append(block)
                self._level = float(np.abs(block).max()) / 32768 if len(block) else 0.0

        try:
            device = miniaudio.CaptureDevice(
                input_format=miniaudio.SampleFormat.SIGNED16, nchannels=2, sample_rate=RATE,
                buffersize_msec=50, app_name="Melograph",
            )
            generator = collect()
            next(generator)
            device.start(generator)
        except Exception as problem:
            self.failed.emit(str(problem))
            return
        self._device = device
        self._started = time.monotonic()
        self._timer.start()
        self.recordingChanged.emit()

    @Slot(str)
    def stop(self, folder: str) -> None:
        if self._device is None:
            return
        if self._device == "muted":
            self._chunks = [np.zeros((int((time.monotonic() - self._started) * RATE), 2), dtype=np.int16)]
        try:
            if self._device != "muted":
                self._device.close()
        finally:
            self._device = None
            self._timer.stop()
            self.recordingChanged.emit()
        audio = np.concatenate(self._chunks) if self._chunks else np.zeros((0, 2), dtype=np.int16)
        self._chunks = []
        if len(audio) < RATE:  # under a second: nothing worth keeping
            self.failed.emit("short")
            return
        target = Path(folder)
        target.mkdir(parents=True, exist_ok=True)
        path = target / time.strftime("Melograph %Y-%m-%d %H-%M-%S.wav")
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(RATE)
            handle.writeframes(audio.tobytes())
        self.finished.emit(str(path))

    @Slot()
    def cancel(self) -> None:
        if self._device is not None:
            if self._device != "muted":
                self._device.close()
            self._device = None
            self._timer.stop()
            self._chunks = []
            self.recordingChanged.emit()

    def _tick(self) -> None:
        self.levelChanged.emit()
        self.elapsedChanged.emit()
        self._level *= 0.85
