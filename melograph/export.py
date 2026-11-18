"""Write the laid-out piece as MusicXML (through music21)."""

from __future__ import annotations

import re
from pathlib import Path

from .engrave import Atom, Layout
from .marks import Marks, nice_tempo
from .model import LEFT, RIGHT, Note, Performance
from .spelling import Key

PEDAL_STYLES = ("lines", "signs", "text", "off")


def _pitch_name(n: Note) -> str:
    accidental = "#" * n.alter if n.alter > 0 else "-" * -n.alter
    return f"{n.step}{accidental}{n.octave + n.shift}"


def build_score(
    layout: Layout,
    keys: Key | list[Key],
    bpm: float,
    title: str,
    performance: Performance,
    marks: Marks | None = None,
    pedal: str = "lines",
    composer: str = "",
):
    """The score as a music21 stream. `keys` is one key, or the key of every bar of the layout."""
    from music21 import (
        articulations, bar as m21bar, chord, clef, duration, dynamics as m21dynamics, expressions, harmony,
        instrument, key as m21key, layout as m21layout, metadata, meter as m21meter, note, spanner, stream, tempo,
        tie,
    )

    marks = marks or Marks()
    if isinstance(keys, Key):
        keys = [keys] * len(layout.bars)
    score = stream.Score()
    score.metadata = metadata.Metadata()
    score.metadata.title = title
    score.metadata.composer = composer or " "
    first_element: dict[int, object] = {}  # id(note) → the first symbol written for it
    last_element: dict[int, object] = {}

    def element(atom: Atom):
        if not atom.notes:
            obj = note.Rest()
            if atom.hidden:
                obj.style.hideObjectOnPrint = True
        elif len(atom.notes) == 1:
            obj = note.Note(_pitch_name(atom.notes[0]))
        else:
            obj = chord.Chord([_pitch_name(n) for n in atom.notes])
        if atom.whole_bar:
            obj.duration = duration.Duration(float(atom.length) if atom.length.denominator > 64 else atom.length)
            obj.fullMeasure = True
            return obj
        d = duration.Duration(type=atom.kind, dots=atom.dots)
        if atom.tuplet:
            t = duration.Tuplet(3, 2, atom.tuplet_unit)
            t.type = atom.tuplet if atom.tuplet in ("start", "stop") else None
            d.appendTuplet(t)
        obj.duration = d
        if atom.notes:
            if atom.tie_in and atom.tie_out:
                obj.tie = tie.Tie("continue")
            elif atom.tie_out:
                obj.tie = tie.Tie("start")
            elif atom.tie_in:
                obj.tie = tie.Tie("stop")
            for n in atom.notes:
                if atom.first:
                    first_element.setdefault(id(n), obj)
                last_element[id(n)] = obj
            if atom.first:
                if all(n.staccato for n in atom.notes):
                    obj.articulations.append(articulations.Staccato())
                if any(n.accent for n in atom.notes):
                    obj.articulations.append(articulations.Accent())
                if any(n.trill for n in atom.notes):
                    obj.expressions.append(expressions.Trill())
                if len(atom.notes) > 1 and sum(1 for n in atom.notes if n.roll) >= 2:
                    obj.expressions.append(expressions.ArpeggioMark("normal"))
            if not atom.tie_out and any(n.fermata for n in atom.notes):
                obj.expressions.append(expressions.Fermata())
        return obj

    def clef_for(sign: str):
        return clef.TrebleClef() if sign == "G" else clef.BassClef()

    plan = marks.clefs or {
        RIGHT: ["G"] * len(layout.bars),
        LEFT: ["F"] * len(layout.bars),
    }

    # "con pedale" goes where the pedal is first used in earnest (only if no pedal marks are written).
    pedal_bar = None
    pedals = [p for p in performance.pedals if p.end - p.start > 0.15]
    if pedal == "text" and len(pedals) >= 3:
        for index, bar in enumerate(layout.bars):
            times = [n.onset for staff in bar.staves for voice in staff for atom in voice for n in atom.notes]
            if times and max(times) >= pedals[0].start:
                pedal_bar = index
                break

    # Things that stand at a position in a bar rather than on a note.
    placed: dict[tuple[int, int], list[tuple[object, object]]] = {}  # (hand, bar) → [(offset, object)]

    def place(hand: int, pos, obj) -> object:
        index, offset = layout.locate(pos)
        placed.setdefault((hand, index), []).append((offset, obj))
        return obj

    for pos, text in marks.dynamics:
        place(RIGHT, pos, m21dynamics.Dynamic(text))
    for pin in marks.hairpins:
        if pin.words:
            words = expressions.TextExpression("cresc." if pin.crescendo else "dim.")
            words.placement = "below"
            words.style.fontStyle = "italic"
            place(RIGHT, pin.start, words)
    initial_bpm = bpm
    for mark in marks.tempos:
        if mark.bpm is not None and mark is marks.tempos[0]:
            initial_bpm = mark.bpm
            continue
        if mark.bpm is not None:
            place(RIGHT, mark.pos, _metronome(tempo, duration, layout.meters[layout.bar_of(mark.pos)], mark.bpm))
        elif mark.text:
            words = expressions.TextExpression(mark.text)
            words.placement = "above"
            words.style.fontStyle = "italic"
            place(RIGHT, mark.pos, words)
    for name in marks.chords:
        try:
            symbol = harmony.ChordSymbol(name.figure)
        except Exception:
            continue
        symbol.writeAsChord = False
        place(RIGHT, name.pos, symbol)
    if marks.swing:
        words = expressions.TextExpression("Swing")
        words.placement = "above"
        words.style.fontWeight = "bold"
        place(RIGHT, layout.origin, words)
    # A new section – another key, another metre, another tempo – begins after a double bar line.
    sections = {
        index for index in range(1, len(layout.bars))
        if keys[index].fifths != keys[index - 1].fifths
        or (layout.meters[index].numerator, layout.meters[index].denominator)
        != (layout.meters[index - 1].numerator, layout.meters[index - 1].denominator)
    }
    for mark in marks.tempos[1:]:
        index, offset = layout.locate(mark.pos)
        if mark.bpm is not None and offset == 0:
            sections.add(index)

    staves = []
    first_voices: dict[tuple[int, int], object] = {}  # (hand, bar) → the voice that carries the marks
    for hand in (RIGHT, LEFT):
        part = stream.PartStaff(id="RH" if hand == RIGHT else "LH")
        if hand == RIGHT:
            part.insert(0, instrument.Piano())
        previous = None
        for index, bar in enumerate(layout.bars):
            measure = stream.Measure(number=bar.number)
            meter = layout.meters[index]
            if index == 0:
                measure.insert(0, clef_for(plan[hand][0]))
                measure.insert(0, m21key.KeySignature(keys[0].fifths))
                measure.insert(0, m21meter.TimeSignature(str(meter)))
                if hand == RIGHT:
                    measure.insert(0, _metronome(tempo, duration, meter, initial_bpm))
                if bar.length < meter.bar_ql:
                    measure.paddingLeft = float(meter.bar_ql - bar.length)
            else:
                if plan[hand][index] != plan[hand][index - 1]:
                    measure.insert(0, clef_for(plan[hand][index]))
                if keys[index].fifths != keys[index - 1].fifths:
                    measure.insert(0, m21key.KeySignature(keys[index].fifths))
                before = layout.meters[index - 1]
                if (meter.numerator, meter.denominator) != (before.numerator, before.denominator):
                    measure.insert(0, m21meter.TimeSignature(str(meter)))
                if index in sections:
                    previous.rightBarline = m21bar.Barline("double")
            if index == len(layout.bars) - 1:
                measure.rightBarline = m21bar.Barline("final")
            previous = measure
            if hand == LEFT and index == pedal_bar:
                text = expressions.TextExpression("con pedale")
                text.placement = "below"
                text.style.fontStyle = "italic"
                measure.insert(0, text)
            # Voices 1–2 belong to the upper staff, 5–6 to the lower one, in every bar.
            voices = []
            for number, atoms in enumerate(bar.staves[hand], start=1 if hand == RIGHT else 5):
                voice = stream.Voice(id=str(number))
                for atom in atoms:
                    if atom.first:
                        for g in sorted((g for n in atom.notes for g in n.graces), key=lambda g: g.onset):
                            grace = note.Note(_pitch_name(g))
                            grace.duration = duration.Duration(type="eighth")
                            voice.insert(atom.offset, grace.getGrace())
                    voice.insert(atom.offset, element(atom))
                voices.append(voice)
            # Marks at a position go into the first voice, so they are written in time order
            # with its notes (notation programs read a pedal change before its start otherwise).
            for offset, obj in placed.get((hand, index), []):
                voices[0].insert(offset, obj)
            first_voices[(hand, index)] = voices[0]
            for voice in voices:
                measure.insert(0, voice)
            part.append(measure)
        staves.append(part)

    def anchor(hand: int, pos, ending: bool = False):
        """The note or rest of the first voice that a line starts on (or ends with) at `pos`.

        Lines hang on notes rather than on free anchors: music21 writes free anchors
        at the end of the bar, and notation programs then read them out of order.
        """
        index, offset = layout.locate(pos)
        if ending and offset == 0 and index > 0:
            index, offset = index - 1, layout.bars[index - 1].length
        items = list(first_voices[(hand, index)].notesAndRests)
        if not items:
            return None
        if ending:
            for item in items:
                if item.offset < offset <= item.offset + item.quarterLength:
                    return item
            return items[-1]
        for item in reversed(items):
            if item.offset <= offset:
                return item
        return items[0]

    for pin in marks.hairpins:
        if pin.words:
            continue
        a, b = anchor(RIGHT, pin.start), anchor(RIGHT, pin.end, ending=True)
        if a is not None and b is not None and a is not b:
            wedge = m21dynamics.Crescendo(a, b) if pin.crescendo else m21dynamics.Diminuendo(a, b)
            staves[RIGHT].insert(0, wedge)
    if pedal in ("lines", "signs"):
        # Every press of the pedal is a mark of its own, from where it goes down to where it
        # is changed: one long line with notches would say the same, but engraving programs
        # draw it unreliably once it runs over several systems.
        for line in marks.pedals:
            points = [line.start] + list(line.changes) + [line.end]
            for start, end in zip(points, points[1:]):
                a, b = anchor(LEFT, start), anchor(LEFT, end, ending=True)
                if a is None or b is None or a is b:
                    continue
                mark = expressions.PedalMark(a, b)
                mark.pedalType = expressions.PedalType.Sustain
                mark.pedalForm = expressions.PedalForm.Line if pedal == "lines" else expressions.PedalForm.Symbol
                staves[LEFT].insert(0, mark)

    # Lines that join notes: slurs, octave lines, trill lines.
    for slur in marks.slurs:
        a, b = first_element.get(id(slur.first)), last_element.get(id(slur.last))
        if a is not None and b is not None and a is not b:
            staves[slur.hand].insert(0, spanner.Slur(a, b))
    for line in marks.ottavas:
        a, b = first_element.get(id(line.first)), last_element.get(id(line.last))
        if a is not None and b is not None:
            mark = spanner.Ottava(a, b, type=line.kind, transposing=True,
                                  placement="above" if line.kind == "8va" else "below")
            staves[line.hand].insert(0, mark)
    for hand, staff in ((RIGHT, staves[0]), (LEFT, staves[1])):
        for bar in layout.bars:
            for voice in bar.staves[hand]:
                for atom in voice:
                    if atom.first and any(n.trill for n in atom.notes):
                        n = next(n for n in atom.notes if n.trill)
                        if n.dur >= 2 and last_element.get(id(n)) is not None:
                            staff.insert(0, expressions.TrillExtension(first_element[id(n)], last_element[id(n)]))

    for part in staves:
        score.insert(0, part)
    score.insert(0, m21layout.StaffGroup(staves, name="Piano", abbreviation="", symbol="brace"))
    return score


def _metronome(tempo, duration, meter, bpm: float):
    """A metronome mark for `bpm` tracked beats per minute, on the note value of the beat."""
    referent = duration.Duration(float(meter.beat_ql)) if meter.compound else duration.Duration(1.0)
    return tempo.MetronomeMark(number=nice_tempo(bpm * float(meter.beat_ql) / referent.quarterLength), referent=referent)


def musicxml_text(score) -> str:
    """The score as MusicXML, cleaned up for notation programs."""
    from music21.musicxml.m21ToXml import GeneralObjectExporter

    from . import __version__

    text = GeneralObjectExporter(score).parse().decode("utf-8")
    # A solo piano score carries no instrument label in front of the staves,
    # and no placeholder composer.
    text = re.sub(r"<part-name\s*/>|<part-name>[^<]*</part-name>", '<part-name print-object="no">Piano</part-name>', text, count=1)
    text = re.sub(r"\s*<part-abbreviation>[^<]*</part-abbreviation>", "", text, count=1)
    text = re.sub(r"\s*<instrument-abbreviation>[^<]*</instrument-abbreviation>", "", text, count=1)
    text = re.sub(r'\s*<creator type="composer">\s*</creator>', "", text, count=1)
    text = text.replace("<software>music21", f"<software>Melograph {__version__}</software>\n      <software>music21", 1)
    return re.sub(r"(<measure\b.*?</measure>)", lambda m: _number_voices(m.group(1)), text, flags=re.S)


def write_musicxml(score, path: Path) -> None:
    path.write_text(musicxml_text(score), encoding="utf-8")


def _number_voices(measure: str) -> str:
    """Give the voices fixed numbers: 1 and 2 on the upper staff, 5 and 6 on the lower.

    music21 numbers them bar by bar as they come, which makes notation programs
    shuffle a line between voices from one bar to the next.
    """
    notes = list(re.finditer(r"<note\b.*?</note>", measure, flags=re.S))
    found: dict[str, set[int]] = {}
    for n in notes:
        voice = re.search(r"<voice>(\d+)</voice>", n.group(0))
        staff = re.search(r"<staff>(\d+)</staff>", n.group(0))
        if voice:
            found.setdefault(staff.group(1) if staff else "1", set()).add(int(voice.group(1)))
    mapping = {
        (staff, old): 4 * (int(staff) - 1) + 1 + rank
        for staff, voices in found.items()
        for rank, old in enumerate(sorted(voices))
    }

    def renumber(n: re.Match) -> str:
        body = n.group(0)
        staff = re.search(r"<staff>(\d+)</staff>", body)
        key = staff.group(1) if staff else "1"
        return re.sub(r"<voice>(\d+)</voice>", lambda v: f"<voice>{mapping[(key, int(v.group(1)))]}</voice>", body, count=1)

    return re.sub(r"<note\b.*?</note>", renumber, measure, flags=re.S)
