"""Small pieces with a known score, played back as a performance for the tests."""

from __future__ import annotations

import random
from fractions import Fraction

import numpy as np

from melograph.model import Note, Pedal, Performance
from melograph.transcribe import finish

STEPS = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}


def pitch(name: str) -> int:
    base = STEPS[name[0].lower()]
    rest = name[1:]
    while rest and rest[0] in "#b":
        base += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    return 12 * (int(rest) + 1) + base


def parse(line: str) -> list[tuple[Fraction, Fraction, list[int], bool]]:
    """'c4:1 [e4 g4]:1/2 r:1 g4:1.' → (start beat, length in beats, pitches, detached).

    r is a rest; a full stop after the length plays the note short (staccato).
    """
    out = []
    t = Fraction(0)
    tokens = line.replace("[", " [").split()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("["):
            while "]" not in token:
                i += 1
                token += " " + tokens[i]
            names, length = token.split("]:")
            names = names[1:].split()
        else:
            name, length = token.split(":")
            names = [name]
        detached = length.endswith(".")
        length = Fraction(length.rstrip("."))
        if names != ["r"]:
            out.append((t, length, [pitch(n) for n in names], detached))
        t += length
        i += 1
    return out


def play(
    *lines: str,
    bpm: float = 100,
    legato: float = 0.92,
    velocity: int = 70,
    jitter: float = 0.0,
    pedals: list[tuple[float, float]] = (),
    beats_per_bar: int = 4,
    tempo=None,
    seed: int = 1,
) -> tuple[Performance, np.ndarray, np.ndarray]:
    """Play the lines and return the performance with its beats and downbeats.

    `tempo(beat) → seconds` can replace the steady tempo (for rit. and the like);
    `pedals` are (first beat, last beat) pairs.
    """
    rng = random.Random(seed)
    seconds = tempo or (lambda b: 1.0 + float(b) * 60.0 / bpm)
    notes: list[Note] = []
    length = Fraction(0)
    for line in lines:
        for start, dur, pitches, detached in parse(line):
            shift = rng.gauss(0, jitter)
            held = Fraction(0.35 if detached else legato).limit_denominator(100)
            for k, p in enumerate(pitches):
                on = seconds(start) + shift + 0.004 * k
                off = seconds(start + dur * held) + rng.gauss(0, jitter / 2)
                notes.append(Note(p, on, max(on + 0.05, off), velocity))
            length = max(length, start + dur)
    total = int(length) + 2
    beats = np.array([seconds(b) for b in range(total)])
    downbeats = beats[::beats_per_bar]
    performance = Performance(
        sorted(notes, key=lambda n: (n.onset, n.pitch)),
        [Pedal(seconds(a), seconds(b)) for a, b in pedals],
        float(beats[-1]),
    )
    return finish(performance), beats, downbeats
