"""Rhythm quantisation: from played times to positions in the bar.

Every beat gets its own subdivision (none, halves, quarters, triplets …).  The
choice is made for the whole piece at once with dynamic programming, so that a
single late note does not turn a bar of plain eighths into triplets, while real
triplets are still found.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
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
    by_hand: dict[int, dict[int, int]] = field(default_factory=dict)  # hand → beat index → subdivision

    def of_hand(self, hand: int) -> "Quantisation":
        """The subdivisions as one hand has them (the hands may differ: three against two)."""
        if hand not in self.by_hand:
            return self
        return Quantisation(self.by_hand[hand], self.triple_share, self.triple_density, self.thirds)


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


APART = 6.0  # cost of writing two hands apart that struck together
TOGETHER = 2.5  # cost of writing two hands together that struck clearly one after the other
POLYRHYTHM = 0.6  # cost of one hand in twos against the other in threes within a beat
PAIR_SPLIT = 4.0  # cost of writing half of what may be a quarter-note triplet as one and half not


def quantise_hands(
    notes: list[Note],
    grid: Grid,
    finest: int = 16,
    triplets: str = "auto",
    warp=None,
) -> Quantisation:
    """Set the positions again, now that the hands are known: each hand gets its own subdivision.

    A quarter-note triplet in the right hand over plain eighths in the left has no
    place on one common grid of sixteenths; with a subdivision for each hand it
    is simply three against two.  The two hands are fitted together, beat by
    beat: what they struck together stays together, what they struck one after
    the other is not written on one position, and a hand changes between twos
    and threes only for a reason.  Sets `pos` on every note.
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
    doubtful = dict(plain)
    for d in TRIPLE:
        if d in doubtful:
            doubtful[d] += 2.5
    in_three = {k for index, meter in enumerate(grid.meters) if meter.compound
                for k in range(grid.bar_start(index), grid.bar_start(index + 1))}

    def beat(seconds: float) -> float:
        b = grid.beat_of(seconds)
        if warp is None:
            return b
        whole = np.floor(b)
        return float(whole + warp(b - whole))

    clusters = _cluster(notes)
    moments = [
        beat(min(n.onset for n in c)) if c[0].roll else beat(float(np.median([n.onset for n in c])))
        for c in clusters
    ]
    # attacks[hand][beat] → [(place in the beat, cluster)]
    attacks: dict[int, dict[int, list[tuple[float, int]]]] = {0: {}, 1: {}}
    for index, (cluster, moment) in enumerate(zip(clusters, moments)):
        k = int(np.floor(moment))
        for hand in {n.hand for n in cluster}:
            attacks[hand].setdefault(k, []).append((moment - k, index))

    def shapes(hand: int) -> tuple[set[int], set[int], set[int]]:
        """Beats with the shape of a real triplet.

        Returns (beats that are trusted to be triplets, first beats of clear quarter-note
        triplets, first beats of everything that could be one).  A quarter-note triplet
        is a pair of beats: one note late in the first beat, one before the middle of the
        second.  Three plus three plus two eighths look alike, but their last note sits
        on the half beat – which is why only pairs with an early last note count as clear.
        """
        mine = attacks[hand]

        def off(k: int) -> list[float]:
            return [f for f, _ in mine.get(k, []) if 0.12 <= f <= 0.88]

        def on(k: int) -> bool:
            """Is something struck on beat k itself (a little early or late)?"""
            return any(f < 0.12 for f, _ in mine.get(k, [])) or any(f > 0.88 for f, _ in mine.get(k - 1, []))

        full = {k for k in mine if {int(round(f * 3)) for f in off(k)} == {1, 2} and len(off(k)) == 2}
        clear: set[int] = set()
        possible: set[int] = set()
        for k in mine:
            first, second = off(k), off(k + 1)
            if on(k + 1):
                continue  # the middle note of a quarter-note triplet is held over the second beat
            if len(first) == 1 and len(second) == 1 and 0.58 <= first[0] <= 0.80 and 0.25 <= second[0] <= 0.55:
                possible.add(k)
                if first[0] <= 0.78 and second[0] <= 0.46:
                    clear.add(k)
        return full | clear | {k + 1 for k in clear}, clear, possible

    shaped = {hand: shapes(hand) for hand in (0, 1)}
    figure = {hand: shaped[hand][1] | {k + 1 for k in shaped[hand][1]} for hand in (0, 1)}
    forced: dict[int, set[int]] = {0: set(), 1: set()}  # beats that are written as triplets whatever the timing

    def fit(hand: int, k: int, d: int, strict: bool) -> tuple[float, list[tuple[Fraction, float, int]]]:
        """Cost of dividing beat k into d for one hand, and where its attacks then stand."""
        here = attacks[hand].get(k, [])
        if not here:
            return (0.0 if d == 1 else float("inf")), []
        if k in forced[hand] and d != 3:
            return float("inf"), []
        trusted = shaped[hand][0]
        if k in in_three:
            penalties = dotted
        else:
            penalties = doubtful if strict and k not in trusted and k not in forced[hand] else plain
        if d not in penalties:
            return float("inf"), []
        cost = penalties[d]
        if d == 3 and (k in figure[hand] or k in forced[hand]) and k not in in_three:
            cost = plain[3] / 2  # the two beats of a quarter-note triplet are one figure
        seconds = grid.beat_seconds(k)
        placed, slots = [], set()
        for f, cluster in here:
            slot = int(round(f * d))
            cost += ((f - slot / d) * seconds / TIMING_SPREAD) ** 2
            if slot in slots:
                cost += COLLISION
            slots.add(slot)
            placed.append((Fraction(k) + Fraction(slot, d), f * seconds, cluster))
        return cost, placed

    beats = sorted(set(attacks[0]) | set(attacks[1]))
    options = sorted(set(plain) | set(dotted))

    def solve(strict: tuple[bool, bool]) -> dict[int, tuple[int, int]]:
        best: list[dict[tuple[int, int], tuple[float, tuple[int, int] | None]]] = []
        for index, k in enumerate(beats):
            fits = {
                hand: {d: fit(hand, k, d, strict[hand]) for d in options} for hand in (0, 1)
            }
            row: dict[tuple[int, int], tuple[float, tuple[int, int] | None]] = {}
            for right, (cost_right, placed_right) in fits[0].items():
                if cost_right == float("inf"):
                    continue
                for left, (cost_left, placed_left) in fits[1].items():
                    if cost_left == float("inf"):
                        continue
                    cost = cost_right + cost_left
                    if _family(right) * _family(left) == 2:
                        cost += POLYRHYTHM
                    # (In a beat that is a triplet by the look of the whole piece, the hands
                    # are two layers; a late triplet note near an eighth of the other hand
                    # does not bind them.)
                    layers = k in forced[0] or k in forced[1]
                    for pos_right, time_right, cluster_right in placed_right:
                        for pos_left, time_left, cluster_left in placed_left:
                            if cluster_right == cluster_left:
                                cost += APART if pos_right != pos_left and not layers else 0.0
                            elif pos_right == pos_left and abs(time_right - time_left) > 0.03:
                                cost += TOGETHER
                    if index == 0:
                        row[(right, left)] = (cost, None)
                        continue
                    adjacent = beats[index - 1] == k - 1
                    choice, total = None, float("inf")
                    for previous, (so_far, _) in best[-1].items():
                        change = 0.0
                        if adjacent:
                            for hand, (new, old) in enumerate(((right, previous[0]), (left, previous[1]))):
                                if k - 1 in shaped[hand][2]:
                                    # the two beats of what may be a quarter-note triplet go together:
                                    # a triplet in both, or in neither
                                    change += PAIR_SPLIT if (new == 3) != (old == 3) else 0.0
                                elif _family(new) * _family(old) == 2 and not (
                                    k in figure[hand] or k - 1 in figure[hand] or k in forced[hand] or k - 1 in forced[hand]
                                ):
                                    change += SWITCH  # entering or leaving such a figure is no change of mind
                        if so_far + change < total:
                            choice, total = previous, so_far + change
                    row[(right, left)] = (cost + total, choice)
            best.append(row)
        result: dict[int, tuple[int, int]] = {}
        state = min(best[-1], key=lambda s: best[-1][s][0])
        for index in range(len(beats) - 1, -1, -1):
            result[beats[index]] = state
            state = best[index][state][1]
        return result

    def share(divisions: dict[int, tuple[int, int]], hand: int) -> float:
        subdivided = [d[hand] for k, d in divisions.items() if d[hand] > 1 and k not in in_three]
        return sum(1 for d in subdivided if d in TRIPLE) / len(subdivided) if subdivided else 0.0

    divisions = solve((False, False))
    if triplets == "auto":
        # As before: a handful of triplets among twos is usually rubato and needs more
        # evidence – for each hand by itself, and not where the shape of a triplet is there.
        strict = tuple(0 < share(divisions, hand) < 0.12 for hand in (0, 1))
        if any(strict):
            divisions = solve(strict)
        # A figure that comes back is written the same way each time.  Where most of the
        # possible quarter-note triplets of a hand came out as triplets, the lazily played
        # ones (the last note nearly on the half beat) are triplets too.
        for hand in (0, 1):
            possible = shaped[hand][2]
            written = {k for k in possible if divisions[k][hand] == 3 and divisions.get(k + 1, (0, 0))[hand] == 3}
            if len(written) >= 2 and len(written) >= len(possible) - len(written):
                forced[hand] = possible | {k + 1 for k in possible}
        if forced[0] or forced[1]:
            divisions = solve(strict)

    for cluster, moment in zip(clusters, moments):
        k = int(np.floor(moment))
        for n in cluster:
            d = divisions[k][n.hand]
            n.pos = Fraction(k) + Fraction(int(round((moment - k) * d)), d)

    # The same key cannot be struck twice at one position.
    seen: dict[tuple[Fraction, int], Note] = {}
    for n in sorted(notes, key=lambda n: -(n.sustain_end - n.onset)):
        seen.setdefault((n.pos, n.pitch), n)
    notes[:] = sorted(seen.values(), key=lambda n: (n.pos, n.pitch))
    finest_of = {k: max(d) for k, d in divisions.items()}
    triple = [d for k, pair in divisions.items() for d in pair if d > 1]
    return Quantisation(
        finest_of,
        sum(1 for d in triple if d in TRIPLE) / len(triple) if triple else 0.0,
        sum(1 for pair in divisions.values() if any(d in TRIPLE for d in pair)) / max(1, len(divisions)),
        by_hand={hand: {k: pair[hand] for k, pair in divisions.items()} for hand in (0, 1)},
    )


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
