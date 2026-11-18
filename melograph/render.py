"""Engraving for the screen and for PDF, with Verovio.

Verovio lays out the MusicXML as pages of SVG.  Qt's SVG renderer understands
only SVG Tiny, so the pages are simplified for it: the nested <svg> that holds
the scale becomes a group, nested text spans are flattened, and the SMuFL font
that Verovio embeds as CSS is handed to Qt separately (see `music_font`).
"""

from __future__ import annotations

import base64
import json
import locale
import re
from dataclasses import dataclass, field
from pathlib import Path

FONT = "Leland"  # the music font of MuseScore 4, so the preview looks like the score there
# Verovio also takes symbols inside text (the flat of a chord symbol) from Leipzig.
MUSIC_FONTS = ("Leland", "Leipzig", "Bravura", "Gootville", "Petaluma")

PAGE_WIDTH = 2100  # A4 in tenths of a millimetre
PAGE_HEIGHT = 2970


def c_numbers() -> None:
    """Numbers with a decimal point for Verovio, whatever the language of the desktop.

    Verovio writes its SVG and MEI with printf. Qt switches the process to the
    desktop's locale when it starts, and with a German LC_NUMERIC "scale(0.72)"
    became "scale(0,72)": every symbol was then drawn at the wrong size.
    """
    locale.setlocale(locale.LC_NUMERIC, "C")


def music_font(name: str = FONT) -> bytes:
    """A SMuFL font Verovio uses for symbols inside text (tempo marks, chord symbols), as WOFF2."""
    import verovio

    css = (Path(verovio.__file__).parent / "data" / f"{name}.css").read_text()
    return base64.b64decode(re.search(r"base64,([A-Za-z0-9+/=]+)", css).group(1))


def register_fonts() -> None:
    """Hand the music fonts to Qt (needs a running QGuiApplication)."""
    from PySide6.QtGui import QFontDatabase

    for name in ("Leland", "Leipzig"):
        QFontDatabase.addApplicationFontFromData(music_font(name))


def for_qt(svg: str) -> str:
    """Rewrite a Verovio page so that QtSvg draws all of it."""
    root = re.search(r'<svg[^>]*?width="([\d.]+)px" height="([\d.]+)px"', svg)
    inner = re.search(r'<svg class="definition-scale"([^>]*?)viewBox="0 0 ([\d.]+) ([\d.]+)"\s*>', svg)
    if root and inner:
        sx = float(root.group(1)) / float(inner.group(2))
        sy = float(root.group(2)) / float(inner.group(3))
        svg = (
            svg[:inner.start()]
            + f'<g class="definition-scale"{inner.group(1)}transform="scale({sx:.6f},{sy:.6f})">'
            + svg[inner.end():]
        )
        last = svg.rfind("</svg>")
        closing = svg.rfind("</svg>", 0, last)
        if closing > 0:
            svg = svg[:closing] + "</g>" + svg[closing + 6:]
    # Embedded fonts are given to Qt directly; the CSS would only be ignored.
    svg = re.sub(r"<style[^>]*>\s*@font-face.*?</style>", "", svg, flags=re.S)
    return re.sub(r"<text\b([^>]*)>(.*?)</text>", _flat_text, svg, flags=re.S)


_STYLE = ("font-family", "font-size", "font-style", "font-weight", "fill")
_PLACE = ("x", "y", "text-anchor")


def _attributes(text: str) -> dict[str, str]:
    return dict(re.findall(r'([\w:-]+)="([^"]*)"', text))


def _flat_text(match: re.Match) -> str:
    """<text> with nested <tspan>s → <text> with one level of spans.

    Verovio puts the position and the anchor on outer spans and the font size on
    the innermost one; every leaf now gets the style it inherits, and the
    position moves up to the <text> element.
    """
    outer = _attributes(match.group(1))
    body = re.sub(r"<title\b.*?</title>", "", match.group(2), flags=re.S)
    stack: list[dict[str, str]] = [outer]
    place = {k: outer[k] for k in _PLACE if k in outer}
    leaves: list[tuple[dict[str, str], str]] = []
    for token in re.finditer(r"<tspan\b([^>]*?)(/?)>|</tspan>|([^<]+)", body):
        if token.group(0).startswith("<tspan"):
            attrs = _attributes(token.group(1))
            for key in _PLACE:
                if key in attrs and key not in place:
                    place[key] = attrs[key]
            if not token.group(2):
                stack.append(attrs)
        elif token.group(0) == "</tspan>":
            if len(stack) > 1:
                stack.pop()
        else:
            text = token.group(3)
            if not text.strip():  # indentation between the tags
                continue
            style: dict[str, str] = {}
            for level in stack:
                style.update({k: v for k, v in level.items() if k in _STYLE and v != "0px"})
            leaves.append((style, text))
    if not leaves:
        return ""
    # A note symbol in a tempo mark comes at the size of a note in the staff; next to
    # text it should be about as tall as the letters.
    words = [s["font-size"] for s, _ in leaves if "font-size" in s and s.get("font-family") not in MUSIC_FONTS]
    if words:
        text_size = float(words[0].rstrip("px"))
        for style, _ in leaves:
            if style.get("font-family") in MUSIC_FONTS:
                style["font-size"] = f"{text_size * 1.15:.0f}px"
    size = next((s["font-size"] for s, _ in leaves if "font-size" in s), None)
    spans = "".join("<tspan " + " ".join(f'{k}="{v}"' for k, v in s.items()) + f">{t}</tspan>" for s, t in leaves)
    head = {k: v for k, v in outer.items() if k not in _PLACE and k != "font-size"}
    head.update(place)
    if size is not None:
        head["font-size"] = size
    return "<text " + " ".join(f'{k}="{v}"' for k, v in head.items()) + ">" + spans + "</text>"


@dataclass
class Engraving:
    """The rendered score and where things are in it."""

    pages: list[str]  # SVG per page, ready for QtSvg
    page_size: tuple[float, float]  # width, height of a page in SVG units
    # Playback: (seconds, ids of notes that start, ids of notes that end), in order.
    events: list[tuple[float, list[str], list[str]]] = field(default_factory=list)
    measures: list[tuple[float, str, int]] = field(default_factory=list)  # (start in seconds, id, page index)
    note_pages: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "pages": len(self.pages), "size": self.page_size, "events": self.events,
            "measures": self.measures, "notePages": self.note_pages,
        })


def write_pdf(pages: list[str], path: Path, title: str = "") -> None:
    """Engraved A4 pages (from `engrave`) as a PDF. Needs a running QGuiApplication."""
    from PySide6.QtCore import QByteArray, QMarginsF, QRectF
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
    from PySide6.QtSvg import QSvgRenderer

    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter)
    writer.setResolution(300)
    writer.setTitle(title or "Melograph")
    writer.setCreator("Melograph")
    painter = QPainter(writer)
    painter.setRenderHint(QPainter.Antialiasing)
    target = QRectF(0, 0, writer.width(), writer.height())
    for index, svg in enumerate(pages):
        if index:
            writer.newPage()
        QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(painter, target)
    painter.end()


def engrave(musicxml: str, seconds_of_quarter, scale: int = 40, landscape: bool = False) -> Engraving:
    """Lay out the score. `seconds_of_quarter(q)` maps a score position in quarters to the recording."""
    import verovio

    c_numbers()
    verovio.enableLog(verovio.LOG_ERROR)  # its notes about spanners it lays out differently are no use here
    toolkit = verovio.toolkit()
    width, height = (PAGE_HEIGHT, PAGE_WIDTH) if landscape else (PAGE_WIDTH, PAGE_HEIGHT)
    toolkit.setOptions({
        "pageWidth": width, "pageHeight": height, "scale": scale,
        "pageMarginLeft": 100, "pageMarginRight": 100, "pageMarginTop": 80, "pageMarginBottom": 80,
        "adjustPageHeight": False, "breaks": "auto", "footer": "none", "header": "auto",
        "font": FONT, "spacingSystem": 14, "spacingStaff": 10, "justifyVertically": False,
        "xmlIdSeed": 1,
    })
    if not toolkit.loadData(musicxml):
        raise RuntimeError("verovio")
    pages = [for_qt(toolkit.renderToSVG(page)) for page in range(1, toolkit.getPageCount() + 1)]
    size = (width * scale / 100 * 0.4, height * scale / 100 * 0.4)
    first = re.search(r'width="([\d.]+)px" height="([\d.]+)px"', pages[0])
    if first:
        size = (float(first.group(1)), float(first.group(2)))

    events: list[tuple[float, list[str], list[str]]] = []
    measures: list[tuple[float, str, int]] = []
    note_pages: dict[str, int] = {}
    seen_measures: set[str] = set()
    for entry in toolkit.renderToTimemap({"includeMeasures": True, "includeRests": False}):
        seconds = float(seconds_of_quarter(float(entry.get("qstamp", 0.0))))
        on, off = list(entry.get("on", [])), list(entry.get("off", []))
        if on or off:
            events.append((seconds, on, off))
        measure = entry.get("measureOn")
        if measure and measure not in seen_measures:
            seen_measures.add(measure)
            measures.append((seconds, measure, toolkit.getPageWithElement(measure) - 1))
        for note in on:
            note_pages[note] = toolkit.getPageWithElement(note) - 1
    return Engraving(pages, size, events, measures, note_pages)
