"""The whole way from a performance to a score, without any user interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np

from .beats import Grid, Tracked, align_metre_changes, build_grid, compound_bars, set_meters, tempo_breaks
from .engrave import Layout, engrave
from .export import build_score
from .hands import split_hands
from .marks import (
    Marks, TempoMark, accents, chord_symbols, clefs, dynamics, fermatas, nice_tempo, ottavas, pedal_lines, slurs,
    tempo_marks,
)
from .model import LEFT, RIGHT, Meter, Note, Performance
from .ornaments import find_rolls, find_trills
from .quantize import find_graces, quantise, swing_warp
from .spelling import Key, estimate_keys, parse_key, spell
from .voices import shape


@dataclass
class Options:
    time_signature: tuple[int, int] | None = None
    key: str | None = None
    finest: int = 16
    triplets: str = "auto"
    tempo_scale: Fraction | None = None
    pickup: float | None = None  # beats before the first full bar
    split_pitch: int | None = None
    max_voices: int = 2
    staccato: bool = True
    dynamics: bool = True
    graces: bool = True
    title: str = ""
    composer: str = ""
    pedal: str = "auto"  # "auto", "lines", "signs", "text" or "off"
    slurs: bool = True
    hairpins: bool = True
    accents: bool = True
    fermatas: bool = True
    ottava: bool = True
    clef_changes: bool = True
    tempo_changes: bool = True
    trills: bool = True
    arpeggios: bool = True
    swing: str = "auto"  # "auto", "on" or "off"
    chords: bool = False


@dataclass
class Result:
    performance: Performance
    notes: list[Note]  # the notes as they appear in the score
    grid: Grid
    meter: Meter
    key: Key
    layout: Layout
    score: object
    marks: Marks
    keys: list[Key] = field(default_factory=list)  # the key of every bar

    @property
    def bars(self) -> int:
        return len(self.layout.bars)

    @property
    def key_changes(self) -> int:
        return sum(1 for a, b in zip(self.keys, self.keys[1:]) if a.fifths != b.fifths)

    @property
    def meter_changes(self) -> int:
        meters = self.layout.meters
        return sum(1 for a, b in zip(meters, meters[1:]) if (a.numerator, a.denominator) != (b.numerator, b.denominator))

    @property
    def right_hand(self) -> int:
        return sum(1 for n in self.notes if n.hand == RIGHT)

    @property
    def left_hand(self) -> int:
        return sum(1 for n in self.notes if n.hand == LEFT)

    @property
    def tempo(self) -> tuple[str, int]:
        """Note value that carries the beat, and beats per minute."""
        unit = {Fraction(3, 2): "♩.", Fraction(1, 2): "♪", Fraction(2): "𝅗𝅥"}.get(self.meter.beat_ql, "♩")
        first = next((m.bpm for m in self.marks.tempos if m.bpm), None)
        return unit, nice_tempo(first or self.grid.bpm)


def analyse(
    performance: Performance,
    beats: np.ndarray | None,
    downbeats: np.ndarray | None,
    options: Options,
    tracked: Tracked | None = None,
) -> Result:
    """From what was played to the score.

    `tracked` is what the beat tracker heard in the recording; without it the
    beats are taken from `beats` and `downbeats` (or derived from the notes).
    """
    requested = options.time_signature
    per_bar = None
    if requested:
        numerator, denominator = requested
        per_bar = numerator
        if denominator == 8 and numerator % 3 == 0 and numerator > 3:
            # 6/8 and friends: is the tracked pulse the eighth or the dotted quarter?
            fast = tracked is None and beats is not None and len(beats) > 3 and 60.0 / float(np.median(np.diff(beats))) > 160
            per_bar = numerator if fast else numerator // 3

    grid = build_grid(performance, beats, downbeats, per_bar, options.tempo_scale, options.pickup, tracked)
    # Fresh notes, so that the same performance can be analysed again with other options.
    played = [Note(n.pitch, n.onset, n.offset, n.velocity, sustain_end=n.sustain_end) for n in performance.notes]
    if options.trills:
        played = find_trills(played, grid)
    if options.arpeggios:
        find_rolls(played, grid)
    notes = list(played)
    quantisation = quantise(notes, grid, options.finest, options.triplets)
    # Simple or compound time, stretch by stretch: where the beats fall into three, the beat is a dotted quarter.
    compound = compound_bars(grid, quantisation.divisions)
    if options.triplets == "off":
        compound = [False] * grid.bars
    # Keys: one that is asked for holds for the whole piece; otherwise the signature follows the music.
    if options.key:
        keys = [parse_key(options.key)] * grid.bars
    else:
        keys = estimate_keys(notes, grid.bar_at, grid.bars)
    sections = tempo_breaks(grid) | {i for i in range(1, grid.bars) if keys[i].fifths != keys[i - 1].fifths}
    set_meters(grid, align_metre_changes(compound, sections), requested)

    # Swing: beats in three that use only their last third (long–short) are swung eighths.
    second, third = quantisation.thirds
    mostly_three = sum(compound) >= 0.8 * len(compound)
    swing = options.swing == "on" or (
        options.swing == "auto" and not requested and mostly_three and third >= 8 and second <= 0.15 * third
    )
    if swing:
        set_meters(grid, [False] * grid.bars)
    warp = swing_warp if swing else None
    triplets = "off" if swing else options.triplets
    if options.graces:
        # Grace notes are judged against the finest grid, which needs the metre; then once more without them.
        notes = find_graces(played, grid, options.finest)
    if any(m.compound for m in grid.meters) or swing or len(notes) != len(played):
        quantisation = quantise(notes, grid, options.finest, triplets, warp=warp)

    split_hands(notes, options.split_pitch)
    shape(notes, quantisation, grid, performance.pedals, options.max_voices, options.staccato)
    graces = [g for n in notes for g in n.graces]
    for g in graces:  # a grace note goes wherever its main note goes
        g.pos, g.hand, g.voice = g.grace_of.pos, g.grace_of.hand, g.grace_of.voice
    regions: dict[int, list[Note]] = {}
    for n in notes + graces:
        regions.setdefault(id(keys[grid.bar_at(n.pos)]), []).append(n)
    for key in {id(k): k for k in keys}.values():
        if id(key) in regions:
            spell(regions[id(key)], key)
    if options.accents:
        accents(notes)
    if options.fermatas:
        fermatas(notes, grid)
    layout = engrave(notes, grid)
    bar_keys = [keys[grid.bar_at(start)] for start in layout.starts[:-1]]
    key, meter = bar_keys[0], layout.meter

    marks = Marks(swing=swing)
    if options.clef_changes:
        marks.clefs = clefs(notes, layout.bar_of, len(layout.bars))
    else:
        def centre(hand: int, fallback: float) -> float:
            pitches = [n.pitch for n in notes if n.hand == hand]
            return sum(pitches) / len(pitches) if pitches else fallback

        marks.clefs = {
            RIGHT: ["F" if centre(RIGHT, 72) < 53 else "G"] * len(layout.bars),
            LEFT: ["G" if centre(LEFT, 48) > 65 else "F"] * len(layout.bars),
        }
    if options.ottava:
        marks.ottavas = ottavas(notes, marks.clefs, layout.bar_of)
        for g in graces:
            g.shift = g.grace_of.shift
    pedal = options.pedal
    if pedal == "auto":
        # Pedalling that runs through the whole piece is not marked change by change in
        # printed music; "con pedale" says it.  Pedal that is used here and there is drawn.
        first, last = min(n.onset for n in notes), max(n.sustain_end for n in notes)
        down = sum(max(0.0, min(last, p.end) - max(first, p.start)) for p in performance.pedals)
        pedal = "text" if len(performance.pedals) >= 6 and down >= 0.6 * (last - first) else "lines"
    if pedal in ("lines", "signs"):
        marks.pedals = pedal_lines(performance.pedals, notes, grid)
    if options.slurs:
        marks.slurs = slurs(notes, grid, performance.pedals)
    if options.dynamics:
        marks.dynamics, marks.hairpins = dynamics(notes, grid.beats_per_bar, options.hairpins)
    if options.tempo_changes:
        marks.tempos = tempo_marks(notes, grid)
    if not marks.tempos:
        marks.tempos = [TempoMark(min(n.pos for n in notes), bpm=grid.bpm)]
    # Where the beat changes from a quarter to a dotted quarter (or back), the tempo is
    # written again with the new note value.
    for index in range(1, len(layout.meters)):
        if layout.meters[index].compound != layout.meters[index - 1].compound:
            pos = layout.starts[index]
            if not any(m.bpm is not None and m.pos == pos for m in marks.tempos):
                current = [m.bpm for m in marks.tempos if m.bpm is not None and m.pos <= pos]
                marks.tempos.append(TempoMark(pos, bpm=current[-1] if current else grid.bpm))
    marks.tempos.sort(key=lambda m: m.pos)
    if options.chords:
        marks.chords = chord_symbols(notes, keys, grid)
    score = build_score(
        layout, bar_keys, grid.bpm, options.title, performance, marks, pedal, options.composer,
    )
    return Result(performance, notes + graces, grid, meter, key, layout, score, marks, bar_keys)
