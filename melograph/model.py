"""Shared data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

RIGHT, LEFT = 0, 1


@dataclass(eq=False)
class Note:
    """One played note, from raw performance timing to its place in the score."""

    pitch: int
    onset: float  # seconds
    offset: float  # seconds, key release
    velocity: int = 64

    sustain_end: float = 0.0  # seconds, end of the sound including the pedal

    # Filled by the quantiser (unit: beats of the tracked pulse).
    pos: Fraction | None = None  # quantised onset
    key_end: float = 0.0  # key release, continuous
    snd_end: float = 0.0  # end of the sound, continuous
    dur: Fraction | None = None  # notated length

    hand: int = RIGHT
    voice: int = 0  # 0 = upper stream of the staff, 1 = lower stream
    held: bool = False  # key stays down while later notes of the hand start
    staccato: bool = False
    accent: bool = False
    fermata: bool = False
    trill: bool = False  # stands for a trill that was played on this note
    roll: int = 0  # > 0: part of a rolled chord (arpeggio), the number names the chord
    shift: int = 0  # octaves the note is written away from where it sounds (8va: -1, 8vb: +1)
    grace_of: "Note | None" = field(default=None, repr=False)  # a grace note leading into that note
    graces: "list[Note]" = field(default_factory=list, repr=False)  # grace notes written before this one

    # Spelling.
    step: str = "C"
    alter: int = 0
    octave: int = 4


@dataclass
class Pedal:
    start: float
    end: float


@dataclass
class Performance:
    """The transcribed performance: what was played, without any notation."""

    notes: list[Note]
    pedals: list[Pedal] = field(default_factory=list)
    duration: float = 0.0


@dataclass
class Meter:
    beats_per_bar: int
    beat_ql: Fraction  # quarter lengths per tracked beat
    numerator: int
    denominator: int

    @property
    def bar_ql(self) -> Fraction:
        return self.beat_ql * self.beats_per_bar

    @property
    def compound(self) -> bool:
        return self.beat_ql == Fraction(3, 2)

    def __str__(self) -> str:
        return f"{self.numerator}/{self.denominator}"
