"""Pulse, bars and metre.

Beat This! (Foscarin, Schlüter & Widmer, ISMIR 2024) listens to the recording
and says, fifty times a second, how likely a beat and a downbeat are.  Its own
list of beats is not used: in music with tempo changes it switches between
counting levels (quarters here, halves there) and doubles beats.  Instead the
probabilities are read here together with the notes that were played:

1. a tempo curve – which pulse the music has at every moment, kept on one
   counting level through the piece while following real changes of tempo;
2. the beats – placed along that curve where the evidence is;
3. the bars – bar lines where the downbeats are, a bar at a time, so that a
   change of metre or one odd bar does not push everything after it off the
   beat.  Beats that only fill a pause are taken out again: a fermata is one
   long beat, not a row of empty ones.

Without a recording (MIDI input) the pulse comes from the note onsets alone.
"""

from __future__ import annotations

import os
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import numpy as np

from .model import Meter, Note, Performance

FPS = 100  # resolution of the evidence curves in frames per second
TRACKER_FPS = 50  # Beat This! works at 50 frames per second


@dataclass
class Tracked:
    """What the beat tracker heard: the probability of a beat and of a downbeat, frame by frame."""

    beat: np.ndarray
    downbeat: np.ndarray
    # Grids already worked out from this (the same recording is set again and again with other options).
    grids: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class Grid:
    times: np.ndarray  # one entry per beat, strictly increasing
    beats_per_bar: int  # of most bars
    phase: int  # beat at which the first bar starts
    source: str  # "audio" or "notes"
    downbeat_confidence: float = 0.0
    starts: list[int] = field(default_factory=list)  # beat index of every bar line, including the closing one
    meters: list[Meter] = field(default_factory=list)  # the written metre of every bar

    def __post_init__(self):
        if not self.starts:  # regular bars from phase and length
            first = self.phase % self.beats_per_bar
            self.starts = list(range(first, len(self.times) + self.beats_per_bar, self.beats_per_bar))
            if first:
                self.starts.insert(0, first - self.beats_per_bar)

    @property
    def bpm(self) -> float:
        return 60.0 / float(np.median(np.diff(self.times)))

    @property
    def bars(self) -> int:
        return len(self.starts) - 1

    def bar_at(self, beat: float) -> int:
        """Index of the bar that contains this beat position."""
        return max(0, min(self.bars - 1, bisect_right(self.starts, beat) - 1))

    def bar_start(self, index: int) -> int:
        return self.starts[index]

    def bar_length(self, index: int) -> int:
        return self.starts[index + 1] - self.starts[index]

    def bar_end(self, beat: float) -> int:
        """The bar line after this beat position."""
        return self.starts[self.bar_at(beat) + 1]

    def meter_at(self, beat: float) -> Meter:
        index = self.bar_at(beat)
        if self.meters:
            return self.meters[index]
        length = self.bar_length(index)
        return Meter(length, Fraction(1), length, 4)

    def beat_of(self, seconds: float) -> float:
        """Continuous beat index of a moment in time."""
        t = self.times
        if seconds <= t[0]:
            return (seconds - t[0]) / (t[1] - t[0])
        if seconds >= t[-1]:
            return len(t) - 1 + (seconds - t[-1]) / (t[-1] - t[-2])
        k = int(np.searchsorted(t, seconds, side="right")) - 1
        return k + (seconds - t[k]) / (t[k + 1] - t[k])

    def time_of(self, beat: float) -> float:
        t = self.times
        if beat <= 0:
            return t[0] + beat * (t[1] - t[0])
        if beat >= len(t) - 1:
            return t[-1] + (beat - (len(t) - 1)) * (t[-1] - t[-2])
        k = int(beat)
        return t[k] + (beat - k) * (t[k + 1] - t[k])

    def beat_seconds(self, k: int) -> float:
        t = self.times
        k = max(0, min(len(t) - 2, k))
        return float(t[k + 1] - t[k])


# ── tracking ────────────────────────────────────────────────────────────────


def beat_model() -> str:
    """The Beat This! checkpoint: shipped with a packaged Melograph, else fetched once by name."""
    bundled = os.environ.get("MELOGRAPH_BEAT_MODEL")
    return bundled if bundled and os.path.isfile(bundled) else "final0"


def beat_model_ready() -> bool:
    """Whether the beat model is already on this computer (otherwise the first run downloads it)."""
    if beat_model() != "final0":
        return True
    try:
        import torch

        return any((Path(torch.hub.get_dir()) / "checkpoints").glob("beat_this-final0*"))
    except Exception:
        return True


def track_audio(audio: np.ndarray, sample_rate: int, device: str) -> Tracked:
    """Beat and downbeat probabilities of a recording, 50 frames per second."""
    import torch
    from beat_this.inference import Audio2Frames

    tracker = Audio2Frames(checkpoint_path=beat_model(), device=device)
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    with torch.no_grad():
        beat, downbeat = tracker(mono, sample_rate)

    def probability(logits) -> np.ndarray:
        values = logits.float().cpu().numpy().astype(np.float64)
        return (1.0 / (1.0 + np.exp(-values))).astype(np.float32)

    return Tracked(probability(beat), probability(downbeat))


def track_notes(performance: Performance) -> np.ndarray:
    """Beat times from the note onsets alone (dynamic programming after Ellis 2007)."""
    fps = 100
    notes = performance.notes
    length = int((max(n.onset for n in notes) + 3.0) * fps)
    envelope = np.zeros(length)
    for n in notes:
        envelope[int(round(n.onset * fps))] += 0.4 + n.velocity / 127
    kernel = np.exp(-0.5 * (np.arange(-6, 7) / 2.0) ** 2)
    envelope = np.convolve(envelope, kernel, mode="same")
    envelope /= envelope.std() + 1e-9

    lags = np.arange(int(0.3 * fps), int(1.5 * fps) + 1)
    correlation = np.array([np.dot(envelope[:-lag], envelope[lag:]) for lag in lags])
    prior = np.exp(-0.5 * (np.log2(lags / fps / 0.6) / 0.9) ** 2)
    period = int(lags[int(np.argmax(correlation * prior))])

    score = envelope.copy()
    back = np.full(length, -1)
    for t in range(length):
        low, high = max(0, t - 2 * period), t - period // 2
        if high <= low:
            continue
        previous = np.arange(low, high)
        values = score[previous] - 100.0 * np.log((t - previous) / period) ** 2
        best = int(np.argmax(values))
        score[t] = envelope[t] + values[best]
        back[t] = previous[best]
    t = length - period + int(np.argmax(score[length - period:]))
    beats = []
    while t >= 0:
        beats.append(t / fps)
        t = back[t]
    return np.array(beats[::-1])


# ── the pulse of a recording ────────────────────────────────────────────────

PERIODS = 0.24 * 2 ** (np.arange(0, 2.75, 1 / 24))  # 0.24 s … 1.6 s (250 … 37 per minute), 24 steps to the octave
HEARD = 0.35  # a beat probability from here on counts as a beat that is really there
WINDOW = 3.0  # seconds to each side over which a tempo is judged
HOP = 0.5  # seconds between two judgements
EVIDENCE = 0.2  # weight of how well a tempo fits, against the cost of changing it
SKIPPED = 1.25  # how much beats that a pulse steps over count against it
CHANGE = 1.2  # cost of changing the tempo by an octave
STEP = 0.08  # and of changing it at all (one step, not a ramp of many)
USUAL = 0.05  # pull towards a pulse of two beats a second, which decides between otherwise equal levels
TIGHT = 8.0  # how closely the beats keep to the tempo curve


def _smooth(values: np.ndarray, sigma: float) -> np.ndarray:
    reach = int(3 * sigma) + 1
    kernel = np.exp(-0.5 * (np.arange(-reach, reach + 1) / sigma) ** 2)
    return np.convolve(values, kernel / kernel.sum(), mode="same")


def _curve(probability: np.ndarray, length: int | None = None) -> np.ndarray:
    """A tracker curve at FPS. The tracker often marks one beat as two peaks a few frames apart; smoothing joins them."""
    joined = _smooth(np.asarray(probability, dtype=float), 1.5)
    count = length or int(len(joined) * FPS / TRACKER_FPS)
    return np.interp(np.arange(count) / FPS, np.arange(len(joined)) / TRACKER_FPS, joined, right=0.0)


def onset_clusters(notes: list[Note]) -> list[tuple[float, float]]:
    """Notes struck together, as (time, weight)."""
    clusters: list[tuple[float, float]] = []
    group: list[Note] = []
    for n in sorted(notes, key=lambda n: n.onset):
        if group and (n.onset - group[-1].onset > 0.03 or n.onset - group[0].onset > 0.07):
            clusters.append((float(np.median([g.onset for g in group])), sum(g.velocity for g in group) / 64))
            group = []
        group.append(n)
    if group:
        clusters.append((float(np.median([g.onset for g in group])), sum(g.velocity for g in group) / 64))
    return clusters


def _onset_curve(notes: list[Note], length: int) -> np.ndarray:
    """Where notes begin, 0 … 1: a chord counts a little more than a single note."""
    curve = np.zeros(length)
    for time, weight in onset_clusters(notes):
        i = int(round(time * FPS))
        if 0 <= i < length:
            curve[i] = max(curve[i], min(1.0, 0.45 + 0.2 * weight))
    kernel = np.exp(-0.5 * (np.arange(-6, 7) / 2.0) ** 2)
    return np.minimum(1.0, np.convolve(curve, kernel, mode="same"))


def _tempo_curve(evidence: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The beat period over time: (times of the judgements, period in seconds at each)."""
    count = len(evidence)
    # A pulse may pass up to 30 ms beside the evidence: nobody plays like a metronome.
    wide = np.maximum.reduce([np.roll(evidence, shift) for shift in range(-3, 4)])
    centres = np.arange(0, count / FPS, HOP)
    fit = np.zeros((len(centres), len(PERIODS)))
    half = int(WINDOW * FPS)
    for w, centre in enumerate(centres):
        lo, hi = max(0, int(centre * FPS) - half), min(count, int(centre * FPS) + half)
        part = wide[lo:hi]
        if len(part) < FPS:
            continue
        for p, period in enumerate(PERIODS):
            frames = period * FPS
            pulses = int(len(part) / frames)
            if pulses < 2:
                continue
            index = np.arange(0, frames, 2.0)[:, None] + frames * np.arange(pulses)[None, :]
            on = np.clip(np.round(index).astype(int), 0, len(part) - 1)
            between = np.clip(np.round(index + frames / 2).astype(int), 0, len(part) - 1)
            # What the pulse collects – less what it steps over: when there is nearly as much
            # half-way between its beats as on them, it is too slow (a waltz at 180 is not
            # counted at 90).  Off-beat notes, which are weaker, do not count against it.
            hit, missed = part[on].mean(axis=1), part[between].mean(axis=1)
            fit[w, p] = (hit - SKIPPED * np.maximum(0.0, missed - 0.8 * hit)).max()  # the best phase

    emission = EVIDENCE * fit - USUAL * np.log2(PERIODS / 0.5)[None, :] ** 2
    change = CHANGE * np.abs(np.log2(PERIODS[:, None] / PERIODS[None, :]))
    change += STEP * (change > 0)
    score = emission[0].copy()
    back = np.zeros(emission.shape, dtype=int)
    states = np.arange(len(PERIODS))
    for w in range(1, len(emission)):
        total = score[None, :] - change  # [new, old]
        back[w] = np.argmax(total, axis=1)
        score = total[states, back[w]] + emission[w]
    path = [int(np.argmax(score))]
    for w in range(len(emission) - 1, 0, -1):
        path.append(int(back[w][path[-1]]))
    path.reverse()
    return centres, PERIODS[np.array(path)]


def _place_beats(evidence: np.ndarray, centres: np.ndarray, periods: np.ndarray) -> np.ndarray:
    """Beat times along the tempo curve, each where the evidence is strongest (after Ellis 2007)."""
    count = len(evidence)
    period = np.interp(np.arange(count) / FPS, centres, periods) * FPS
    score = evidence.copy()
    back = np.full(count, -1)
    for t in range(count):
        lo, hi = max(0, int(t - 2.0 * period[t])), int(t - 0.5 * period[t])
        if hi <= lo:
            continue
        previous = np.arange(lo, hi)
        values = score[previous] - TIGHT * np.log((t - previous) / period[t]) ** 2
        best = int(np.argmax(values))
        score[t] = evidence[t] + values[best]
        back[t] = previous[best]
    last = max(1, int(period[-1]))
    t = count - last + int(np.argmax(score[count - last:]))
    beats = []
    while t >= 0:
        beats.append(t / FPS)
        t = back[t]
    return np.array(beats[::-1])


def find_beats(tracked: Tracked, notes: list[Note]) -> np.ndarray:
    """Beat times of a recording, from the tracker's probabilities and the notes that were played."""
    heard = _curve(tracked.beat)
    onsets = _onset_curve(notes, len(heard))
    # For the tempo a weak beat counts almost like a strong one: where the tracker counts
    # half notes, the quarters in between are still faintly there, and they are the pulse.
    centres, periods = _tempo_curve(np.maximum(np.minimum(1.0, heard / HEARD), 0.5 * onsets))
    return _place_beats(heard + 0.5 * onsets, centres, periods)


# ── tidying beats ───────────────────────────────────────────────────────────


def _regularise(beats: np.ndarray) -> np.ndarray:
    """Drop doubled beats and fill in skipped ones (for beats that are given as a list)."""
    beats = np.unique(np.round(beats, 4))
    if len(beats) < 4:
        return beats
    overall = float(np.median(np.diff(beats)))
    out = [float(beats[0])]
    for b in beats[1:]:
        # The local beat never strays far from the overall one, so a run of doubled
        # beats cannot talk the next gaps into being "skipped" ones.
        local = float(np.median(np.diff(out[-6:]))) if len(out) >= 4 else overall
        local = min(max(local, 0.6 * overall), 1.7 * overall)
        gap = b - out[-1]
        if gap < 0.55 * local:
            continue
        parts = int(round(gap / local))
        if 2 <= parts <= 4 and abs(gap / parts - local) < 0.3 * local:
            start = out[-1]
            out.extend(start + gap * i / parts for i in range(1, parts))
        out.append(float(b))
    return np.array(out)


def _snap_to_onsets(beats: np.ndarray, notes: list[Note]) -> np.ndarray:
    """Move each beat onto the chord that was played on it, if there is one close by."""
    clusters = onset_clusters(notes)
    if not clusters:
        return beats
    times = np.array([c[0] for c in clusters])
    snapped = beats.copy()
    for i, b in enumerate(beats):
        span = beats[min(i + 1, len(beats) - 1)] - beats[max(i - 1, 0)]
        ibi = span / (2 if 0 < i < len(beats) - 1 else 1)
        tolerance = min(0.07, 0.11 * ibi)
        j = int(np.argmin(np.abs(times - b)))
        if abs(times[j] - b) <= tolerance:
            snapped[i] = times[j]
    # Never let snapping reorder or crush beats.
    for i in range(1, len(snapped)):
        if snapped[i] - snapped[i - 1] < 0.5 * (beats[i] - beats[i - 1]):
            snapped[i] = beats[i]
    return snapped


def _beat_salience(times: np.ndarray, notes: list[Note]) -> np.ndarray:
    """How strongly each beat is marked by the playing (bass notes and long notes count most)."""
    salience = np.zeros(len(times))
    lowest = np.full(len(times), np.inf)
    for n in notes:
        i = int(np.argmin(np.abs(times - n.onset)))
        left = times[i] - times[i - 1] if i > 0 else times[1] - times[0]
        if abs(times[i] - n.onset) > 0.2 * left:
            continue
        low = 1.0 + max(0, 60 - n.pitch) / 18.0
        long = 1.0 + min(n.sustain_end - n.onset, 2.0) / 2.0
        salience[i] += (n.velocity / 100.0) * low * long
        lowest[i] = min(lowest[i], n.pitch)
    # The bass note of a bar: clearly lower than what is played just before and after.
    played = salience[salience > 0]
    bonus = 1.5 * float(np.median(played)) if len(played) else 0.0
    for i in range(len(times)):
        before = lowest[i - 1] if i > 0 else np.inf
        after = lowest[i + 1] if i + 1 < len(times) else np.inf
        if np.isfinite(lowest[i]) and lowest[i] <= min(before, after) - 3:
            salience[i] += bonus

    # Harmony tends to change on "one".
    return salience + 2.0 * bonus * _harmony_change(times, notes, 2)


def _harmony_change(times: np.ndarray, notes: list[Note], span: int) -> np.ndarray:
    """How much the notes change at each beat: the `span` beats before it against the `span` from it on (0 … 1)."""
    chroma = np.zeros((len(times), 12))
    for n in notes:
        i = int(np.searchsorted(times, n.onset + 0.05, side="right")) - 1
        if 0 <= i < len(times):
            chroma[i, n.pitch % 12] += 1.0
    change = np.zeros(len(times))
    for i in range(span, len(times) - span + 1):
        before, after = chroma[i - span:i].sum(axis=0), chroma[i:i + span].sum(axis=0)
        size = float(np.linalg.norm(before) * np.linalg.norm(after))
        if size > 0:
            change[i] = 1.0 - float(before @ after) / size
    return change


def _sounding(times: np.ndarray, notes: list[Note]) -> np.ndarray:
    """For every beat: does a note begin in it (from just before the beat to just before the next)?"""
    onsets = np.sort(np.array([n.onset for n in notes]))
    result = np.zeros(len(times), dtype=bool)
    for i in range(len(times)):
        following = times[i + 1] if i + 1 < len(times) else times[i] + (times[i] - times[i - 1])
        early = 0.15 * (following - times[i])
        lo = np.searchsorted(onsets, times[i] - early)
        hi = np.searchsorted(onsets, following - early)
        result[i] = hi > lo
    return result


# ── bars ────────────────────────────────────────────────────────────────────

LENGTHS = (2, 3, 4)  # beats a bar may have
BAR_LINE = 0.35  # a beat has to look this much like a downbeat to earn a bar line
METRE_CHANGE = 1.2  # cost of a bar that is not as long as the one before
SHORT_BAR = 1.4  # seconds: shorter bars than this are unusual (2/4 at a quick tempo is nearly always 4/4)


def _downbeat_evidence(times: np.ndarray, notes: list[Note], tracked: Tracked | None, given: np.ndarray | None) -> np.ndarray:
    """How much every beat looks like the first of a bar, 0 … 1."""
    salience = _beat_salience(times, notes)
    top = float(np.percentile(salience, 90)) if len(salience) else 0.0
    salience = np.minimum(1.0, salience / top) if top > 0 else np.zeros(len(times))
    if tracked is not None:
        curve = _curve(tracked.downbeat)
        heard = np.zeros(len(times))
        for i, t in enumerate(times):
            frame = int(round(t * FPS))
            around = curve[max(0, frame - 5):max(0, frame + 6)]
            heard[i] = float(around.max()) if len(around) else 0.0
        # The tracker may be unsure and still be right: what counts is how a beat stands out
        # among the beats around it.
        level = np.array([
            max(0.25, float(np.percentile(heard[max(0, i - 16):i + 17], 85))) for i in range(len(times))
        ])
        return np.minimum(1.0, heard / level) * 0.85 + 0.15 * salience
    if given is not None and len(given):
        evidence = 0.15 * salience
        for d in given:
            i = int(np.argmin(np.abs(times - d)))
            local = times[min(i + 1, len(times) - 1)] - times[max(i - 1, 0)]
            if abs(times[i] - d) < 0.25 * local:
                evidence[i] = 1.0
        return evidence
    return salience


def _bar_lines(evidence: np.ndarray, times: np.ndarray) -> list[tuple[int, int]]:
    """Bars as (first beat, number of beats), found for the piece as a whole.

    A bar line wants a beat that looks like a downbeat, and no such beat inside the
    bar (the middle of a bar in four may be half a downbeat).  Bars keep their
    length unless the music insists; very short bars are unlikely.
    """
    count = len(evidence)
    ibi = np.diff(times)
    period = np.concatenate([ibi, ibi[-1:]]) if len(ibi) else np.ones(count)
    period = np.array([float(np.median(period[max(0, i - 4):i + 5])) for i in range(count)])

    def worth(i: int, length: int) -> float:
        inside = 0.0
        for j in range(i + 1, min(count, i + length)):
            inside += evidence[j] * (0.3 if length == 4 and j - i == 2 else 1.0)
        short = max(0.0, SHORT_BAR - length * period[i]) * 1.5
        return evidence[i] - BAR_LINE - inside - short - (0.1 if length == 3 else 0.0)

    never = -1e18
    score = {length: np.full(count, never) for length in LENGTHS}
    back: dict[int, np.ndarray] = {length: np.full(count, -1) for length in LENGTHS}
    for i in range(count):
        for length in LENGTHS:
            own = worth(i, length)
            if i < max(LENGTHS):  # the piece may begin inside a bar
                opening = -float(evidence[:i].sum())
                if opening + own > score[length][i]:
                    score[length][i], back[length][i] = opening + own, 0
            for before in LENGTHS:
                j = i - before
                if j >= 0 and score[before][j] > never / 2:
                    total = score[before][j] + own - (METRE_CHANGE if before != length else 0.0)
                    if total > score[length][i]:
                        score[length][i], back[length][i] = total, before
    best, where = never, (0, LENGTHS[-1])
    for i in range(max(0, count - max(LENGTHS)), count):
        for length in LENGTHS:
            if i + length >= count and score[length][i] > best:
                best, where = score[length][i], (i, length)
    bars = []
    i, length = where
    while True:
        bars.append((i, length))
        before = int(back[length][i])
        if before <= 0:
            break
        i, length = i - before, before
    return bars[::-1]


def _join_pairs(bars: list[tuple[int, int]], times: np.ndarray, notes: list[Note]) -> list[tuple[int, int]]:
    """Runs of two-beat bars whose harmony moves only every other bar are really bars of four."""
    change = _harmony_change(times, notes, 2)
    result: list[tuple[int, int]] = []
    i = 0
    while i < len(bars):
        j = i
        while j < len(bars) and bars[j][1] == 2:
            j += 1
        run = bars[i:j]
        if len(run) >= 6:
            even = [change[s] for s, _ in run[0::2] if s < len(change)]
            odd = [change[s] for s, _ in run[1::2] if s < len(change)]
            a, b = float(np.mean(even)), float(np.mean(odd))
            if max(a, b) >= 0.25 and max(a, b) >= 2.0 * min(a, b):
                first = 0 if a >= b else 1
                result.extend(run[:first])
                pairs = run[first:]
                for k in range(0, len(pairs) - 1, 2):
                    result.append((pairs[k][0], 4))
                if len(pairs) % 2:
                    result.append(pairs[-1])
                i = j
                continue
        result.extend(run)
        if j < len(bars):
            result.append(bars[j])
        i = j + 1
    return result


def _usual_length(bars: list[tuple[int, int]], index: int) -> int:
    """The bar length of the music around bar `index`."""
    around = [length for _, length in bars[max(0, index - 4):index] + bars[index + 1:index + 5]]
    return Counter(around).most_common(1)[0][0] if around else bars[index][1]


def _drop_pauses(
    times: np.ndarray, bars: list[tuple[int, int]], sounding: np.ndarray,
) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Take out beats that only count through a pause.

    Where the music stops for a fermata the beats found above still run on, and
    the bar gets longer than its neighbours or an odd bar of nothing follows.  A
    held note is one long beat; the surplus beats go, and the bar is regular again.
    """
    keep = np.ones(len(times), dtype=bool)
    lengths = [length for _, length in bars]
    for index, (start, length) in enumerate(bars):
        usual = _usual_length(bars, index)
        beats = range(start, min(len(times), start + length))
        silent = [not sounding[b] for b in beats]
        if all(silent) and length != usual and index > 0:
            for b in beats:  # an odd bar of nothing: part of the pause before it
                keep[b] = False
            lengths[index] = 0
        elif length != usual and len(silent) == length:
            # An odd bar that ends in silence: the silence is a pause, not part of the count.
            # (A longer bar keeps its regular length; a shorter one is joined to its neighbour below.)
            spare = length - usual if length > usual else length - 1
            surplus = 0
            while surplus < spare and silent[length - 1 - surplus]:
                surplus += 1
            for b in list(beats)[length - surplus:]:
                keep[b] = False
            lengths[index] = length - surplus
    if keep.all():
        return times, bars
    new_index = np.cumsum(keep) - 1
    result = []
    for (start, _), length in zip(bars, lengths):
        if length > 0:
            first = next(b for b in range(start, len(times)) if keep[b])
            result.append((int(new_index[first]), length))
    return times[keep], result


def _mend_odd_bars(
    times: np.ndarray, bars: list[tuple[int, int]], notes: list[Note], evidence,
) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Put right the bars that only look odd because the tempo was pulled about.

    Through a ritardando the beats found above keep to the old tempo for a while
    and count one too many; over a row of triplet chords they may count the
    chords.  Such a stretch shows as a few bars of unusual length among regular
    ones, with bar lines nobody is sure of.  If its time is filled just as well
    by whole regular bars at a tempo that bends only gently, it is counted again
    that way.  Bars that really are shorter or longer stay as they are: their
    downbeats are clear (`evidence(times)` says how clear), or their time does
    not fit regular bars.
    """
    for _ in range(len(bars)):  # one stretch at a time, as the beats are renumbered
        mended = False
        clear = evidence(times)
        index = 0
        while index < len(bars):
            usual = _usual_length(bars, index)
            if bars[index][1] == usual:
                index += 1
                continue
            end = index
            while end < len(bars) and bars[end][1] != usual:
                end += 1
            first, total = bars[index][0], sum(length for _, length in bars[index:end])
            after = first + total  # the beat that follows the stretch
            sure = min(clear[start] for start, _ in bars[index:end] if start < len(clear))
            if end - index > 4 or sure >= 0.6:
                index = end  # a passage in another metre, or bar lines that are certain
                continue
            if total % usual == 0:
                # Only the bar lines are irregular: draw them regularly.
                regular = [(first + k * usual, usual) for k in range(total // usual)]
                if regular != bars[index:end]:
                    bars = bars[:index] + regular + bars[end:]
                    mended = True
                    break
                index = end
                continue
            if after >= len(times) or first < 2:
                index = end
                continue
            before = float(np.median(np.diff(times[max(0, first - 6):first + 1])))
            span = float(times[after] - times[first])
            best = None
            for count in range(max(usual, total - 2), total + 2):
                if count % usual:
                    continue
                # Beats that grow (or shrink) by the same factor each: which factor fills the time?
                lo, hi = 0.6, 1.7
                for _ in range(40):
                    factor = (lo + hi) / 2
                    filled = before * sum(factor ** k for k in range(1, count + 1))
                    lo, hi = (factor, hi) if filled < span else (lo, factor)
                if 0.88 <= factor <= 1.3 and (best is None or abs(np.log(factor)) < abs(np.log(best[1]))):
                    best = (count, factor)
            if best is None:
                index = end
                continue
            count, factor = best
            inside = float(times[first]) + before * np.cumsum([factor ** k for k in range(1, count)])
            fresh = np.concatenate([times[:first + 1], inside, times[after:]])
            fresh[first:first + count + 1] = _snap_to_onsets(fresh[first:first + count + 1], notes)
            shift = count - total
            bars = (
                bars[:index] + [(first + k * usual, usual) for k in range(count // usual)]
                + [(start + shift, length) for start, length in bars[end:]]
            )
            times = fresh
            mended = True
            break
        if not mended:
            break
    # A single beat is no bar: it belongs to the bar before it.
    joined: list[tuple[int, int]] = []
    for start, length in bars:
        if length == 1 and joined:
            joined[-1] = (joined[-1][0], joined[-1][1] + 1)
        else:
            joined.append((start, length))
    return times, joined


# ── from beats to a grid ────────────────────────────────────────────────────


def _bars_of_four(times: np.ndarray, notes: list[Note], phase: int) -> int | None:
    """When a "2/4" piece changes harmony only every other bar, it is really in four.

    Returns the phase of the four-beat bars, or None when the two-beat bars are right.
    """
    change = _harmony_change(times, notes, 2)
    first = min(n.onset for n in notes)
    last = max(n.onset for n in notes)
    inside = [i for i in range(len(times)) if first - 0.05 <= times[i] <= last]
    a = [change[i] for i in inside if (i - phase) % 4 == 0]
    b = [change[i] for i in inside if (i - phase) % 4 == 2]
    if len(a) < 3 or len(b) < 3:
        return None
    strong, weak = (np.mean(a), np.mean(b)) if np.mean(a) >= np.mean(b) else (np.mean(b), np.mean(a))
    if strong >= 0.25 and strong >= 2.0 * weak:
        return phase % 4 if np.mean(a) >= np.mean(b) else (phase + 2) % 4
    return None


def _contrast(salience: np.ndarray, per_bar: int, first: int) -> tuple[float, int]:
    """How much one beat of the bar stands out from the others, and which one.

    `first` is the beat the piece starts on: most pieces begin on "one", so that
    beat gets a head start which a clearly accented later beat still overtakes.
    """
    spread = float(salience.std()) + 1e-9
    best, phase = -np.inf, 0
    for r in range(per_bar):
        mask = np.zeros(len(salience), dtype=bool)
        mask[r::per_bar] = True
        if mask.sum() < 2 or (~mask).sum() < 2:
            continue
        value = float(salience[mask].mean() - salience[~mask].mean()) / spread
        value += 0.5 * (r == first % per_bar)
        if value > best:
            best, phase = value, r
    return best, phase


def _bars_from_notes(salience: np.ndarray, first: int) -> tuple[int, int]:
    """Guess beats per bar and the bar phase from accents alone."""
    triple, triple_phase = _contrast(salience, 3, first)
    duple, duple_phase = _contrast(salience, 4, first)
    return (3, triple_phase) if triple > duple + 0.1 else (4, duple_phase)


def _downbeat_indices(beats: np.ndarray, downbeats: np.ndarray | None) -> tuple[list[int], int | None]:
    """Which beats were given as downbeats, and the bar length that follows from them."""
    indices: list[int] = []
    if downbeats is None or len(downbeats) < 2:
        return indices, None
    for d in downbeats:
        i = int(np.argmin(np.abs(beats - d)))
        local = beats[min(i + 1, len(beats) - 1)] - beats[max(i - 1, 0)]
        if abs(beats[i] - d) < 0.25 * local:
            indices.append(i)
    steps = Counter(int(x) for x in np.diff(sorted(set(indices))) if x > 0)
    if steps:
        candidate, count = steps.most_common(1)[0]
        if 2 <= candidate <= 12 and count >= 0.5 * sum(steps.values()):
            return indices, candidate
    return indices, None


def _regular_bars(per_bar: int, phase: int, count: int) -> list[tuple[int, int]]:
    return [(start, per_bar) for start in range(phase % per_bar, count, per_bar)]


def build_grid(
    performance: Performance,
    beats: np.ndarray | None,
    downbeats: np.ndarray | None,
    beats_per_bar: int | None = None,
    tempo_scale: Fraction | None = None,
    pickup: float | None = None,
    tracked: Tracked | None = None,
) -> Grid:
    """Find the beats, lay them over the whole piece and find the bars.

    `tracked` is what the beat tracker heard in the recording.  Without it,
    `beats` and `downbeats` are taken as given (or the pulse is derived from
    the notes), and all bars have the same length.
    """
    notes = performance.notes
    source = "audio"
    if tracked is not None and len(tracked.beat) < 2 * TRACKER_FPS:
        tracked = None
    memo = (beats_per_bar, tempo_scale, pickup, len(notes))
    if tracked is not None and memo in tracked.grids:
        times, per_bar, confidence, starts = tracked.grids[memo]
        return Grid(times.copy(), per_bar, starts[0], source, confidence, list(starts))
    listened = tracked
    if tracked is not None:
        beats = find_beats(tracked, notes)
        if len(beats) < 4:
            tracked = None
    if tracked is None:
        if beats is None or len(beats) < 4:
            beats, downbeats, source = track_notes(performance), None, "notes"
        beats = _regularise(np.asarray(beats, dtype=float))

    # Which note value is "the beat"?  Given beats may sit on half notes where a
    # musician would count quarters; written out, that gives needlessly small
    # note values.  (The pulse found in a recording is already on its level.)
    doubled = tempo_scale == 2
    if tracked is None and tempo_scale is None and not beats_per_bar:
        bpm = 60.0 / float(np.median(np.diff(beats)))
        _, counted = _downbeat_indices(beats, downbeats)
        attacks = [c for c, _ in onset_clusters(notes) if beats[0] <= c <= beats[-1]]
        density = len(attacks) / max(1, int(np.searchsorted(beats, attacks[-1]) - np.searchsorted(beats, attacks[0]))) if attacks else 0
        doubled = bpm < 40 or (bpm < 60 and counted == 2) or (bpm < 56 and counted in (None, 4) and density >= 3)
    if doubled:
        mids = (beats[:-1] + beats[1:]) / 2
        beats = np.sort(np.concatenate([beats, mids]))
    beats = _snap_to_onsets(beats, notes)
    for i in range(1, len(beats)):  # snapping must leave the beats in order
        if beats[i] <= beats[i - 1]:
            beats[i] = beats[i - 1] + 0.01
    first_beat = int(np.argmin(np.abs(beats - min(n.onset for n in notes))))

    halve = tempo_scale == Fraction(1, 2) or (
        tracked is None and tempo_scale is None and not beats_per_bar and 60.0 / float(np.median(np.diff(beats))) > 200
    )

    # Bars: how many beats, and which beat is "one".
    confidence = 0.0
    if tracked is not None:
        evidence = _downbeat_evidence(beats, notes, tracked, None)
        if halve:
            keep = int(np.argmax([evidence[r::2].sum() for r in range(2)]))
            beats = beats[keep::2]
            evidence = _downbeat_evidence(beats, notes, tracked, None)
            first_beat = int(np.argmin(np.abs(beats - min(n.onset for n in notes))))
        if pickup is not None:
            per_bar = beats_per_bar or Counter(length for _, length in _bar_lines(evidence, beats)).most_common(1)[0][0]
            start = Grid(beats, per_bar, 0, source)
            phase = int(round(start.beat_of(min(n.onset for n in notes)) + pickup)) % per_bar
            bars, confidence = _regular_bars(per_bar, phase, len(beats)), 1.0
        elif beats_per_bar:
            phase = int(np.argmax([
                evidence[r::beats_per_bar].mean() + 0.1 * (r == first_beat % beats_per_bar) for r in range(beats_per_bar)
            ]))
            bars = _regular_bars(beats_per_bar, phase, len(beats))
        else:
            bars = _join_pairs(_bar_lines(evidence, beats), beats, notes)
            beats, bars = _drop_pauses(beats, bars, _sounding(beats, notes))
            beats, bars = _mend_odd_bars(beats, bars, notes, lambda t: _downbeat_evidence(t, notes, tracked, None))
        if not confidence and bars:
            fresh = _downbeat_evidence(beats, notes, tracked, None)
            confidence = float(np.mean([fresh[s] for s, _ in bars if s < len(fresh)]))
    else:
        salience = _beat_salience(beats, notes)
        phase = 0
        indices, per_bar = _downbeat_indices(beats, downbeats)
        if doubled and per_bar in (6, 8):
            per_bar //= 2  # the old bar becomes two
        if beats_per_bar:
            per_bar = beats_per_bar
        if per_bar is None:
            per_bar, phase = _bars_from_notes(salience, first_beat)
        if indices:
            votes = Counter(i % per_bar for i in indices)
            accents = np.array([salience[r::per_bar].mean() if len(salience[r::per_bar]) else 0.0 for r in range(per_bar)])
            accents = accents / (accents.max() + 1e-9)
            scores = [
                votes.get(r, 0) / len(indices) + 0.35 * accents[r] + 0.1 * (r == first_beat % per_bar)
                for r in range(per_bar)
            ]
            phase = int(np.argmax(scores))
            confidence = votes.get(phase, 0) / len(indices)
        elif beats_per_bar:
            _, phase = _contrast(salience, per_bar, first_beat)
        if per_bar == 2 and not beats_per_bar and pickup is None:
            four = _bars_of_four(beats, notes, phase)
            if four is not None:
                per_bar, phase = 4, four
        if pickup is not None:
            # The user says how many beats come before the first full bar.
            start = Grid(beats, per_bar, 0, source)
            phase = int(round(start.beat_of(min(n.onset for n in notes)) + pickup)) % per_bar
            confidence = 1.0
        if halve and per_bar % 2 == 0:  # half as many beats
            keep = phase % 2
            beats = beats[keep::2]
            phase = (phase - keep) // 2
            per_bar //= 2
            if per_bar == 1:  # two old bars make one
                salience = _beat_salience(beats, notes)
                per_bar = 2
                phase = int(np.argmax([salience[r::2].mean() if len(salience[r::2]) else 0 for r in range(2)]))
        bars = _regular_bars(per_bar, phase, len(beats))

    # Cover everything that sounds, with a little room on both sides, in whole bars.
    first = min(n.onset for n in notes)
    last = max(n.sustain_end for n in notes)
    head = float(np.median(np.diff(beats[:5])))
    tail = float(np.median(np.diff(beats[-5:])))
    opening, closing = bars[0][1], bars[-1][1]
    starts = [s for s, _ in bars] + [bars[-1][0] + closing]
    # Before: at least one beat ahead of the first note, and the first bar complete.
    room = 1
    while float(beats[0]) - room * head > first - 0.25 * head:
        room += 1
    while starts[0] > -room:
        starts.insert(0, starts[0] - opening)
    room = -starts[0]
    before = [float(beats[0]) - head * i for i in range(room, 0, -1)]
    starts = [s + room for s in starts]
    beats = np.concatenate([before, beats])
    # After: beats to the end of the last sound, and bars to there.
    after: list[float] = []
    end = float(beats[-1])
    while end < last + tail:
        end += tail
        after.append(end)
    beats = np.concatenate([beats, after])
    final = int(np.searchsorted(beats, last))  # the first beat after everything has sounded
    while len(starts) > 2 and starts[-2] >= final:
        starts.pop()
    while starts[-1] < final:
        starts.append(starts[-1] + closing)
    if starts[-1] > len(beats) - 1:
        extra = starts[-1] - (len(beats) - 1)
        beats = np.concatenate([beats, float(beats[-1]) + tail * np.arange(1, extra + 1)])
    per_bar = Counter(b - a for a, b in zip(starts, starts[1:])).most_common(1)[0][0]
    if listened is not None:
        listened.grids[memo] = (beats.copy(), per_bar, confidence, list(starts))
    return Grid(beats, per_bar, starts[0], source, confidence, starts)


# ── metre ───────────────────────────────────────────────────────────────────


def _meter(beats: int, compound: bool) -> Meter:
    if compound:
        return Meter(beats, Fraction(3, 2), beats * 3, 8)
    return Meter(beats, Fraction(1), beats, 4)


def compound_bars(grid: Grid, divisions: dict[int, int]) -> list[bool]:
    """For every bar: do its beats fall into three (6/8, 9/8, 12/8) rather than into two?

    Decided for stretches of bars, not bar by bar: a few triplets do not make a
    bar of 4/4 a bar of 12/8, and a bar of long notes follows its neighbours.
    """
    count = grid.bars
    # What a bar costs to write: in simple time every beat in three needs a triplet; in
    # compound time every beat in two needs a duplet, and plain beats become dotted notes.
    # Simple time is the usual case, so compound time has to earn its place.
    cost = np.zeros((count, 2))
    for index in range(count):
        three = two = plain = 0
        for k in range(grid.bar_start(index), grid.bar_start(index + 1)):
            d = divisions.get(k)
            if d in (3, 6):
                three += 1
            elif d in (2, 4, 8):
                two += 1
            elif d == 1:
                plain += 1
        cost[index] = (three, 1.2 * two + 0.35 * plain + 0.3)
    stay = 5.0  # a change of kind needs about three clear bars
    score = -cost[0]
    back = np.zeros((count, 2), dtype=int)
    for index in range(1, count):
        new = np.zeros(2)
        for state in (0, 1):
            keep, switch = score[state], score[1 - state] - stay
            back[index, state] = state if keep >= switch else 1 - state
            new[state] = max(keep, switch) - cost[index, state]
        score = new
    state = int(np.argmax(score))
    result = [False] * count
    for index in range(count - 1, -1, -1):
        result[index] = bool(state)
        state = int(back[index, state])
    return result


def tempo_breaks(grid: Grid) -> set[int]:
    """Bars at which the music takes a clearly different tempo."""
    ibi = np.diff(grid.times)
    tempo = np.array([
        float(np.median(ibi[grid.bar_start(i):max(grid.bar_start(i) + 1, min(grid.bar_start(i + 1), len(ibi)))]))
        if grid.bar_start(i) < len(ibi) else float(ibi[-1])
        for i in range(grid.bars)
    ])
    jump = np.zeros(grid.bars)
    for i in range(2, grid.bars - 1):
        before, after = float(np.median(tempo[max(0, i - 3):i])), float(np.median(tempo[i:i + 3]))
        jump[i] = abs(np.log(after / before))
    # One bar per change: the one where the difference between before and after is greatest.
    return {
        i for i in range(grid.bars)
        if jump[i] >= np.log(1.08) and jump[i] >= jump[max(0, i - 2):i + 3].max()
    }


def align_metre_changes(compound: list[bool], breaks: set[int]) -> list[bool]:
    """A change between simple and compound time belongs to the start of a section.

    The first bar of a new section is often played freely, and its beats then say
    little about twos or threes; when a new key or tempo begins one bar beside the
    change, the change moves there.
    """
    result = list(compound)
    for i in range(1, len(compound)):
        if compound[i] != compound[i - 1] and i not in breaks:
            if i - 1 in breaks:
                result[i - 1] = compound[i]
            elif i + 1 in breaks and i + 1 < len(compound):
                result[i] = compound[i - 1]
    return result


def set_meters(grid: Grid, compound: list[bool], requested: tuple[int, int] | None = None) -> None:
    """Name the time signature of every bar."""
    if requested:
        numerator, denominator = requested
        per_bar = grid.beats_per_bar
        if denominator == 8 and numerator % 3 == 0 and numerator > 3 and per_bar * 3 == numerator:
            meter = Meter(per_bar, Fraction(3, 2), numerator, denominator)
        else:
            meter = Meter(per_bar, Fraction(4, denominator) * Fraction(numerator, per_bar), numerator, denominator)
        grid.meters = [meter] * grid.bars
        return
    grid.meters = []
    for index in range(grid.bars):
        length = grid.bar_length(index)
        if compound[index] and length in (2, 3, 4):
            grid.meters.append(_meter(length, True))
        elif length in (6, 9, 12) or (grid.bpm > 200 and length in (3, 5, 7)):
            grid.meters.append(Meter(length, Fraction(1, 2), length, 8))
        elif length == 8:
            grid.meters.append(Meter(length, Fraction(1, 2), 4, 4))
        else:
            grid.meters.append(_meter(length, False))
