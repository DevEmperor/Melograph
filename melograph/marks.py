"""Marks of expression, read from how the piece was played.

Everything here works on notes that already have their place in the bar
(`pos`, `dur`, `hand`, `voice`).  Positions are in beats of the tracked pulse,
like `Note.pos`; the exporter turns them into bars and offsets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np

from .beats import Grid
from .model import LEFT, RIGHT, Note, Pedal
from .spelling import Key, _name

F = Fraction

DYNAMICS = [(38, "pp"), (52, "p"), (64, "mp"), (78, "mf"), (94, "f"), (128, "ff")]


@dataclass
class PedalLine:
    start: Fraction
    end: Fraction
    changes: list[Fraction] = field(default_factory=list)


@dataclass
class Slur:
    hand: int
    first: Note
    last: Note


@dataclass
class Hairpin:
    start: Fraction
    end: Fraction
    crescendo: bool
    words: bool = False  # long ones are written "cresc." / "dim." instead of a wedge


@dataclass
class TempoMark:
    pos: Fraction
    bpm: float | None = None  # a new metronome mark (in tracked beats per minute)
    text: str | None = None  # "rit.", "a tempo", "accel."


@dataclass
class ChordName:
    pos: Fraction
    figure: str  # music21 chord symbol figure, e.g. "B-m7/F"


@dataclass
class Ottava:
    hand: int
    kind: str  # "8va" or "8vb"
    first: Note
    last: Note


@dataclass
class Marks:
    pedals: list[PedalLine] = field(default_factory=list)
    slurs: list[Slur] = field(default_factory=list)
    dynamics: list[tuple[Fraction, str]] = field(default_factory=list)
    hairpins: list[Hairpin] = field(default_factory=list)
    tempos: list[TempoMark] = field(default_factory=list)
    chords: list[ChordName] = field(default_factory=list)
    ottavas: list[Ottava] = field(default_factory=list)
    clefs: dict[int, list[str]] = field(default_factory=dict)  # hand → clef per bar ("G" or "F")
    swing: bool = False


def _events(notes: list[Note]) -> dict[tuple[int, int], list[list[Note]]]:
    """Chords per hand and voice, in order."""
    grouped: dict[tuple[int, int, Fraction], list[Note]] = {}
    for n in notes:
        grouped.setdefault((n.hand, n.voice, n.pos), []).append(n)
    lines: dict[tuple[int, int], list[list[Note]]] = {}
    for (hand, voice, _pos), chord in sorted(grouped.items(), key=lambda item: item[0][2]):
        lines.setdefault((hand, voice), []).append(sorted(chord, key=lambda n: n.pitch))
    return lines


def _onset_positions(notes: list[Note]) -> list[tuple[float, Fraction]]:
    """(time, position) of every attack, earliest time per position."""
    first: dict[Fraction, float] = {}
    for n in notes:
        first[n.pos] = min(first.get(n.pos, math.inf), n.onset)
    return sorted((t, p) for p, t in first.items())


# ── pedal ───────────────────────────────────────────────────────────────────


def pedal_lines(pedals: list[Pedal], notes: list[Note], grid: Grid) -> list[PedalLine]:
    """Where the sustain pedal goes down, changes and comes up, as positions in the bar.

    Pianists press the pedal just after the chord it is meant to hold and change
    it just after the next harmony is struck, so the marks are placed at the
    note the pedal belongs to rather than at the exact moment of the foot.
    """
    pedals = [p for p in pedals if p.end - p.start >= 0.12]
    if not pedals or not notes:
        return []
    attacks = _onset_positions(notes)
    times = [t for t, _ in attacks]

    def grid_position(t: float, steps: int) -> Fraction:
        return F(round(grid.beat_of(t) * steps), steps)

    def note_before(t: float, before: float, after: float) -> Fraction | None:
        lo, hi = np.searchsorted(times, t - before), np.searchsorted(times, t + after, side="right")
        return attacks[hi - 1][1] if hi > lo else None

    def nearest_note(t: float, reach: float) -> Fraction | None:
        lo, hi = np.searchsorted(times, t - reach), np.searchsorted(times, t + reach, side="right")
        if hi <= lo:
            return None
        return min(attacks[lo:hi], key=lambda a: abs(a[0] - t))[1]

    lines: list[PedalLine] = []
    current: PedalLine | None = None
    previous: Pedal | None = None
    for p in pedals:
        if current is not None and previous is not None and p.start - previous.end < 0.35:
            change = note_before(previous.end, 0.35, 0.1) or grid_position(previous.end, 2)
            last = current.changes[-1] if current.changes else current.start
            if change > last:
                current.changes.append(change)
            previous = p
            continue
        if current is not None and previous is not None:
            current.end = nearest_note(previous.end, 0.2) or grid_position(previous.end, 4)
            lines.append(current)
        start = note_before(p.start, 0.4, 0.06) or nearest_note(p.start, 0.2) or grid_position(p.start, 4)
        current, previous = PedalLine(start, start), p
    if current is not None and previous is not None:
        current.end = nearest_note(previous.end, 0.2) or grid_position(previous.end, 4)
        lines.append(current)

    tidy: list[PedalLine] = []
    for line in lines:
        line.changes = [c for c in line.changes if line.start < c < line.end]
        if line.end > line.start:
            if tidy and line.start <= tidy[-1].end:
                # Touching lines become one line with a change.
                tidy[-1].changes.append(line.start)
                tidy[-1].changes.extend(line.changes)
                tidy[-1].end = max(tidy[-1].end, line.end)
            else:
                tidy.append(line)
    return tidy


# ── slurs ───────────────────────────────────────────────────────────────────


def slurs(notes: list[Note], beats_per_bar: int, phase: int, pedals: list[Pedal] = ()) -> list[Slur]:
    """Slurs over the passages that were played legato.

    Legato on the piano means the next key goes down before (or just as) the
    last one comes up; the key releases tell that even under the pedal.  A long
    legato passage is divided into phrases at the places where a pianist
    breathes: a small gap, a longer note, a bar line, a leap.  Accompaniment
    figures of the left hand that lie under the pedal get no slurs: there the
    pedal binds the notes, and editions leave them plain.
    """
    found: list[Slur] = []
    longest = 2 * beats_per_bar

    def pedalled(run: list[list[Note]]) -> float:
        start = min(n.onset for n in run[0])
        end = max(n.offset for n in run[-1])
        if end <= start:
            return 0.0
        covered = sum(max(0.0, min(end, p.end) - max(start, p.start)) for p in pedals)
        return covered / (end - start)

    for (hand, _voice), events in _events(notes).items():
        runs: list[list[list[Note]]] = []
        run = [events[0]]
        for a, b in zip(events, events[1:]):
            if _legato(a, b):
                run.append(b)
            else:
                runs.append(run)
                run = [b]
        runs.append(run)
        for run in runs:
            if hand == LEFT and pedalled(run) >= 0.6:
                continue
            for phrase in _phrases(run, longest, beats_per_bar, phase):
                if len(phrase) >= 3:
                    found.append(Slur(hand, phrase[0][0], phrase[-1][0]))
    return found


def _legato(a: list[Note], b: list[Note]) -> bool:
    if any(n.staccato for n in a) or any(n.staccato for n in b):
        return False
    written_end = a[0].pos + max(n.dur for n in a)
    if written_end < b[0].pos:
        return False  # a rest lies between them
    start_a = min(n.onset for n in a)
    start_b = min(n.onset for n in b)
    release = max(n.offset for n in a)
    gap = start_b - release
    return gap <= max(0.035, 0.12 * (start_b - start_a))


def _phrases(run: list[list[Note]], longest: int, per_bar: int, phase: int) -> list[list[list[Note]]]:
    span = float(run[-1][0].pos - run[0][0].pos)
    if span <= longest or len(run) < 6:
        return [run]
    starts = [min(n.onset for n in e) for e in run]
    iois = [b - a for a, b in zip(starts, starts[1:])]
    typical = float(np.median(iois)) if iois else 1.0
    best, best_score = None, -math.inf
    for i in range(2, len(run) - 2):  # cut between run[i-1] and run[i]; each side keeps 2 or more
        a, b = run[i - 1], run[i]
        release = max(n.offset for n in a)
        gap = max(0.0, starts[i] - release) / max(iois[i - 1], 1e-6)
        score = 2.0 * min(gap, 1.0)
        score += 1.0 if iois[i - 1] >= 1.5 * typical else 0.0
        where = (b[0].pos - phase) % per_bar
        score += 0.8 if where == 0 else 0.4 if per_bar % 2 == 0 and where == per_bar // 2 else 0.0
        score += 0.05 * min(abs(b[-1].pitch - a[-1].pitch), 12)
        # Prefer halves of similar length.
        left, right = float(b[0].pos - run[0][0].pos), float(run[-1][0].pos - b[0].pos)
        score -= 0.3 * abs(left - right) / span
        if score > best_score:
            best, best_score = i, score
    if best is None:
        return [run]
    return _phrases(run[:best], longest, per_bar, phase) + _phrases(run[best:], longest, per_bar, phase)


# ── clefs and octave lines ──────────────────────────────────────────────────


def clefs(notes: list[Note], bar_of, bars: int) -> dict[int, list[str]]:
    """The clef of each staff in each bar, with a little inertia so it does not flicker."""
    plan: dict[int, list[str]] = {}
    for hand in (RIGHT, LEFT):
        pitches: list[list[int]] = [[] for _ in range(bars)]
        for n in notes:
            if n.hand == hand:
                pitches[bar_of(n.pos)].append(n.pitch)
        home = "G" if hand == RIGHT else "F"
        other = "F" if hand == RIGHT else "G"
        states: list[str] = []
        current = None
        for index, bar in enumerate(pitches):
            if not bar:
                states.append(current or home)
                continue
            median, low, high = float(np.median(bar)), min(bar), max(bar)
            # A few notes around middle C do not justify a change; a register that lasts does.
            if hand == LEFT:
                away = median >= 64 and low >= 57
                strong = low >= 67 and len(bar) >= 2
                back = low < 55 or median < 60
            else:
                away = median <= 53 and high <= 59
                strong = high <= 50 and len(bar) >= 2
                back = high > 64 or median > 60
            nxt = next((p for p in pitches[index + 1:index + 2] if p), None)
            if hand == LEFT:
                next_away = nxt is not None and float(np.median(nxt)) >= 64 and min(nxt) >= 57
            else:
                next_away = nxt is not None and float(np.median(nxt)) <= 53 and max(nxt) <= 59
            if current is None:
                current = other if (strong or (away and next_away)) else home
            elif current == home and (strong or (away and next_away)):
                current = other
            elif current == other and back:
                current = home
            states.append(current)
        plan[hand] = states
    return plan


def ottavas(notes: list[Note], plan: dict[int, list[str]], bar_of) -> list[Ottava]:
    """8va over passages far above a treble staff, 8vb under ones far below a bass staff.

    Sets `shift` on the notes inside: they are written an octave nearer the staff.
    """
    found: list[Ottava] = []
    for hand in (RIGHT, LEFT):
        chords: dict[Fraction, list[Note]] = {}
        for n in notes:
            if n.hand == hand:
                chords.setdefault(n.pos, []).append(n)
        events = [chords[p] for p in sorted(chords)]
        for kind in ("8va", "8vb"):
            clef = "G" if kind == "8va" else "F"
            run: list[list[Note]] = []

            def close() -> None:
                if not run:
                    return
                pitches = [n.pitch for e in run for n in e]
                if kind == "8va":
                    good = (len(run) >= 4 and max(pitches) >= 91) or (len(run) >= 8 and float(np.median(pitches)) >= 86)
                else:
                    good = len(run) >= 3 and min(pitches) <= 33
                if good:
                    for e in run:
                        for n in e:
                            n.shift = -1 if kind == "8va" else 1
                    first = min(run[0], key=lambda n: n.pitch)
                    found.append(Ottava(hand, kind, first, run[-1][0]))
                run.clear()

            for event in events:
                low, high = min(n.pitch for n in event), max(n.pitch for n in event)
                inside = plan[hand][bar_of(event[0].pos)] == clef and (
                    low >= 84 if kind == "8va" else high <= 38
                )
                if inside and not any(n.shift for n in event):
                    run.append(event)
                else:
                    close()
            close()
    return found


# ── articulation ────────────────────────────────────────────────────────────


def accents(notes: list[Note]) -> None:
    """Accents on the few notes that were struck clearly harder than everything around them."""
    for hand in (RIGHT, LEFT):
        mine = sorted((n for n in notes if n.hand == hand), key=lambda n: n.onset)
        if len(mine) < 8:
            continue
        onsets = np.array([n.onset for n in mine])
        velocities = np.array([n.velocity for n in mine])
        candidates: list[tuple[float, Note]] = []
        for i, n in enumerate(mine):
            lo, hi = np.searchsorted(onsets, n.onset - 2.0), np.searchsorted(onsets, n.onset + 2.0)
            around = np.concatenate([velocities[lo:i], velocities[i + 1:hi]])
            if len(around) < 4:
                continue
            excess = n.velocity - float(np.median(around))
            if excess >= 20 and n.velocity >= 72:
                candidates.append((excess, n))
        limit = max(1, int(0.06 * len(mine)))
        for _, n in sorted(candidates, key=lambda c: -c[0])[:limit]:
            n.accent = True


def fermatas(notes: list[Note], grid: Grid) -> None:
    """A fermata where the music stops for a moment: a beat stretched to well over its length,
    and on the last chord when it is held clearly longer than written."""
    if not notes:
        return
    times = grid.times
    last_onset = max(n.onset for n in notes)
    ibi = np.diff(times)
    for k in range(len(ibi)):
        if times[k] > last_onset:
            break
        around = np.concatenate([ibi[max(0, k - 4):k], ibi[k + 1:k + 5]])
        if len(around) >= 3 and ibi[k] >= 1.7 * float(np.median(around)) and ibi[k] > 0.5:
            sounding = [n for n in notes if n.pos <= k < n.pos + n.dur]
            if sounding:
                start = max(n.pos for n in sounding)
                for n in sounding:
                    if n.pos == start:
                        n.fermata = True
    final = max(n.pos for n in notes)
    chord = [n for n in notes if n.pos == final]
    written_end = grid.time_of(float(final + max(n.dur for n in chord)))
    if max(n.sustain_end for n in chord) >= written_end + 0.6 * grid.beat_seconds(int(final)):
        for n in chord:
            n.fermata = True


# ── dynamics ────────────────────────────────────────────────────────────────


def _level(velocity: float) -> int:
    return next(i for i, (limit, _) in enumerate(DYNAMICS) if velocity < limit)


def dynamics(notes: list[Note], beats_per_bar: int, hairpins: bool = True) -> tuple[list[tuple[Fraction, str]], list[Hairpin]]:
    """Dynamic marks and crescendo/diminuendo hairpins from how hard the keys were struck.

    The loudness of the leading voice is followed beat by beat and smoothed; a
    hairpin stands where it rises or falls clearly over a bar or more, a new
    mark where it settles on a different level.
    """
    if not notes:
        return [], []
    first = int(math.floor(min(n.pos for n in notes)))
    last = int(math.floor(max(n.pos for n in notes)))
    count = last - first + 1
    level = np.full(count, np.nan)
    for k in range(count):
        here = [n for n in notes if int(math.floor(n.pos)) == first + k]
        if not here:
            continue
        lead = [n.velocity for n in here if n.hand == RIGHT] or [n.velocity for n in here]
        level[k] = float(np.percentile(lead, 75))
    known = np.flatnonzero(~np.isnan(level))
    level = np.interp(np.arange(count), known, level[known])
    sigma = max(1.0, beats_per_bar / 2)
    kernel = np.exp(-0.5 * (np.arange(-3 * sigma, 3 * sigma + 1) / sigma) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(level, len(kernel) // 2, mode="edge")
    smooth = np.convolve(padded, kernel, mode="valid")[:count]

    positions = sorted({n.pos for n in notes if n.hand == RIGHT} or {n.pos for n in notes})

    def snap(beat: int, after: bool = False) -> Fraction:
        target = F(first + beat)
        if after:
            later = [p for p in positions if p >= target]
            return later[0] if later else target
        return min(positions, key=lambda p: abs(p - target))

    # Turning points with a clear rise or fall in between.
    turns = [0]
    direction = 0
    for k in range(1, count):
        step = smooth[k] - smooth[k - 1]
        if abs(step) < 1e-6:
            continue
        sign = 1 if step > 0 else -1
        if direction and sign != direction:
            turns.append(k - 1)
        direction = sign
    turns.append(count - 1)
    extrema = [turns[0]]
    for k in turns[1:]:
        if abs(smooth[k] - smooth[extrema[-1]]) >= 8 or k == turns[-1]:
            extrema.append(k)

    marks: list[tuple[Fraction, str]] = []
    pins: list[Hairpin] = []
    start_level = _level(float(np.mean(smooth[:beats_per_bar])))
    marks.append((min(positions), DYNAMICS[start_level][1]))
    current = start_level
    last_mark = 0
    for a, b in zip(extrema, extrema[1:]):
        delta = float(smooth[b] - smooth[a])
        if abs(delta) < 12:
            continue
        length = b - a
        if hairpins and length >= beats_per_bar and (not pins or snap(a) >= pins[-1].end):
            start, end = snap(a), snap(b)
            if end > start:
                pins.append(Hairpin(start, end, delta > 0, words=length > 6 * beats_per_bar))
        settled = _level(float(np.mean(smooth[b:b + beats_per_bar])))
        if settled != current and b - last_mark >= beats_per_bar:
            marks.append((snap(b, after=True), DYNAMICS[settled][1]))
            current, last_mark = settled, b
    return marks, pins


# ── tempo ───────────────────────────────────────────────────────────────────


def tempo_marks(notes: list[Note], grid: Grid) -> list[TempoMark]:
    """The tempo at the start, new tempos for longer sections, and rit./a tempo/accel. in between."""
    per_bar, phase = grid.beats_per_bar, grid.phase
    first = min(n.pos for n in notes)
    last = max(n.pos for n in notes)
    start = phase + per_bar * math.floor((first - phase) / per_bar)
    bars: list[tuple[int, float]] = []  # (first beat, tempo)
    b = start
    while b <= last:
        lo, hi = max(b, math.floor(first)), b + per_bar
        seconds = grid.time_of(hi) - grid.time_of(lo)
        if hi - lo >= 1 and seconds > 0:
            bars.append((b, 60.0 * (hi - lo) / seconds))
        b += per_bar
    if not bars:
        return []
    tempos = np.array([t for _, t in bars])
    current = float(np.median(tempos[:8]))
    marks = [TempoMark(F(first), bpm=current)]
    i = 1
    while i < len(bars):
        ratio = tempos[i] / current
        # A new section: four bars or more, steady, clearly faster or slower.
        section = tempos[i:i + 4]
        if len(section) == 4:
            median = float(np.median(section))
            steady = np.all(np.abs(section / median - 1) <= 0.06)
            if steady and abs(median / current - 1) >= 0.1:
                current = median
                marks.append(TempoMark(F(bars[i][0]), bpm=current))
                i += 4
                continue
        # Slowing down (or speeding up) for one to three bars.
        if ratio <= 0.86 or ratio >= 1.16:
            slower = ratio <= 0.86
            k = i
            while k < len(bars) and k < i + 3 and ((tempos[k] / current <= 0.9) if slower else (tempos[k] / current >= 1.1)):
                k += 1
            marks.append(TempoMark(F(bars[i][0]), text="rit." if slower else "accel."))
            if k < len(bars) and abs(tempos[k] / current - 1) <= 0.07:
                marks.append(TempoMark(F(bars[k][0]), text="a tempo"))
            i = k + 1
            continue
        i += 1
    return marks


# ── chord symbols ───────────────────────────────────────────────────────────

# (suffix, intervals, complexity) – the suffix in music21's chord symbol notation
TEMPLATES = [
    ("", (0, 4, 7), 0.0), ("m", (0, 3, 7), 0.0),
    ("7", (0, 4, 7, 10), 0.05), ("maj7", (0, 4, 7, 11), 0.06), ("m7", (0, 3, 7, 10), 0.05),
    ("dim", (0, 3, 6), 0.1), ("m7b5", (0, 3, 6, 10), 0.1), ("dim7", (0, 3, 6, 9), 0.12),
    # Without a third a chord is "sus" only when the third is really missing, not merely quiet.
    ("+", (0, 4, 8), 0.14), ("sus4", (0, 5, 7), 0.2), ("sus2", (0, 2, 7), 0.22),
    ("6", (0, 4, 7, 9), 0.1), ("m6", (0, 3, 7, 9), 0.1), ("add9", (0, 2, 4, 7), 0.18),
]


def _pitch_name(pc: int, key: Key) -> str:
    centre = key.fifths + (3 if key.minor else 1)
    position = (pc * 7) % 12
    position += 12 * round((centre - position) / 12)
    step, alter = _name(position)
    return step + ("#" * alter if alter > 0 else "-" * -alter)


def chord_symbols(notes: list[Note], key: Key, beats_per_bar: int, phase: int) -> list[ChordName]:
    """Chord names above the music, for players who read lead sheets."""
    if not notes:
        return []
    # Harmony is read in steps of half a bar (a whole bar in triple time): fine enough for
    # most music, coarse enough not to name every passing note of the tune.
    unit = beats_per_bar // 2 if beats_per_bar % 2 == 0 else beats_per_bar
    opening = min(n.pos for n in notes)
    first = phase + beats_per_bar * math.floor((opening - phase) / beats_per_bar)
    last = int(math.ceil(max(n.pos + n.dur for n in notes)))
    count = max(1, math.ceil((last - first) / unit))
    weights = np.zeros((count, 12))
    bass = np.full(count, -1)
    for n in notes:
        start, end = float(n.pos), float(n.pos + n.dur)
        # The tune passes through notes outside the chord; the accompaniment spells it out.
        melody = 0.55 if n.hand == RIGHT and n.voice == 0 else 1.0
        for k in range(max(0, int((start - first) // unit)), min(count, int(math.ceil((end - first) / unit)))):
            overlap = min(end, first + (k + 1) * unit) - max(start, first + k * unit)
            if overlap > 0:
                weights[k, n.pitch % 12] += overlap * (0.4 + n.velocity / 127) * melody
    for k in range(count):
        lo, hi = first + k * unit, first + (k + 1) * unit
        sounding = [n.pitch for n in notes if n.pos < lo + unit / 2 and n.pos + n.dur > lo] or \
                   [n.pitch for n in notes if lo <= n.pos < hi]
        if sounding:
            bass[k] = min(sounding) % 12
            weights[k, bass[k]] *= 1.3

    names = [(root, suffix, set((root + i) % 12 for i in intervals), cost)
             for root in range(12) for suffix, intervals, cost in TEMPLATES]
    # Chords made of the notes of the key are the likelier reading when the music is ambiguous.
    scale = {0, 2, 3, 5, 7, 8, 10, 11} if key.minor else {0, 2, 4, 5, 7, 9, 11}
    home = {(key.tonic + i) % 12 for i in scale}
    emission = np.full((count, len(names) + 1), -1.0)
    for k in range(count):
        total = weights[k].sum()
        distinct = int(np.sum(weights[k] >= 0.12 * total)) if total > 0 else 0
        if total < 0.3 or distinct < 3:
            # Too little sound to name a chord: keep the one before (or none at the start).
            emission[k, :] = -0.15
            emission[k, -1] = 0.0
            continue
        for j, (root, _suffix, members, cost) in enumerate(names):
            inside = sum(weights[k, pc] for pc in members)
            emission[k, j] = (inside - 0.7 * (total - inside)) / total - cost
            if bass[k] == root:
                emission[k, j] += 0.12
            if members <= home:
                emission[k, j] += 0.06
        emission[k, -1] = -0.2

    # Viterbi: a new chord costs a little, a little more in the middle of a bar.
    states = emission.shape[1]
    score = emission[0].copy()
    back = np.zeros((count, states), dtype=int)
    for k in range(1, count):
        change = 0.25 if (k * unit) % beats_per_bar == 0 else 0.4
        best_prev = int(np.argmax(score))
        stay = score
        move = score[best_prev] - change
        back[k] = np.where(stay >= move, np.arange(states), best_prev)
        score = np.maximum(stay, move) + emission[k]
    path = [int(np.argmax(score))]
    for k in range(count - 1, 0, -1):
        path.append(back[k, path[-1]])
    path.reverse()

    result: list[ChordName] = []
    previous = None
    for k, state in enumerate(path):
        if state == previous:
            continue
        previous = state
        if state == len(names):
            continue
        root, suffix, _members, _cost = names[state]
        figure = _pitch_name(root, key) + suffix
        if bass[k] >= 0 and bass[k] != root:
            figure += "/" + _pitch_name(int(bass[k]), key)
        result.append(ChordName(max(F(first + k * unit), opening), figure))
    return result
