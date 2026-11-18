"""The engraved pages of a recording as PNG files – for looking at what the engine writes, without the window.

    .venv/bin/python tools/pages.py recording.mp3 [folder] [--width 900]

Uses what Melograph remembers of the recording (it is transcribed first if it is
new), prints the sections it found – bars, time signatures, keys, tempos – and
writes page-01.png, page-02.png … and score.musicxml into the folder.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> int:
    arguments = [a for a in sys.argv[1:] if not a.startswith("--")]
    source = Path(arguments[0]).resolve()
    out = Path(arguments[1] if len(arguments) > 1 else "pages").resolve()
    width = next((int(sys.argv[i + 1]) for i, a in enumerate(sys.argv[:-1]) if a == "--width"), 900)
    out.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import QByteArray, QRectF, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    from melograph import cache
    from melograph.audio import MIDI_SUFFIXES, load_audio
    from melograph.export import musicxml_text
    from melograph.gui.options import title_from
    from melograph.pipeline import Options, analyse
    from melograph.render import engrave, register_fonts

    key = cache.fingerprint(source)
    remembered = cache.load(key)
    if source.suffix.lower() in MIDI_SUFFIXES:
        from melograph.transcribe import read_midi

        performance, tracked = read_midi(source), None
    elif remembered is not None and remembered[1] is not None:
        performance, tracked = remembered
    else:
        from melograph.beats import track_audio
        from melograph.transcribe import pick_device, transcribe

        audio = load_audio(source)
        device = pick_device("auto")
        performance = remembered[0] if remembered else transcribe(audio, device)
        tracked = track_audio(audio, 44100, device)
        cache.save(key, source, performance, tracked, cache.waveform_peaks(audio))

    result = analyse(performance, None, None, Options(title=title_from(source)), tracked)
    layout = result.layout
    sections: list[list] = []
    for index, (meter, k) in enumerate(zip(layout.meters, result.keys)):
        tag = f"{meter} {k.label('en')}"
        if sections and sections[-1][0] == tag:
            sections[-1][2] = index + 1
        else:
            sections.append([tag, index + 1, index + 1])
    print(f"{len(layout.bars)} bars")
    for tag, first, last in sections:
        print(f"  bars {first}–{last}: {tag}")
    print("  tempo: " + ", ".join(
        f"bar {layout.bar_of(m.pos) + 1} {m.text or round(m.bpm)}" for m in result.marks.tempos
    ))

    xml = musicxml_text(result.score)
    (out / "score.musicxml").write_text(xml, encoding="utf-8")
    app = QGuiApplication(["melograph-pages"])
    register_fonts()
    engraving = engrave(xml, layout.seconds_of_quarter(result.grid))
    for old in out.glob("page-*.png"):
        old.unlink()
    height = round(width * engraving.page_size[1] / engraving.page_size[0])
    for number, svg in enumerate(engraving.pages, start=1):
        image = QImage(width, height, QImage.Format_RGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(painter, QRectF(0, 0, width, height))
        painter.end()
        image.save(str(out / f"page-{number:02d}.png"))
    print(f"{len(engraving.pages)} pages in {out}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
