"""Pulse, bars and metre.

The beats come from the audio through Beat This! (Foscarin, Schlüter & Widmer,
ISMIR 2024), which also marks the downbeats.  They are then tidied up, pulled
onto the notes that were actually played and extended to cover the whole piece.
If there is no audio (MIDI input) or the tracker finds nothing, the pulse is
derived from the note onsets instead.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from .model import Meter, Note, Performance


@dataclass
class Grid:
    times: np.ndarray  # one entry per beat, strictly increasing
    beats_per_bar: int
    phase: int  # beats with index ≡ phase (mod beats_per_bar) start a bar
    source: str  # "audio" or "notes"
    downbeat_confidence: float = 0.0

    @property
    def bpm(self) -> float:
        return 60.0 / float(np.median(np.diff(self.times)))

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


def track_audio(audio: np.ndarray, sample_rate: int, device: str) -> tuple[np.ndarray, np.ndarray]:
    """Beat and downbeat times of a recording."""
    from beat_this.inference import Audio2Beats

    tracker = Audio2Beats(checkpoint_path=beat_model(), device=device, dbn=False)
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    beats, downbeats = tracker(mono, sample_rate)
    return np.asarray(beats, dtype=float), np.asarray(downbeats, dtype=float)


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


# ── from raw beats to a usable grid ─────────────────────────────────────────


def _regularise(beats: np.ndarray) -> np.ndarray:
    """Drop doubled beats and fill in skipped ones."""
    beats = np.unique(np.round(beats, 4))
    if len(beats) < 4:
        return beats
    overall = float(np.median(np.diff(beats)))
    out = [float(beats[0])]
    for b in beats[1:]:
        local = float(np.median(np.diff(out[-6:]))) if len(out) >= 4 else overall
        gap = b - out[-1]
        if gap < 0.55 * local:
            continue
        parts = int(round(gap / local))
        if parts >= 2 and abs(gap / parts - local) < 0.3 * local:
            start = out[-1]
            out.extend(start + gap * i / parts for i in range(1, parts))
        out.append(float(b))
    return np.array(out)


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
    """Which beats the tracker called downbeats, and the bar length that follows from them."""
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


def build_grid(
    performance: Performance,
    beats: np.ndarray | None,
    downbeats: np.ndarray | None,
    beats_per_bar: int | None = None,
    tempo_scale: Fraction | None = None,
    pickup: float | None = None,
) -> Grid:
    """Clean the beats, lay them over the whole piece and find the bars."""
    notes = performance.notes
    source = "audio"
    if beats is None or len(beats) < 4:
        beats, downbeats, source = track_notes(performance), None, "notes"

    beats = _regularise(np.asarray(beats, dtype=float))

    # Which note value is "the beat"?  A tracker may lock onto half notes where a
    # musician would count quarters; written out, that gives needlessly small
    # note values.  Bring the pulse into the range people actually count in.
    doubled = tempo_scale == 2
    if tempo_scale is None and not beats_per_bar:
        bpm = 60.0 / float(np.median(np.diff(beats)))
        _, counted = _downbeat_indices(beats, downbeats)
        attacks = [c for c, _ in onset_clusters(notes) if beats[0] <= c <= beats[-1]]
        density = len(attacks) / max(1, int(np.searchsorted(beats, attacks[-1]) - np.searchsorted(beats, attacks[0]))) if attacks else 0
        doubled = bpm < 40 or (bpm < 60 and counted == 2) or (bpm < 56 and counted in (None, 4) and density >= 3)
    if doubled:
        mids = (beats[:-1] + beats[1:]) / 2
        beats = np.sort(np.concatenate([beats, mids]))
    beats = _snap_to_onsets(beats, notes)

    # Bars: how many beats, and which beat is "one".
    salience = _beat_salience(beats, notes)
    phase, confidence = 0, 0.0
    indices, per_bar = _downbeat_indices(beats, downbeats)
    if doubled and per_bar in (6, 8):
        per_bar //= 2  # the old bar becomes two
    if beats_per_bar:
        per_bar = beats_per_bar
    first_beat = int(np.argmin(np.abs(beats - min(n.onset for n in notes))))
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
        grid = Grid(beats, per_bar, 0, source)
        phase = int(round(grid.beat_of(min(n.onset for n in notes)) + pickup)) % per_bar
        confidence = 1.0

    too_fast = tempo_scale is None and not beats_per_bar and 60.0 / float(np.median(np.diff(beats))) > 200
    if (tempo_scale == Fraction(1, 2) or too_fast) and per_bar % 2 == 0:  # half as many beats
        keep = phase % 2
        beats = beats[keep::2]
        phase = (phase - keep) // 2
        per_bar //= 2
        if per_bar == 1:  # two old bars make one
            salience = _beat_salience(beats, notes)
            per_bar = 2
            phase = int(np.argmax([salience[r::2].mean() if len(salience[r::2]) else 0 for r in range(2)]))

    # Cover everything that sounds, with a little room on both sides.
    first = min(n.onset for n in notes)
    last = max(n.sustain_end for n in notes)
    head = float(np.median(np.diff(beats[:5])))
    tail = float(np.median(np.diff(beats[-5:])))
    before: list[float] = []
    start = float(beats[0])
    while start > first - 0.25 * head or len(before) < 1:
        start -= head
        before.append(start)
    after: list[float] = []
    end = float(beats[-1])
    while end < last + tail:
        end += tail
        after.append(end)
    beats = np.concatenate([before[::-1], beats, after])
    phase = (phase + len(before)) % per_bar

    return Grid(beats, per_bar, phase, source, confidence)


def decide_meter(
    grid: Grid, triple_share: float, requested: tuple[int, int] | None = None, triple_density: float = 1.0,
) -> Meter:
    """Name the time signature for the tracked pulse.

    `triple_share` is the share of subdivided beats that fall into three parts;
    when it dominates, the pulse is a dotted quarter (6/8, 9/8, 12/8).
    """
    per_bar, bpm = grid.beats_per_bar, grid.bpm
    if requested:
        numerator, denominator = requested
        if denominator == 8 and numerator % 3 == 0 and numerator > 3 and per_bar * 3 == numerator:
            return Meter(per_bar, Fraction(3, 2), numerator, denominator)
        return Meter(per_bar, Fraction(4, denominator) * Fraction(numerator, per_bar), numerator, denominator)
    # Compound only when the music lives in threes, not because of a triplet here and there.
    if per_bar in (2, 3, 4) and triple_share >= 0.6 and triple_density >= 0.3:
        return Meter(per_bar, Fraction(3, 2), per_bar * 3, 8)
    if per_bar in (6, 9, 12) or (bpm > 200 and per_bar in (3, 5, 7)):
        return Meter(per_bar, Fraction(1, 2), per_bar, 8)
    if per_bar == 8:
        return Meter(per_bar, Fraction(1, 2), 4, 4)
    return Meter(per_bar, Fraction(1), per_bar, 4)
