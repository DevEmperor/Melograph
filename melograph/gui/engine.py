"""The slow work – listening, engraving, synthesizing, exporting – in a process of its own.

The window talks to it through two queues.  A transcription can take a minute,
and music21 and Verovio hold the interpreter while they work; in a separate
process none of that makes the window stutter, and cancelling is simply
ending the process.
"""

from __future__ import annotations

import math
import multiprocessing as mp
import os
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal

# ── inside the engine process ───────────────────────────────────────────────


class _Work:
    """State of the engine process: the recording that is open and its last analysis."""

    def __init__(self, replies):
        self.replies = replies
        self.key = None
        self.source = None
        self.performance = None
        self.beats = None
        self.downbeats = None
        self.result = None
        self.xml = ""
        self.engraving = None
        self.revision = 0
        self.app = None

    def reply(self, job, kind, **values):
        self.replies.put({"id": job.get("id"), "type": kind, **values})

    def qt(self):
        """Qt for SVG measurements and PDF, without a screen."""
        if self.app is None:
            from PySide6.QtGui import QGuiApplication

            from ..render import register_fonts

            self.app = QGuiApplication(["melograph-engine"])
            register_fonts()
        return self.app

    # -- listening --------------------------------------------------------

    def hear(self, job):
        from .. import cache
        from ..audio import MIDI_SUFFIXES, load_audio

        source = Path(job["path"])
        key = cache.fingerprint(source)
        remembered = None if job.get("fresh") else cache.load(key)
        peaks = cache.peaks(key)
        device = "cpu"
        if remembered is not None:
            performance, beats, downbeats = remembered
            self.reply(job, "stage", stage="cache")
        elif source.suffix.lower() in MIDI_SUFFIXES:
            from ..transcribe import read_midi

            self.reply(job, "stage", stage="load")
            performance = read_midi(source)
            beats = downbeats = None
            peaks = None
            cache.save(key, source, performance, None, None)
        else:
            from ..beats import beat_model_ready, track_audio
            from ..transcribe import pick_device, transcribe

            self.reply(job, "stage", stage="load")
            audio = load_audio(source)
            peaks = cache.waveform_peaks(audio)
            self.reply(job, "loaded", duration=len(audio) / 44100, peaks=peaks.tolist())
            self.reply(job, "stage", stage="transcribe")
            device = pick_device(job.get("device", "auto"))
            try:
                performance = transcribe(audio, device, lambda done, total: self.reply(job, "progress", done=done, total=total))
            except RuntimeError as problem:
                if "out of memory" not in str(problem).lower() or device == "cpu":
                    raise
                device = "cpu"
                performance = transcribe(audio, device, lambda done, total: self.reply(job, "progress", done=done, total=total))
            self.reply(job, "stage", stage="beats", download=not beat_model_ready())
            try:
                beats, downbeats = track_audio(audio, 44100, device)
            except Exception:
                beats = downbeats = None
            cache.save(key, source, performance, beats, downbeats, peaks)
            del audio
        if not performance.notes:
            self.reply(job, "error", message="no_notes")
            return
        self.key, self.source = key, source
        self.performance, self.beats, self.downbeats = performance, beats, downbeats
        self.result = None
        self.reply(
            job, "heard", key=key, cached=remembered is not None, device=device,
            duration=performance.duration, notes=len(performance.notes), pedals=len(performance.pedals),
            peaks=peaks.tolist() if peaks is not None else [], beatsFromAudio=beats is not None,
            settings=cache.settings(key),
        )

    # -- notation ---------------------------------------------------------

    def analyse(self, job):
        from .. import cache
        from ..export import musicxml_text
        from ..pipeline import analyse
        from ..render import engrave
        from .options import to_options

        if self.performance is None:
            return
        values = job.get("options", {})
        cache.store_settings(self.key, values)
        options = to_options(values, self.source)
        result = analyse(self.performance, self.beats, self.downbeats, options)
        xml = musicxml_text(result.score)
        seconds = result.layout.seconds_of_quarter(result.grid)
        engraving = engrave(xml, seconds, scale=int(job.get("scale", 40)))
        self.result, self.xml, self.engraving = result, xml, engraving
        self.revision += 1

        folder = cache.folder(self.key) / "pages"
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.svg"):
            old.unlink(missing_ok=True)
        pages = []
        for index, svg in enumerate(engraving.pages):
            path = folder / f"r{self.revision}-p{index + 1}.svg"
            path.write_text(svg, encoding="utf-8")
            pages.append(str(path))
        rects = self._rects(engraving)
        bar_times = [seconds(float(edge)) for edge in result.layout.edges]
        self.reply(
            job, "analysed", revision=self.revision, pages=pages, size=list(engraving.page_size),
            events=engraving.events, measures=engraving.measures, rects=rects,
            summary=_summary(result), roll=_roll(result), bars=bar_times,
            beats=[float(t) for t in result.grid.times],
        )
        if job.get("thumbnail") and pages:
            self._thumbnail(engraving.pages[0], cache.folder(self.key) / "thumb.png")

    def _rects(self, engraving):
        """Where each note and each bar sits on its page, as fractions of the page size."""
        from PySide6.QtCore import QByteArray
        from PySide6.QtSvg import QSvgRenderer

        self.qt()
        width, height = engraving.page_size
        renderers = [QSvgRenderer(QByteArray(svg.encode("utf-8"))) for svg in engraving.pages]

        def box(page: int, ident: str):
            renderer = renderers[page]
            if not renderer.elementExists(ident):
                return None
            r = renderer.transformForElement(ident).mapRect(renderer.boundsOnElement(ident))
            return [page, r.x() / width, r.y() / height, r.width() / width, r.height() / height]

        notes = {ident: box(page, ident) for ident, page in engraving.note_pages.items() if 0 <= page < len(renderers)}
        measures = {ident: box(page, ident) for _t, ident, page in engraving.measures if 0 <= page < len(renderers)}
        return {"notes": {k: v for k, v in notes.items() if v}, "measures": {k: v for k, v in measures.items() if v}}

    def _thumbnail(self, svg: str, path: Path):
        from PySide6.QtCore import QByteArray, QRectF, Qt
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer

        self.qt()
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        size = renderer.defaultSize()
        width = 360
        height = int(width * size.height() / max(1, size.width()))
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter, QRectF(0, 0, width, height))
        painter.end()
        image.copy(0, 0, width, int(width * 0.62)).save(str(path))

    # -- sound of the notes ------------------------------------------------

    def synth(self, job):
        from .. import cache
        from ..synth import render

        if self.result is None:
            return
        result = self.result
        events = _playback_events(result)
        pedals = [(p.start, p.end) for p in self.performance.pedals]
        length = max(self.performance.duration, max((e[1] for e in events), default=0) + 1.5)
        path = cache.folder(self.key) / f"score-r{self.revision}.wav"
        for old in cache.folder(self.key).glob("score-r*.wav"):
            if old != path:
                old.unlink(missing_ok=True)
        render(events, pedals, length, path)
        self.reply(job, "synthesized", revision=self.revision, path=str(path))

    # -- export -----------------------------------------------------------

    def export(self, job):
        from ..transcribe import write_midi

        kind, path = job["format"], Path(job["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "musicxml":
            path.write_text(self.xml, encoding="utf-8")
        elif kind == "pdf":
            self._pdf(path)
        elif kind == "midi-score":
            self._score_midi(path)
        elif kind == "midi-performance":
            write_midi(self.performance, path)
        elif kind == "mei":
            import verovio

            toolkit = verovio.toolkit()
            toolkit.loadData(self.xml)
            path.write_text(toolkit.getMEI(), encoding="utf-8")
        else:
            raise ValueError(kind)
        self.reply(job, "exported", format=kind, path=str(path))

    def _pdf(self, path: Path):
        from ..render import write_pdf

        self.qt()
        write_pdf(self.engraving.pages, path, self.result.score.metadata.title or "")

    def _score_midi(self, path: Path):
        import pretty_midi

        events = _playback_events(self.result)
        midi = pretty_midi.PrettyMIDI(resolution=960)
        piano = pretty_midi.Instrument(program=0, name="Piano")
        for start, end, pitch, velocity in events:
            piano.notes.append(pretty_midi.Note(int(velocity), int(pitch), float(start), float(end)))
        midi.instruments.append(piano)
        midi.write(str(path))


def _summary(result) -> dict:
    unit, bpm = result.tempo
    fifths = result.key.fifths
    first = min(n.pos for n in result.notes)
    pickup = float(result.layout.bars[0].length / result.meter.beat_ql) if result.layout.bars[0].number == 0 else 0.0
    return {
        "keyDe": result.key.label("de"), "keyEn": result.key.label("en"),
        "keyValue": _key_value(result.key), "fifths": fifths,
        "meter": str(result.meter), "tempoUnit": unit, "tempo": bpm,
        "bars": len(result.layout.bars), "notes": len(result.notes),
        "right": result.right_hand, "left": result.left_hand,
        "pickup": pickup, "swing": result.marks.swing, "first": float(first),
        "slurs": len(result.marks.slurs), "pedals": len(result.marks.pedals),
        "beatsPerBar": result.grid.beats_per_bar,
    }


def _key_value(key) -> str:
    step, alter = key.tonic_name
    return step + ("#" * alter if alter > 0 else "b" * -alter) + ("m" if key.minor else "")


def _roll(result) -> list:
    """Played notes for the piano roll: onset, release, pitch, hand, velocity."""
    return [
        [round(n.onset, 4), round(max(n.offset, n.onset + 0.03), 4), n.pitch, n.hand, n.velocity]
        for n in sorted(result.notes, key=lambda n: n.onset)
    ]


def _playback_events(result) -> list[tuple[float, float, int, int]]:
    """The written notes at the times of the recording, so both line up when played together."""
    from ..quantize import swing_unwarp

    grid = result.grid
    swing = result.marks.swing

    def seconds(pos) -> float:
        b = float(pos)
        if swing:
            whole = math.floor(b)
            b = whole + swing_unwarp(b - whole)
        return grid.time_of(b)

    # A rolled chord sounds note by note, from the bottom up.
    order: dict[int, int] = {}
    for roll in {n.roll for n in result.notes if n.roll}:
        for rank, m in enumerate(sorted((m for m in result.notes if m.roll == roll), key=lambda m: m.pitch)):
            order[id(m)] = rank

    events = []
    for n in result.notes:
        if n.grace_of is not None:
            start = seconds(n.grace_of.pos) - 0.07
            events.append((max(0.0, start), start + 0.06, n.pitch, n.velocity))
            continue
        start = seconds(n.pos) + 0.025 * order.get(id(n), 0)
        end = seconds(n.pos + n.dur)
        length = end - start
        end = start + length * (0.5 if n.staccato else 0.96)
        events.append((start, end, n.pitch, n.velocity))
    return events


def serve(requests, replies):
    import warnings

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    warnings.filterwarnings("ignore")  # PyTorch talks a lot about things that do not matter here
    work = _Work(replies)
    handlers = {"hear": work.hear, "analyse": work.analyse, "synth": work.synth, "export": work.export}
    while True:
        job = requests.get()
        if job is None:
            break
        try:
            handlers[job["op"]](job)
        except Exception as problem:  # reported to the window, which shows it
            work.reply(job, "error", message=str(problem) or problem.__class__.__name__, trace=traceback.format_exc(), op=job["op"])


# ── in the window process ───────────────────────────────────────────────────


class Engine(QObject):
    """Starts the engine process and passes its replies on as a Qt signal."""

    reply = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._context = mp.get_context("spawn")
        self._next = 0
        self._process = None
        self._start()

    def _start(self):
        self._requests = self._context.Queue()
        self._replies = self._context.Queue()
        self._process = self._context.Process(target=serve, args=(self._requests, self._replies), daemon=True, name="melograph-engine")
        self._process.start()
        replies = self._replies
        threading.Thread(target=self._listen, args=(replies,), daemon=True).start()

    def _listen(self, replies):
        while True:
            try:
                message = replies.get()
            except (EOFError, OSError, ValueError):
                return
            if message is None:
                return
            self.reply.emit(message)

    def send(self, op: str, **values) -> int:
        self._next += 1
        self._requests.put({"id": self._next, "op": op, **values})
        return self._next

    def restart(self):
        """Stop whatever runs (cancel) and start a fresh process."""
        try:
            self._replies.put(None)
        except (OSError, ValueError):
            pass
        if self._process is not None and self._process.is_alive():
            self._process.terminate()
            self._process.join(2)
        self._start()

    def stop(self):
        try:
            self._requests.put(None)
            self._replies.put(None)
        except (OSError, ValueError):
            pass
        if self._process is not None:
            self._process.join(1.5)
            if self._process.is_alive():
                self._process.terminate()
