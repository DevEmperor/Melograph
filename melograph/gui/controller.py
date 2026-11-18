"""Everything the window shows and does, for QML."""

from __future__ import annotations

import bisect
import os
import shutil
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot

from .. import __version__, cache
from ..audio import AUDIO_SUFFIXES, MIDI_SUFFIXES
from . import menu, store
from .engine import Engine
from .options import DEFAULTS, KEYS, TIME_SIGNATURES, merged, title_from
from .sound import Player, Recorder
from .texts import table

STAGES = ["load", "transcribe", "beats", "score"]


def _path(url_or_path: str) -> Path:
    if url_or_path.startswith("file:"):
        return Path(QUrl(url_or_path).toLocalFile())
    return Path(url_or_path).expanduser()


def _musescore() -> str | None:
    for name in ("mscore", "musescore", "mscore4", "MuseScore4", "musescore4", "MuseScore-Studio"):
        found = shutil.which(name)
        if found:
            return found
    return None


class Controller(QObject):
    pageChanged = Signal()
    fileChanged = Signal()
    stagesChanged = Signal()
    progressChanged = Signal()
    resultChanged = Signal()
    optionsChanged = Signal()
    busyChanged = Signal()
    highlightChanged = Signal()
    recentChanged = Signal()
    textsChanged = Signal()
    preferencesChanged = Signal()
    menuChanged = Signal()
    message = Signal(str)
    scrollTo = Signal(int, float, float)  # page, x and y as fractions of it – asks the view to show this place

    def __init__(self, parent=None):
        super().__init__(parent)
        self._prefs = store.load_preferences()
        self._language = self._resolve_language()
        self._texts = table(self._language)
        self.player = Player(self)
        self.player.mode = self._prefs["mode"]
        self.player.volume = float(self._prefs["volume"])
        self.recorder = Recorder(self)
        self.recorder.finished.connect(self.openFile)
        self.recorder.failed.connect(lambda reason: self.message.emit(self.t("rec_short" if reason == "short" else "rec_failed")))
        self.engine = Engine(self)
        self.engine.reply.connect(self._on_reply)

        self._page = "welcome"
        self._source: Path | None = None
        self._key = ""
        self._stages: list[dict] = []
        self._progress = 0.0
        self._progress_started = 0.0
        self._remaining = ""
        self._device = "cpu"
        self._options = dict(DEFAULTS)
        self._busy = False
        self._result: dict = {}
        self._peaks: list = []
        self._duration = 0.0
        self._has_audio = False
        self._job = 0
        self._analysis_job = 0
        self._revision = 0
        self._score_revision = 0
        self._recent = store.load_history()
        self._starts: list[float] = []
        self._ends: list[float] = []
        self._ids: list[str] = []
        self._measure_times: list[float] = []
        self._measure_ids: list[str] = []
        self._note_rects: dict = {}
        self._measure_rects: dict = {}
        self._highlight: list = []
        self._measure_rect: list = []
        self._last_scroll = (-1, -1.0)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(320)
        self._debounce.timeout.connect(self._analyse)
        self.player.positionChanged.connect(self._follow)

    # ── language and texts ─────────────────────────────────────────────────

    def _resolve_language(self) -> str:
        chosen = os.environ.get("MELOGRAPH_LANG") or self._prefs.get("language", "auto")
        if chosen in ("de", "en"):
            return chosen
        for name in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
            value = os.environ.get(name)
            if value:
                return "de" if value.lower().startswith("de") else "en"
        return "en"

    def t(self, key: str, *values) -> str:
        text = self._texts.get(key, key)
        for i, value in enumerate(values, start=1):
            text = text.replace(f"%{i}", str(value))
        return text

    @Property("QVariantMap", notify=textsChanged)
    def tr(self):
        return self._texts

    @Property(str, notify=textsChanged)
    def language(self) -> str:
        return self._language

    @Property(str, constant=True)
    def version(self) -> str:
        return __version__

    # ── preferences ────────────────────────────────────────────────────────

    @Property("QVariantMap", notify=preferencesChanged)
    def preferences(self):
        return self._prefs

    @Slot(str, "QVariant")
    def setPreference(self, name: str, value) -> None:
        if name not in store.PREFERENCES:
            return
        self._prefs[name] = value
        store.save_preferences(self._prefs)
        if name == "language":
            self._language = self._resolve_language()
            self._texts = table(self._language)
            self.textsChanged.emit()
            self.stagesChanged.emit()
        self.preferencesChanged.emit()

    @Slot(int, int, bool)
    def rememberWindow(self, width: int, height: int, maximized: bool) -> None:
        self._prefs.update(windowWidth=width, windowHeight=height, windowMaximized=maximized)
        store.save_preferences(self._prefs)

    @Property(bool, constant=True)
    def gpuAvailable(self) -> bool:
        try:
            import torch

            return bool(torch.cuda.is_available())
        except Exception:
            return False

    @Property(str, constant=True)
    def museScore(self) -> str:
        return _musescore() or ""

    @Property(str, constant=True)
    def soundInfo(self) -> str:
        from ..synth import available, soundfont

        if available() == "fluidsynth":
            return self.t("sound_fluid", soundfont().stem)
        return self.t("sound_simple")

    @Slot(result=str)
    def cacheSize(self) -> str:
        size = cache.size()
        return f"{size / 1e6:.0f} MB" if size >= 1e6 else f"{size / 1e3:.0f} kB"

    @Slot()
    def clearCache(self) -> None:
        cache.clear()
        self.message.emit(self.t("cache_cleared"))

    @Property(bool, constant=True)
    def canAddToMenu(self) -> bool:
        return menu.launcher() is not None

    @Property(bool, notify=menuChanged)
    def inMenu(self) -> bool:
        return menu.installed()

    @Slot(bool)
    def setInMenu(self, wanted: bool) -> None:
        try:
            menu.install() if wanted else menu.remove()
        except OSError:
            self.message.emit(self.t("menu_failed"))
        else:
            self.message.emit(self.t("menu_added" if wanted else "menu_removed"))
        self.menuChanged.emit()

    @Property(str, constant=True)
    def recordFolder(self) -> str:
        return str(store.user_dir("MUSIC", "Music") / "Melograph")

    # ── state for the window ───────────────────────────────────────────────

    @Property(str, notify=pageChanged)
    def page(self) -> str:
        return self._page

    def _set_page(self, page: str) -> None:
        if page != self._page:
            self._page = page
            self.pageChanged.emit()

    @Property(str, notify=fileChanged)
    def fileName(self) -> str:
        return self._source.name if self._source else ""

    @Property(str, notify=fileChanged)
    def filePath(self) -> str:
        return str(self._source) if self._source else ""

    @Property(bool, notify=fileChanged)
    def hasAudio(self) -> bool:
        return self._has_audio

    @Property("QVariantList", notify=stagesChanged)
    def stages(self):
        return [dict(s, label=self.t("stage_" + s["key"])) for s in self._stages]

    @Property(float, notify=progressChanged)
    def progress(self) -> float:
        return self._progress

    @Property(str, notify=progressChanged)
    def remaining(self) -> str:
        return self._remaining

    @Property(str, notify=fileChanged)
    def device(self) -> str:
        return self._device

    @Property("QVariantMap", notify=resultChanged)
    def result(self):
        return self._result

    @Property("QVariantList", notify=fileChanged)
    def peaks(self):
        return self._peaks

    @Property(float, notify=fileChanged)
    def duration(self) -> float:
        return self._duration

    @Property("QVariantMap", notify=optionsChanged)
    def options(self):
        return self._options

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property("QVariantList", notify=highlightChanged)
    def highlight(self):
        return self._highlight

    @Property("QVariantList", notify=highlightChanged)
    def measureRect(self):
        return self._measure_rect

    @Property("QVariantList", notify=recentChanged)
    def recent(self):
        entries = []
        for entry in self._recent:
            thumb = cache.folder(entry.get("key", "")) / "thumb.png" if entry.get("key") else None
            entries.append(dict(
                entry,
                exists=Path(entry["path"]).exists(),
                thumb=QUrl.fromLocalFile(str(thumb)).toString() if thumb and thumb.exists() else "",
            ))
        return entries

    @Property("QVariantList", constant=True)
    def timeSignatures(self):
        return TIME_SIGNATURES

    @Property("QVariantList", constant=True)
    def keys(self):
        return KEYS

    # ── opening ────────────────────────────────────────────────────────────

    @Slot(str)
    def openFile(self, url: str) -> None:
        self._open(_path(url), fresh=False)

    @Slot()
    def listenAgain(self) -> None:
        if self._source:
            self._open(self._source, fresh=True)

    def _open(self, source: Path, fresh: bool) -> None:
        if not source.is_file() or source.suffix.lower() not in AUDIO_SUFFIXES | MIDI_SUFFIXES:
            self.message.emit(self.t("err_format"))
            return
        self.player.clear()
        self._source = source
        self._has_audio = source.suffix.lower() in AUDIO_SUFFIXES
        self._peaks, self._duration, self._result = [], 0.0, {}
        self._key = ""
        self._options = dict(DEFAULTS)
        self._stages = [{"key": key, "state": "pending", "detail": ""} for key in STAGES]
        self._progress, self._remaining = 0.0, ""
        self._clear_timing()
        self.fileChanged.emit()
        self.resultChanged.emit()
        self.optionsChanged.emit()
        self.stagesChanged.emit()
        self.progressChanged.emit()
        self._set_page("working")
        self._job = self.engine.send("hear", path=str(source), device=self._prefs["device"], fresh=fresh)
        if self._has_audio:
            self.player.load_original(str(source))

    @Slot()
    def cancel(self) -> None:
        self.engine.restart()
        self.player.clear()
        self._source = None
        self.fileChanged.emit()
        self._set_page("welcome")

    @Slot()
    def goHome(self) -> None:
        self.player.pause()
        self._set_page("welcome")

    @Slot(str)
    def forget(self, path: str) -> None:
        self._recent = store.forget(path)
        self.recentChanged.emit()

    # ── notation settings ──────────────────────────────────────────────────

    @Slot(str, "QVariant")
    def setOption(self, name: str, value) -> None:
        if name not in DEFAULTS or self._options.get(name) == value:
            return
        self._options[name] = value
        self.optionsChanged.emit()
        self._busy = True
        self.busyChanged.emit()
        self._debounce.start()

    @Slot()
    def resetOptions(self) -> None:
        title, composer = self._options.get("title", ""), self._options.get("composer", "")
        self._options = dict(DEFAULTS, title=title, composer=composer)
        self.optionsChanged.emit()
        self._busy = True
        self.busyChanged.emit()
        self._debounce.start()

    def _analyse(self, thumbnail: bool = False) -> None:
        if not self._key:
            return
        self._analysis_job = self.engine.send("analyse", options=self._options, thumbnail=thumbnail)
        self._busy = True
        self.busyChanged.emit()

    # ── replies from the engine ────────────────────────────────────────────

    def _stage(self, key: str, state: str, detail: str = "") -> None:
        for stage in self._stages:
            if stage["key"] == key:
                stage["state"], stage["detail"] = state, detail or stage["detail"]
            elif state == "active" and stage["state"] == "active":
                stage["state"] = "done"
        self.stagesChanged.emit()

    def _on_reply(self, reply: dict) -> None:
        kind = reply.get("type")
        if kind == "stage":
            stage = reply["stage"]
            if stage == "cache":
                self._stages = [{"key": "cache", "state": "done", "detail": ""}, {"key": "score", "state": "pending", "detail": ""}]
                self.stagesChanged.emit()
            else:
                self._stage(stage, "active", self.t("first_download") if reply.get("download") else "")
                self._progress, self._remaining = 0.0, ""
                self._progress_started = time.monotonic()
                self.progressChanged.emit()
        elif kind == "loaded":
            self._peaks, self._duration = reply["peaks"], reply["duration"]
            self.fileChanged.emit()
        elif kind == "progress":
            done, total = reply["done"], max(1, reply["total"])
            self._progress = done / total
            elapsed = time.monotonic() - self._progress_started
            if done >= 2 and self._progress < 1:
                left = elapsed / self._progress * (1 - self._progress)
                self._remaining = self.t("remaining", _duration_text(left))
            self.progressChanged.emit()
        elif kind == "heard":
            self._key = reply["key"]
            self._device = reply.get("device", "cpu")
            if reply.get("peaks"):
                self._peaks = reply["peaks"]
            self._duration = self._duration or reply["duration"]
            settings = reply.get("settings") or {}
            self._options = merged(settings)
            if not self._options.get("title") and self._source:
                self._options["title"] = title_from(self._source)
            self.fileChanged.emit()
            self.optionsChanged.emit()
            for stage in self._stages:
                if stage["key"] != "score":
                    stage["state"] = "done"
            self._stage("score", "active")
            self._analyse(thumbnail=True)
        elif kind == "analysed":
            if reply["id"] != self._analysis_job:
                return
            self._take_result(reply)
        elif kind == "synthesized":
            if reply["revision"] == self._revision:
                self._score_revision = reply["revision"]
                self.player.load_score(reply["path"])
        elif kind == "exported":
            name = Path(reply["path"]).name
            self.message.emit(self.t("exported", name))
            if reply["format"] == "musicxml" and self._prefs.get("openAfterExport") and _musescore():
                self._launch(reply["path"])
        elif kind == "error":
            self._on_error(reply)

    def _on_error(self, reply: dict) -> None:
        text = reply.get("message", "")
        if reply.get("trace"):
            print(reply["trace"])
        if text == "no_notes":
            self.message.emit(self.t("err_no_notes"))
            self._set_page("welcome")
            return
        self.message.emit(self.t("err_generic", text))
        if self._page == "working":
            self._set_page("welcome")
        self._busy = False
        self.busyChanged.emit()

    def _take_result(self, reply: dict) -> None:
        self._revision = reply["revision"]
        summary = reply["summary"]
        pages = [QUrl.fromLocalFile(p).toString() for p in reply["pages"]]
        self._result = {
            "summary": summary, "pages": pages, "size": reply["size"], "roll": reply["roll"],
            "bars": reply["bars"], "beats": reply["beats"], "revision": self._revision,
        }
        rects = reply["rects"]
        self._note_rects = rects["notes"]
        self._measure_rects = rects["measures"]
        self._set_timing(reply["events"], reply["measures"])
        self._busy = False
        self.busyChanged.emit()
        self.resultChanged.emit()
        self.player.clear_score()
        self.engine.send("synth")
        if self._page == "working":
            self._stage("score", "done")
            self._set_page("score")
            self._recent = store.remember({
                "path": str(self._source), "key": self._key, "title": self._options.get("title") or self.fileName,
                "meter": summary["meter"], "keyDe": summary["keyDe"], "keyEn": summary["keyEn"],
                "bars": summary["bars"], "duration": self._duration,
            })
            self.recentChanged.emit()

    # ── playback position in the score ─────────────────────────────────────

    def _clear_timing(self) -> None:
        self._starts, self._ends, self._ids = [], [], []
        self._measure_times, self._measure_ids = [], []
        self._note_rects, self._measure_rects = {}, {}
        self._highlight, self._measure_rect = [], []
        self.highlightChanged.emit()

    def _set_timing(self, events: list, measures: list) -> None:
        begun: dict[str, float] = {}
        spans: list[tuple[float, float, str]] = []
        for seconds, on, off in events:
            for ident in off:
                if ident in begun:
                    spans.append((begun.pop(ident), seconds, ident))
            for ident in on:
                begun[ident] = seconds
        for ident, seconds in begun.items():
            spans.append((seconds, seconds + 1.0, ident))
        spans.sort()
        self._starts = [s for s, _, _ in spans]
        self._ends = [e for _, e, _ in spans]
        self._ids = [i for _, _, i in spans]
        self._measure_times = [m[0] for m in measures]
        self._measure_ids = [m[1] for m in measures]
        self._last_scroll = (-1, -1.0)
        self._follow()

    def _follow(self) -> None:
        if not self._starts:
            return
        now = self.player.position
        upto = bisect.bisect_right(self._starts, now)
        sounding = [
            self._note_rects[self._ids[i]]
            for i in range(max(0, upto - 64), upto)
            if self._ends[i] > now and self._ids[i] in self._note_rects
        ]
        index = bisect.bisect_right(self._measure_times, now) - 1
        measure = self._measure_rects.get(self._measure_ids[index], []) if index >= 0 else []
        if sounding != self._highlight or measure != self._measure_rect:
            self._highlight, self._measure_rect = sounding, measure
            self.highlightChanged.emit()
        if measure and self.player.playing and self._prefs.get("follow", True):
            place = (measure[0], round(measure[1], 3), round(measure[2], 3))
            if place != self._last_scroll:
                self._last_scroll = place
                self.scrollTo.emit(int(measure[0]), float(measure[1] + measure[3] / 2), float(measure[2]))

    @Slot(int, float, float)
    def seekAt(self, page: int, x: float, y: float) -> None:
        """A click on the score: go to the bar (and the note) under the pointer."""
        best = None
        for ident, rect in self._measure_rects.items():
            if rect[0] == page and rect[1] <= x <= rect[1] + rect[3] and rect[2] - 0.01 <= y <= rect[2] + rect[4] + 0.01:
                best = ident
                break
        if best is None:
            return
        start = self._measure_times[self._measure_ids.index(best)]
        band = self._measure_rects[best]
        candidates = [
            (abs(rect[1] - x), self._starts[i])
            for i, ident in enumerate(self._ids)
            if (rect := self._note_rects.get(ident)) and rect[0] == page
            and band[1] <= rect[1] <= band[1] + band[3] and band[2] - 0.02 <= rect[2] <= band[2] + band[4]
        ]
        if candidates:
            start = min(candidates)[1]
        self.player.seek(max(0.0, start - 0.02))

    # ── export ─────────────────────────────────────────────────────────────

    @Slot(str, result=str)
    def suggestedFile(self, extension: str) -> str:
        folder = Path(self._prefs.get("exportFolder") or (self._source.parent if self._source else Path.home()))
        name = (self._options.get("title") or (self._source.stem if self._source else "Melograph")).strip() or "Melograph"
        for bad in '/\\:*?"<>|':
            name = name.replace(bad, "-")
        return QUrl.fromLocalFile(str(folder / f"{name}.{extension}")).toString()

    @Slot(str, str)
    def export(self, kind: str, url: str) -> None:
        path = _path(url)
        self._prefs["exportFolder"] = str(path.parent)
        store.save_preferences(self._prefs)
        self.engine.send("export", format=kind, path=str(path))

    @Slot()
    def openInMuseScore(self) -> None:
        if not self._key:
            return
        path = cache.folder(self._key) / f"{(self._options.get('title') or 'Melograph').strip() or 'Melograph'}.musicxml"
        for bad in '/\\:*?"<>|':
            path = path.with_name(path.name.replace(bad, "-"))
        self.engine.send("export", format="musicxml", path=str(path))
        self._launch(str(path), wait_for_file=True)

    def _launch(self, path: str, wait_for_file: bool = False) -> None:
        program = _musescore()
        if not program:
            subprocess.Popen(["xdg-open", path], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return

        def go(tries=0):
            if wait_for_file and not Path(path).exists() and tries < 40:
                QTimer.singleShot(100, lambda: go(tries + 1))
                return
            subprocess.Popen([program, path], start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.message.emit(self.t("musescore_opened"))

        go()

    # ── leaving ────────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        self.player.stop_device()
        self.recorder.cancel()
        self.engine.stop()


def _duration_text(seconds: float) -> str:
    seconds = max(1, int(round(seconds)))
    if seconds < 60:
        return f"{seconds} s"
    return f"{seconds // 60}:{seconds % 60:02d} min"
