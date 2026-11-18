"""Rhythm quantisation: from played times to positions in the bar.

Every beat gets its own subdivision (none, halves, quarters, triplets …).  The
choice is made for the whole piece at once with dynamic programming, so that a
single late note does not turn a bar of plain eighths into triplets, while real
triplets are still found.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from fractions import Fraction

import numpy as np

from .beats import Grid
from .model import Note

TIMING_SPREAD = 0.028  # seconds a pianist typically deviates from the grid
COLLISION = 4.0  # cost of folding two separate attacks into one position
SWITCH = 1.2  # cost of changing between twos and threes from one beat to the next

DUPLE = {2, 4, 8}
TRIPLE = {3, 6}


def _family(division: int) -> int:
    return 1 if division in DUPLE else 2 if division in TRIPLE else 0


@dataclass
class Quantisation:
    divisions: dict[int, int]  # beat index → subdivision
    triple_share: float  # share of subdivided beats that are in three
    triple_density: float = 0.0  # share of all beats with notes that are in three
    # Attacks on the second and on the third third of beats that are in three:
    # swing uses only the third one (long–short), real triplets both.
    thirds: tuple[int, int] = (0, 0)


def find_graces(notes: list[Note], grid: Grid, finest: int) -> list[Note]:
    """Find grace notes and return the notes that remain for the rhythm.

    A grace note is flicked just before its main note, a step away from it, and
    let go at once.  It has no place in the bar of its own – it falls into the
    same slot of the finest grid as its main note – and forced onto the grid it
    would wreck the rhythm around it.  Fast runs are left alone: the note must
    stand by itself, with nothing similar right before or after.
    """
    ordered = sorted(notes, key=lambda n: (n.onset, n.pitch))
    onsets = [n.onset for n in ordered]
    for n in ordered:
        n.grace_of, n.graces = None, []

    def slot(seconds: float) -> int:
        beat = grid.beat_of(seconds)
        slots = (6 if grid.meter_at(beat).compound else 4) * (2 if finest >= 32 else 1)
        return round(beat * slots)

    for i, g in enumerate(ordered):
        if g.offset - g.onset > 0.16:
            continue
        main = None
        for m in ordered[i + 1:]:
            lead = m.onset - g.onset
            if lead >= 0.12:
                break
            if (
                lead > 0.03
                and 1 <= abs(m.pitch - g.pitch) <= 2
                and g.offset <= m.onset + 0.07
                and m.offset - m.onset > 0.16
                and slot(g.onset) == slot(m.onset)
            ):
                main = m
                break
        if main is None or main.grace_of is not None or g.graces:
            continue
        nearby = ordered[bisect_left(onsets, g.onset - 0.14):bisect_left(onsets, main.onset + 0.14)]
        in_a_run = any(
            o is not g and o is not main and abs(o.pitch - g.pitch) <= 7
            and (o.onset < g.onset - 0.03 or o.onset > main.onset + 0.03)
            for o in nearby
        )
        if not in_a_run:
            g.grace_of = main
            main.graces.append(g)
    return [n for n in notes if n.grace_of is None]


def _cluster(notes: list[Note]) -> list[list[Note]]:
    """Group notes that were struck together (a chord, even a slightly rolled one)."""
    clusters: list[list[Note]] = []
    rolls: dict[int, list[Note]] = {}
    for n in sorted(notes, key=lambda n: (n.onset, n.pitch)):
        if n.roll:
            if n.roll in rolls:
                rolls[n.roll].append(n)
            else:
                rolls[n.roll] = [n]
                clusters.append(rolls[n.roll])
            continue
        if clusters and not clusters[-1][0].roll:
            group = clusters[-1]
            together = n.onset - group[-1].onset <= 0.028 and n.onset - group[0].onset <= 0.06
            if together and all(g.pitch != n.pitch for g in group):
                group.append(n)
                continue
        clusters.append([n])
    return clusters


def quantise(
    notes: list[Note],
    grid: Grid,
    finest: int = 16,
    triplets: str = "auto",
    compound: bool = False,
    warp=None,
) -> Quantisation:
    """Set `pos`, `key_end` and `snd_end` (all in beats) on every note.

    `compound` means the beat itself is a dotted note (6/8, 12/8 …), so that
    three to a beat is the plain case and two to a beat the exception; once
    the metres of the grid are set, they decide that bar by bar.
    `warp` maps the position inside a beat (0 … 1) before fitting; swing uses it
    to turn its long-short pairs into the even eighths they are written as.
    """
    dotted = {1: 0.0, 3: 0.35, 2: 1.9}
    if finest >= 16:
        dotted[6] = 1.2
    plain = {1: 0.0, 2: 0.35, 4: 1.2}
    if finest >= 32:
        plain[8] = 3.6
    if finest <= 8:
        plain.pop(4)
    if triplets != "off":
        plain[3] = 1.7
        if finest >= 32:
            plain[6] = 3.9
    if grid.meters and not compound:
        in_three = {k for index, meter in enumerate(grid.meters) if meter.compound
                    for k in range(grid.bar_start(index), grid.bar_start(index + 1))}
    else:
        in_three = None  # all beats alike

    def penalties_of(k: int, plain: dict[int, float] = plain) -> dict[int, float]:
        if in_three is None:
            return dotted if compound else plain
        return dotted if k in in_three else plain

    def beat(seconds: float) -> float:
        """Continuous beat position; with swing the long-short pairs become even."""
        b = grid.beat_of(seconds)
        if warp is None:
            return b
        whole = np.floor(b)
        return float(whole + warp(b - whole))

    clusters = _cluster(notes)
    # A rolled chord counts from its first note, where the roll begins.
    moments = [
        beat(min(n.onset for n in c)) if c[0].roll else beat(float(np.median([n.onset for n in c])))
        for c in clusters
    ]
    by_beat: dict[int, list[float]] = {}
    for m in moments:
        by_beat.setdefault(int(np.floor(m)), []).append(m - np.floor(m))

    def solve(plain: dict[int, float], doubtful: dict[int, float] | None = None, trusted: set[int] = frozenset()) -> dict[int, int]:
        """The division of every beat. `doubtful` penalties apply to all beats but the `trusted` ones."""
        beats = sorted(by_beat)
        best: list[dict[int, tuple[float, int | None]]] = []
        for index, k in enumerate(beats):
            seconds = grid.beat_seconds(k)
            pen = penalties_of(k, plain if doubtful is None or k in trusted else doubtful)
            row: dict[int, tuple[float, int | None]] = {}
            for d in sorted(pen):
                cost = pen[d]
                slots: set[int] = set()
                for f in by_beat[k]:
                    slot = int(round(f * d))
                    cost += ((f - slot / d) * seconds / TIMING_SPREAD) ** 2
                    if slot in slots:
                        cost += COLLISION
                    slots.add(slot)
                if index == 0:
                    row[d] = (cost, None)
                    continue
                adjacent = beats[index - 1] == k - 1
                choice, total = None, float("inf")
                for previous, (so_far, _) in best[-1].items():
                    change = SWITCH if adjacent and _family(previous) * _family(d) == 2 else 0.0
                    if so_far + change < total:
                        choice, total = previous, so_far + change
                row[d] = (cost + total, choice)
            best.append(row)
        result: dict[int, int] = {}
        d = min(best[-1], key=lambda x: best[-1][x][0])
        for index in range(len(beats) - 1, -1, -1):
            result[beats[index]] = d
            d = best[index][d][1]
        return result

    divisions = solve(plain)

    def share(div: dict[int, int], everywhere: bool = True) -> float:
        subdivided = [d for k, d in div.items() if d > 1 and (everywhere or not in_three or k not in in_three)]
        return sum(1 for d in subdivided if d in TRIPLE) / len(subdivided) if subdivided else 0.0

    if triplets == "auto" and not compound and 0 < share(divisions, everywhere=False) < 0.12:
        # A handful of triplet beats in music that otherwise moves in twos is almost
        # always rubato; ask for much stronger evidence – unless a beat has the shape of
        # a real triplet: all three notes, or the pair of beats of a quarter-note triplet
        # (a note on the last third, then one on the first third of the next beat).
        def thirds(k: int) -> set[int]:
            return {int(round(f * 3)) for f in by_beat.get(k, [])} & {1, 2}

        shaped = {k for k in by_beat if thirds(k) == {1, 2}}
        for k in by_beat:
            if thirds(k) == {2} and thirds(k + 1) == {1}:
                shaped.update((k, k + 1))
        stricter = dict(plain)
        for d in TRIPLE:
            if d in stricter:
                stricter[d] += 2.5
        divisions = solve(plain, stricter, shaped)
    triple_share = share(divisions)

    thirds = [0, 0, 0]
    for cluster, moment in zip(clusters, moments):
        k = int(np.floor(moment))
        d = divisions[k]
        slot = int(round((moment - k) * d))
        position = Fraction(k) + Fraction(slot, d)
        if d == 3:
            thirds[slot % 3] += 1
        for n in cluster:
            n.pos = position
    for n in notes:
        n.key_end = beat(n.offset)
        n.snd_end = beat(n.sustain_end)

    # The same key cannot be struck twice at one position.
    seen: dict[tuple[Fraction, int], Note] = {}
    for n in sorted(notes, key=lambda n: -(n.sustain_end - n.onset)):
        seen.setdefault((n.pos, n.pitch), n)
    notes[:] = sorted(seen.values(), key=lambda n: (n.pos, n.pitch))
    density = sum(1 for d in divisions.values() if d in TRIPLE) / max(1, len(divisions))
    return Quantisation(divisions, triple_share, density, (thirds[1], thirds[2]))


def swing_warp(f: float) -> float:
    """Swung eighths: the long first two thirds of a beat become the first half."""
    return f * 0.75 if f <= 2 / 3 else 0.5 + (f - 2 / 3) * 1.5


def swing_unwarp(f: float) -> float:
    """The other way round: where a written position inside the beat is played with swing."""
    return f / 0.75 if f <= 0.5 else 2 / 3 + (f - 0.5) / 1.5


def snap_length(start: Fraction, end: float, quantisation: Quantisation, anchors: list[Fraction]) -> Fraction:
    """Notated end of a note that stops at `end` (continuous beats).

    Prefers a position where something else begins (the usual reason a note
    ends), otherwise the subdivision of the beat it ends in.
    """
    best, distance = None, 0.3
    index = bisect_left(anchors, end)  # `anchors` is sorted; only its neighbours of `end` matter
    for a in anchors[max(0, index - 1):index + 1]:
        if a > start and abs(float(a) - end) < distance:
            best, distance = a, abs(float(a) - end)
    if best is not None:
        return best
    k = int(np.floor(end))
    d = max(2, quantisation.divisions.get(k, 2))
    snapped = Fraction(k) + Fraction(int(round((end - k) * d)), d)
    step = Fraction(1, d)
    return max(snapped, start + step)
