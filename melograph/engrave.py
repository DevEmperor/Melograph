"""From quantised notes to bars of symbols that can actually be written down.

A note that lasts five sixteenths has no single symbol; it has to be split and
tied – and *where* it is split decides whether the bar is readable.  The rules
here follow engraving practice: the beat structure of the bar stays visible,
simple syncopations and dotted figures are kept as one note, rests never hide
a beat, and triplets are bracketed beat by beat.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

from .beats import Grid
from .model import LEFT, RIGHT, Meter, Note

F = Fraction
TYPES = {
    F(8): "breve", F(4): "whole", F(2): "half", F(1): "quarter",
    F(1, 2): "eighth", F(1, 4): "16th", F(1, 8): "32nd", F(1, 16): "64th",
}
SMALLEST = F(1, 16)


@dataclass
class Atom:
    """One written symbol: a note, a chord or a rest."""

    offset: Fraction  # from the start of the bar, in quarter lengths
    length: Fraction  # sounding length in quarter lengths
    kind: str  # "quarter", "eighth" …
    dots: int = 0
    notes: list[Note] = field(default_factory=list)  # empty → rest
    tie_in: bool = False
    tie_out: bool = False
    first: bool = True  # first symbol of its note (carries the articulation)
    tuplet: str | None = None  # "start", "inside" or "stop" for triplet members
    tuplet_unit: str | None = None
    whole_bar: bool = False
    hidden: bool = False  # a rest that only keeps the second voice in step
    span: int = -1


@dataclass
class Bar:
    number: int  # 0 for a pickup bar
    length: Fraction
    staves: list[list[list[Atom]]]  # [staff][voice] → atoms


@dataclass
class Layout:
    meter: Meter
    bars: list[Bar]
    origin: Fraction  # beat at which the first bar starts
    edges: list[Fraction] = field(default_factory=list)  # bar lines in quarter lengths from the origin

    def locate(self, pos: Fraction) -> tuple[int, Fraction]:
        """Bar index and offset in it (quarter lengths) of a position in beats."""
        t = (pos - self.origin) * self.meter.beat_ql
        index = 0
        while index + 1 < len(self.edges) - 1 and self.edges[index + 1] <= t:
            index += 1
        index = max(0, min(index, len(self.bars) - 1))
        return index, max(F(0), min(t - self.edges[index], self.bars[index].length))

    def bar_of(self, pos: Fraction) -> int:
        return self.locate(pos)[0]

    def seconds_of_quarter(self, grid: Grid):
        """Maps a score position in quarters (from the first bar line) to seconds in the recording."""
        def convert(q: float) -> float:
            return grid.time_of(float(self.origin) + q / float(self.meter.beat_ql))
        return convert


@dataclass
class _Segment:
    start: Fraction  # metric position inside the bar
    end: Fraction
    notes: list[Note]
    tie_in: bool
    tie_out: bool


def _binary(x: Fraction) -> bool:
    d = x.denominator
    return d & (d - 1) == 0


def _notatable(d: Fraction) -> tuple[str, int] | None:
    if d in TYPES:
        return TYPES[d], 0
    plain = d * 2 / 3
    if plain in TYPES and plain >= SMALLEST * 2:
        return TYPES[plain], 1
    return None


class Metric:
    """The hierarchy of strong and weak positions in a bar."""

    def __init__(self, meter: Meter):
        self.meter = meter
        self.bar = meter.bar_ql
        n, d = meter.numerator, meter.denominator
        if meter.compound:
            beats = [F(3, 2) * i for i in range(1, n // 3)]
            self.tops = [{F(0)}, {F(3)}, {F(3, 2), F(9, 2)}] if n == 12 else [{F(0)}, set(beats)]
            self.unit = F(1, 2)
        elif d == 4:
            middle = {4: 2, 5: 3, 6: 3, 7: 4}.get(n)
            self.tops = [{F(0)}, {F(middle)}] if middle else [{F(0)}]
            self.unit = F(1)
        elif d == 8:
            self.tops = [{F(0)}, {F(3, 2)}] if n in (5, 7) else [{F(0)}]
            self.unit = F(1, 2)
        else:
            self.tops = [{F(0)}]
            self.unit = F(4, d)
        self.tops = [group for group in self.tops if group]

    def level(self, p: Fraction) -> int:
        p = p % self.bar
        for i, group in enumerate(self.tops):
            if p in group:
                return i
        u, i = self.unit, len(self.tops)
        while p % u != 0:
            u, i = u / 2, i + 1
        return i

    def unit_of(self, level: int) -> Fraction | None:
        return self.unit / 2 ** (level - len(self.tops)) if level >= len(self.tops) else None

    def strongest_inside(self, s: Fraction, e: Fraction) -> tuple[int, list[Fraction]] | None:
        for i, group in enumerate(self.tops):
            inside = sorted(p for p in group if s < p < e)
            if inside:
                return i, inside
        u, i = self.unit, len(self.tops)
        while u >= SMALLEST:
            p = (s // u + 1) * u
            if p < e:
                points = []
                while p < e:
                    points.append(p)
                    p += u
                return i, points
            u, i = u / 2, i + 1
        return None

    def note_ok(self, s: Fraction, e: Fraction) -> bool:
        d = e - s
        if _notatable(d) is None:
            return False
        inside = self.strongest_inside(s, e)
        if inside is None:
            return True
        level, points = inside
        if self.meter.compound:
            beat = F(3, 2)
            crosses = (s // beat + 1) * beat < e
            if crosses and (s % beat or e % beat):
                return False
        start, end = self.level(s), self.level(e)
        if level >= min(start, end):
            return True
        # Simple syncopation: short – long – short across one stronger position.
        u = self.unit_of(start)
        if u is not None and d == 2 * u and level == start - 1 and points == [s + u]:
            p = points[0] - u
            while self.level(p) > level:
                p -= u
            return points[0] - p == 2 * u
        return False

    def rest_ok(self, s: Fraction, e: Fraction) -> bool:
        d = e - s
        kind = _notatable(d)
        if kind is None:
            return False
        dotted = kind[1] == 1
        inside = self.strongest_inside(s, e)
        if inside is None:
            return not dotted
        if inside[0] > max(self.level(s), self.level(e)):
            return not dotted or (self.meter.compound and d in (F(3, 2), F(3)))
        return self.meter.compound and d == 1 and s % F(3, 2) == 0

    def split(self, s: Fraction, e: Fraction, rest: bool) -> list[tuple[Fraction, Fraction]]:
        if (self.rest_ok if rest else self.note_ok)(s, e):
            return [(s, e)]
        inside = self.strongest_inside(s, e)
        if inside is None:
            return [(s, e)]
        level, points = inside
        cut = points[-1] if self.level(s) <= level else points[0]
        return self.split(s, cut, rest) + self.split(cut, e, rest)


def _split_triplet(a: int, b: int) -> list[tuple[int, int]]:
    """Split [a, b) inside a triplet beat, measured in twelfths of the beat."""
    n = b - a
    if n == 1 or (n == 2 and a % 2 == 0) or (n in (4, 8) and a % 4 == 0):
        return [(a, b)]
    for step in (4, 2, 1):
        inside = [p for p in range(a + 1, b) if p % step == 0]
        if inside:
            cut = inside[-1] if a % step == 0 else inside[0]
            return _split_triplet(a, cut) + _split_triplet(cut, b)
    return [(a, b)]


def _voice_atoms(
    segments: list[_Segment],
    shift: Fraction,
    length: Fraction,
    metric: Metric,
    span: Fraction | None,
    fill: bool,
) -> list[Atom]:
    """Write one voice of one bar. Positions are metric (bar start = `shift`)."""
    end_of_bar = shift + length
    segments = sorted(segments, key=lambda s: s.start)
    if not segments:
        if shift == 0 and length == metric.bar:
            return [Atom(F(0), length, "whole", whole_bar=True)]
        return [Atom(s - shift, e - s, *_notatable(e - s)) for s, e in metric.split(shift, end_of_bar, True)]

    pieces: list[tuple[Fraction, Fraction, _Segment | None]] = []
    cursor = shift
    for seg in segments:
        if seg.start > cursor:
            pieces.append((cursor, seg.start, None))
        pieces.append((seg.start, seg.end, seg))
        cursor = seg.end
    if cursor < end_of_bar:
        pieces.append((cursor, end_of_bar, None))

    # Triplet brackets: each beat in three gets its own – unless notes run across the
    # beat line between two such beats (quarter-note triplets); then they share one.
    groups: list[tuple[Fraction, Fraction]] = []  # (start, length)
    if span is not None:
        triplet_beats = sorted({int(p // span) for seg in segments for p in (seg.start, seg.end) if not _binary(p)})
        bounds = {x for s, e, _ in pieces for x in (s, e)}
        taken: set[int] = set()
        for k in triplet_beats:
            if k in taken:
                continue
            lo, hi = k * span, (k + 2) * span
            inside = [x for x in bounds if lo < x < hi]
            pair = (
                k % 2 == 0 and hi <= metric.bar
                and lo + span not in bounds
                and all(((x - lo) / (span / 3)).denominator == 1 for x in inside)
            )
            groups.append((lo, 2 * span if pair else span))
            taken.update((k, k + 1) if pair else (k,))
    starts = [g[0] for g in groups]

    def group_at(p: Fraction) -> int | None:
        for index, (g, length) in enumerate(groups):
            if g <= p < g + length:
                return index
        return None

    atoms: list[Atom] = []
    for s, e, seg in pieces:
        written: list[Atom] = []
        p = s
        while p < e:
            index = group_at(p)
            if index is not None:
                g, length = groups[index]
                q = min(e, g + length)
                twelfth = length / 12
                a, b = (p - g) / twelfth, (q - g) / twelfth
                for x, y in _split_triplet(int(round(a)), int(round(b))):
                    written.append(Atom(
                        g + x * twelfth - shift, (y - x) * twelfth, TYPES[(y - x) * length / 8],
                        tuplet="inside", tuplet_unit=TYPES[length / 2], span=index,
                    ))
            else:
                q = min([e] + [t for t in starts if t > p])
                for x, y in metric.split(p, q, seg is None):
                    kind, dots = _notatable(y - x) or ("quarter", 0)
                    written.append(Atom(x - shift, y - x, kind, dots, hidden=seg is None and not fill))
            p = q
        if seg is not None:
            for i, atom in enumerate(written):
                atom.notes = seg.notes
                atom.tie_in = seg.tie_in or i > 0
                atom.tie_out = seg.tie_out or i < len(written) - 1
                atom.first = i == 0 and not seg.tie_in
        atoms.extend(written)

    for index in range(len(groups)):
        members = [a for a in atoms if a.span == index]
        if members:
            members[0].tuplet, members[-1].tuplet = "start", "stop"
    return atoms


def engrave(notes: list[Note], grid: Grid, meter: Meter) -> Layout:
    """Lay the piece out in bars, staves and voices."""
    beat, per_bar = meter.beat_ql, meter.beats_per_bar
    bar = meter.bar_ql
    metric = Metric(meter)
    span = beat if beat in (F(1, 2), F(1), F(2)) else None

    # Where does bar one start, and is there a pickup?
    first = min(n.pos for n in notes)
    bar_start = grid.phase + per_bar * math.floor((first - grid.phase) / per_bar)
    into = first - bar_start
    pickup = F(0)
    origin = F(bar_start)
    if into > 0 and into * 2 >= per_bar:
        origin = first if _binary(first * beat) else F(math.floor(first))
        pickup = (bar_start + per_bar - origin) * beat

    # Events: (staff, stream) → [(start, end, notes)] in quarter lengths from the origin.
    grouped: dict[tuple, list[Note]] = {}
    for n in notes:
        grouped.setdefault((n.hand, n.voice, n.pos), []).append(n)
    events: dict[tuple[int, int], list[tuple[Fraction, Fraction, list[Note]]]] = {}
    last = F(0)
    for (hand, voice, pos), chord in grouped.items():
        start = (pos - origin) * beat
        end = start + max(n.dur for n in chord) * beat
        events.setdefault((hand, voice), []).append((start, end, sorted(chord, key=lambda n: n.pitch)))
        last = max(last, end)

    # Bar boundaries.
    edges = [F(0)]
    if pickup:
        edges.append(pickup)
    while edges[-1] < last:
        edges.append(edges[-1] + bar)
    count = len(edges) - 1

    def bar_of(t: Fraction) -> int:
        if pickup:
            return 0 if t < pickup else 1 + int((t - pickup) // bar)
        return int(t // bar)

    cells: dict[tuple[int, int, int], list[_Segment]] = {}
    for (hand, voice), line in events.items():
        for start, end, chord in line:
            index = bar_of(start)
            while index < count and edges[index] < end:
                lo, hi = max(start, edges[index]), min(end, edges[index + 1])
                shift = bar - pickup if pickup and index == 0 else F(0)
                cells.setdefault((index, hand, voice), []).append(_Segment(
                    lo - edges[index] + shift, hi - edges[index] + shift, chord,
                    tie_in=lo > start, tie_out=hi < end,
                ))
                index += 1

    bars: list[Bar] = []
    for index in range(count):
        length = edges[index + 1] - edges[index]
        shift = bar - pickup if pickup and index == 0 else F(0)
        staves = []
        for hand in (RIGHT, LEFT):
            upper = cells.get((index, hand, 0), [])
            lower = cells.get((index, hand, 1), [])
            if upper and lower:
                voices = [
                    _voice_atoms(upper, shift, length, metric, span, fill=True),
                    _voice_atoms(lower, shift, length, metric, span, fill=False),
                ]
            else:
                voices = [_voice_atoms(upper or lower, shift, length, metric, span, fill=True)]
            staves.append(voices)
        bars.append(Bar(index if pickup else index + 1, length, staves))
    return Layout(meter, bars, origin, edges)
