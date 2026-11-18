"""The whole way from a performance to a score, without any user interface."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

import numpy as np

from .beats import Grid, build_grid, decide_meter
from .engrave import Layout, engrave
from .export import build_score
from .hands import split_hands
from .marks import (
    Marks, TempoMark, accents, chord_symbols, clefs, dynamics, fermatas, ottavas, pedal_lines, slurs, tempo_marks,
)
from .model import LEFT, RIGHT, Meter, Note, Performance
from .ornaments import find_rolls, find_trills
from .quantize import find_graces, quantise, swing_warp
from .spelling import Key, estimate_key, parse_key, spell
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
    pedal: str = "lines"  # "lines", "signs", "text" or "off"
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

    @property
    def bars(self) -> int:
        return len(self.layout.bars)

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
        return unit, round(first or self.grid.bpm)


def analyse(
    performance: Performance,
    beats: np.ndarray | None,
    downbeats: np.ndarray | None,
    options: Options,
) -> Result:
    requested = options.time_signature
    per_bar = None
    if requested:
        numerator, denominator = requested
        per_bar = numerator
        if denominator == 8 and numerator % 3 == 0 and numerator > 3:
            # 6/8 and friends: is the tracked pulse the eighth or the dotted quarter?
            fast = beats is not None and len(beats) > 3 and 60.0 / float(np.median(np.diff(beats))) > 160
            per_bar = numerator if fast else numerator // 3

    grid = build_grid(performance, beats, downbeats, per_bar, options.tempo_scale, options.pickup)
    # Fresh notes, so that the same performance can be analysed again with other options.
    played = [Note(n.pitch, n.onset, n.offset, n.velocity, sustain_end=n.sustain_end) for n in performance.notes]
    if options.trills:
        played = find_trills(played, grid)
    if options.arpeggios:
        find_rolls(played, grid)
    notes = list(played)
    quantisation = quantise(notes, grid, options.finest, options.triplets)
    meter = decide_meter(grid, quantisation.triple_share, requested, quantisation.triple_density)

    # Swing: beats in three that use only their last third (long–short) are swung eighths.
    second, third = quantisation.thirds
    swing = options.swing == "on" or (
        options.swing == "auto" and not requested and meter.compound and third >= 8 and second <= 0.15 * third
    )
    if swing:
        meter = Meter(grid.beats_per_bar, Fraction(1), grid.beats_per_bar, 4)
    warp = swing_warp if swing else None
    triplets = "off" if swing else options.triplets
    if options.graces:
        # Grace notes are judged against the finest grid, which needs the metre; then once more without them.
        slots = (6 if meter.compound else 4) * (2 if options.finest >= 32 else 1)
        notes = find_graces(played, grid, slots)
    if meter.compound or swing or len(notes) != len(played):
        quantisation = quantise(notes, grid, options.finest, triplets, compound=meter.compound, warp=warp)

    split_hands(notes, options.split_pitch)
    shape(notes, quantisation, grid, performance.pedals, options.max_voices, options.staccato)
    graces = [g for n in notes for g in n.graces]
    for g in graces:  # a grace note goes wherever its main note goes
        g.pos, g.hand, g.voice = g.grace_of.pos, g.grace_of.hand, g.grace_of.voice
    key = parse_key(options.key) if options.key else estimate_key(notes)
    spell(notes + graces, key)
    if options.accents:
        accents(notes)
    if options.fermatas:
        fermatas(notes, grid)
    layout = engrave(notes, grid, meter)

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
    if options.pedal in ("lines", "signs"):
        marks.pedals = pedal_lines(performance.pedals, notes, grid)
    if options.slurs:
        marks.slurs = slurs(notes, grid.beats_per_bar, grid.phase, performance.pedals)
    if options.dynamics:
        marks.dynamics, marks.hairpins = dynamics(notes, grid.beats_per_bar, options.hairpins)
    if options.tempo_changes:
        marks.tempos = tempo_marks(notes, grid)
    if not marks.tempos:
        marks.tempos = [TempoMark(min(n.pos for n in notes), bpm=grid.bpm)]
    if options.chords:
        marks.chords = chord_symbols(notes, key, grid.beats_per_bar, grid.phase)
    score = build_score(
        layout, key, grid.bpm, options.title, performance, marks, options.pedal, options.composer,
    )
    return Result(performance, notes + graces, grid, meter, key, layout, score, marks)
