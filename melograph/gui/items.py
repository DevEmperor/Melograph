"""Two views drawn in Python: the waveform of the recording and the piano roll of what was heard."""

from __future__ import annotations

from PySide6.QtCore import Property, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtQuick import QQuickPaintedItem

BLACK_KEYS = {1, 3, 6, 8, 10}


def _color_property(name: str):
    signal_name = f"{name}Changed"

    def getter(self):
        return getattr(self, f"_{name}")

    def setter(self, value):
        value = QColor(value)
        if value != getattr(self, f"_{name}"):
            setattr(self, f"_{name}", value)
            getattr(self, signal_name).emit()
            self.update()

    return getter, setter


class Waveform(QQuickPaintedItem):
    """Loudness over time, with the part already played in the accent colour."""

    peaksChanged = Signal()
    positionChanged = Signal()
    durationChanged = Signal()
    barsChanged = Signal()
    colorChanged = Signal()
    playedColorChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAntialiasing(True)
        self._peaks: list[float] = []
        self._position = 0.0
        self._duration = 0.0
        self._bars: list[float] = []
        self._color = QColor("#5a525c")
        self._playedColor = QColor("#e5484d")

    def _set_peaks(self, value):
        self._peaks = list(value or [])
        self.peaksChanged.emit()
        self.update()

    peaks = Property("QVariantList", lambda self: self._peaks, _set_peaks, notify=peaksChanged)

    def _set_position(self, value):
        if abs(value - self._position) > 1e-4:
            self._position = value
            self.positionChanged.emit()
            self.update()

    position = Property(float, lambda self: self._position, _set_position, notify=positionChanged)

    def _set_duration(self, value):
        self._duration = value
        self.durationChanged.emit()
        self.update()

    duration = Property(float, lambda self: self._duration, _set_duration, notify=durationChanged)

    def _set_bars(self, value):
        self._bars = list(value or [])
        self.barsChanged.emit()
        self.update()

    bars = Property("QVariantList", lambda self: self._bars, _set_bars, notify=barsChanged)
    color = Property(QColor, *_color_property("color"), notify=colorChanged)
    playedColor = Property(QColor, *_color_property("playedColor"), notify=playedColorChanged)

    def paint(self, painter: QPainter):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0 or not self._peaks:
            return
        mid = h / 2
        step = 3.0
        columns = int(w / step)
        played_x = (self._position / self._duration * w) if self._duration > 0 else 0
        n = len(self._peaks)
        painter.setPen(Qt.NoPen)
        for c in range(columns):
            a = int(c * n / columns)
            b = max(a + 1, int((c + 1) * n / columns))
            value = max(self._peaks[a:b])
            height = max(1.5, value * (h - 4))
            x = c * step
            painter.setBrush(self._playedColor if x < played_x else self._color)
            painter.drawRoundedRect(QRectF(x, mid - height / 2, step - 1.2, height), 1, 1)
        if self._duration > 0 and self._bars:
            pen = QPen(QColor(self._color.red(), self._color.green(), self._color.blue(), 90))
            pen.setWidthF(1)
            painter.setPen(pen)
            for t in self._bars:
                x = t / self._duration * w
                painter.drawLine(QPointF(x, h - 3), QPointF(x, h))


class PianoRoll(QQuickPaintedItem):
    """The played notes on a keyboard grid: right hand red, left hand blue, bars as lines."""

    notesChanged = Signal()
    barsChanged = Signal()
    positionChanged = Signal()
    viewChanged = Signal()
    themeChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAntialiasing(True)
        self._notes: list = []
        self._bars: list[float] = []
        self._position = 0.0
        self._start = 0.0
        self._span = 10.0
        self._dark = True
        self._low, self._high = 36, 96

    def _set_notes(self, value):
        self._notes = list(value or [])
        if self._notes:
            pitches = [n[2] for n in self._notes]
            self._low = max(21, min(pitches) - 3)
            self._high = min(108, max(pitches) + 3)
        self.notesChanged.emit()
        self.update()

    notes = Property("QVariantList", lambda self: self._notes, _set_notes, notify=notesChanged)

    def _set_bars(self, value):
        self._bars = list(value or [])
        self.barsChanged.emit()
        self.update()

    bars = Property("QVariantList", lambda self: self._bars, _set_bars, notify=barsChanged)

    def _set_position(self, value):
        if abs(value - self._position) > 1e-4:
            self._position = value
            self.positionChanged.emit()
            self.update()

    position = Property(float, lambda self: self._position, _set_position, notify=positionChanged)

    def _set_start(self, value):
        self._start = value
        self.viewChanged.emit()
        self.update()

    viewStart = Property(float, lambda self: self._start, _set_start, notify=viewChanged)

    def _set_span(self, value):
        self._span = max(1.0, value)
        self.viewChanged.emit()
        self.update()

    viewSpan = Property(float, lambda self: self._span, _set_span, notify=viewChanged)

    def _set_dark(self, value):
        self._dark = bool(value)
        self.themeChanged.emit()
        self.update()

    dark = Property(bool, lambda self: self._dark, _set_dark, notify=themeChanged)

    def paint(self, painter: QPainter):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        keys = 34.0
        rows = self._high - self._low + 1
        row = h / rows
        scale = (w - keys) / self._span

        def x_of(t: float) -> float:
            return keys + (t - self._start) * scale

        def y_of(pitch: int) -> float:
            return (self._high - pitch) * row

        lane = QColor(255, 255, 255, 9) if self._dark else QColor(0, 0, 0, 10)
        painter.setPen(Qt.NoPen)
        for pitch in range(self._low, self._high + 1):
            if pitch % 12 in BLACK_KEYS:
                painter.fillRect(QRectF(keys, y_of(pitch), w - keys, row), lane)
        line = QColor(255, 255, 255, 40) if self._dark else QColor(0, 0, 0, 45)
        painter.setPen(QPen(line, 1))
        for t in self._bars:
            if self._start <= t <= self._start + self._span:
                painter.drawLine(QPointF(x_of(t), 0), QPointF(x_of(t), h))

        right, left = QColor("#e5484d"), QColor("#5b9bd5")
        for on, off, pitch, hand, velocity in self._notes:
            if off < self._start or on > self._start + self._span:
                continue
            color = QColor(right if hand == 0 else left)
            color.setAlphaF(0.45 + 0.55 * min(1.0, velocity / 110))
            rect = QRectF(x_of(on), y_of(pitch) + 0.5, max(2.0, (off - on) * scale - 1), max(2.0, row - 1))
            path = QPainterPath()
            path.addRoundedRect(rect, min(3.0, row / 2), min(3.0, row / 2))
            painter.fillPath(path, color)

        # A small keyboard on the left, with C marked.
        painter.fillRect(QRectF(0, 0, keys, h), QColor("#16131a") if self._dark else QColor("#f1edee"))
        font = QFont()
        font.setPixelSize(max(7, min(10, int(row * 0.9))))
        painter.setFont(font)
        for pitch in range(self._low, self._high + 1):
            y = y_of(pitch)
            if pitch % 12 in BLACK_KEYS:
                painter.fillRect(QRectF(0, y, keys * 0.6, row), QColor("#000000") if self._dark else QColor("#3a3540"))
            if pitch % 12 == 0:
                painter.setPen(QColor("#8d868f"))
                painter.drawText(QRectF(2, y - 1, keys - 4, row + 2), Qt.AlignRight | Qt.AlignVCenter, f"C{pitch // 12 - 1}")
        pen = QPen(QColor("#e5484d"), 1.6)
        painter.setPen(pen)
        x = x_of(self._position)
        if keys <= x <= w:
            painter.drawLine(QPointF(x, 0), QPointF(x, h))
