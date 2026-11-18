"""Which hand plays what.

Each chord is cut at some pitch: everything below goes to the left hand,
everything above to the right.  Where to cut is decided for the whole piece
together (beam search) by what two real hands can do: how far a hand can
stretch, how far it has to travel and how much time it has for that, keys it
is still holding down, and the two hands not getting in each other's way.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import LEFT, RIGHT, Note

BEAM = 48
STRETCH = 12  # semitones a hand covers comfortably
MOVE = 0.25  # cost per semitone the hand has to travel outside its position
PREFERENCE = 0.08  # pull of the low register to the left hand, the high one to the right


SHORT = 0.35  # seconds: a key let go this quickly belongs to a figure, not to a held note
STREAM = 0.25  # cost of breaking a running figure away from the hand that plays it


@dataclass(frozen=True)
class _Hand:
    low: int
    high: int
    time: float
    held: tuple[tuple[int, float], ...] = ()
    figure: float = -1e9  # when this hand last struck a short note


def _play(hand: _Hand, chord: list[Note], time: float, side: int) -> tuple[float, _Hand]:
    """Cost of this hand playing `chord` now, and the hand afterwards."""
    if not chord:
        return 0.0, hand
    low, high = chord[0].pitch, chord[-1].pitch
    held = tuple((p, release) for p, release in hand.held if release > time + 0.05)
    cost = 0.0

    # Everything the hand holds or strikes at this moment must be within reach.
    lowest = min([low] + [p for p, _ in held])
    highest = max([high] + [p for p, _ in held])
    span = highest - lowest
    cost += 0.01 * max(0, span - 7) ** 2  # beyond a fifth a grip starts to cost a little
    if span > STRETCH:
        cost += 0.6 * (span - STRETCH) ** 2
    fingers = len(chord) + len(held)
    if fingers > 5:
        cost += 6.0 * (fingers - 5)

    # Travelling: free inside an octave around where the hand just was (that is finger
    # work, not a move), cheap when there is time, expensive when there is not.
    elapsed = max(0.02, time - hand.time)
    outside = max(0, (hand.high - STRETCH) - low, high - (hand.low + STRETCH))
    cost += MOVE * outside / (1.0 + elapsed / 0.35)
    cost += 0.03 * max(0.0, abs((low + high) / 2 - (hand.low + hand.high) / 2) - 5) / (1.0 + elapsed)

    # A soft pull towards the usual registers; around middle C either hand is fine.
    for n in chord:
        cost += PREFERENCE * (max(0, 57 - n.pitch) if side == RIGHT else max(0, n.pitch - 64))

    held += tuple((n.pitch, n.offset) for n in chord)
    short = any(n.offset - n.onset < SHORT for n in chord)
    return cost, _Hand(low, high, time, held, time if short else hand.figure)


def _figure(hand: _Hand, other: _Hand, chord: list[Note], time: float) -> float:
    """Cost of giving a short note to this hand while the other hand is in the middle of a figure."""
    if not chord or not any(n.offset - n.onset < SHORT for n in chord):
        return 0.0
    if other.figure > hand.figure and time - other.figure < SHORT:
        return STREAM
    return 0.0


def _crossing(left: _Hand, right: _Hand, played_left: bool, played_right: bool, time: float) -> float:
    """Penalty for one hand reaching over the other."""
    if played_left and played_right:
        return 0.0
    cost = 0.0
    if played_right and (time - left.time < 0.6 or any(r > time for _, r in left.held)):
        over = left.high - right.low
        if over >= 0:
            cost += 1.0 + 0.15 * over
    if played_left and (time - right.time < 0.6 or any(r > time for _, r in right.held)):
        over = left.high - right.low
        if over >= 0:
            cost += 1.0 + 0.15 * over
    return cost


def split_hands(notes: list[Note], split_pitch: int | None = None) -> None:
    """Set `hand` on every note. Notes must already be quantised."""
    if split_pitch is not None:
        for n in notes:
            n.hand = RIGHT if n.pitch >= split_pitch else LEFT
        return

    chords: dict = {}
    for n in notes:
        chords.setdefault(n.pos, []).append(n)
    ordered = [sorted(chords[p], key=lambda n: n.pitch) for p in sorted(chords)]

    start = ordered[0][0].onset - 2.0
    # (cost, right hand, left hand, trail of cut points)
    beam: list[tuple[float, _Hand, _Hand, tuple | None]] = [(0.0, _Hand(67, 76, start), _Hand(43, 52, start), None)]
    for chord in ordered:
        time = sum(n.onset for n in chord) / len(chord)
        candidates: dict[tuple, tuple[float, _Hand, _Hand, tuple | None]] = {}
        for cost, right, left, trail in beam:
            for cut in range(len(chord) + 1):
                lower, upper = chord[:cut], chord[cut:]
                cost_left, new_left = _play(left, lower, time, LEFT)
                cost_right, new_right = _play(right, upper, time, RIGHT)
                total = cost + cost_left + cost_right + _crossing(new_left, new_right, bool(lower), bool(upper), time)
                total += _figure(left, right, lower, time) + _figure(right, left, upper, time)
                key = (new_right.low, new_right.high, new_right.time, new_left.low, new_left.high, new_left.time)
                if key not in candidates or total < candidates[key][0]:
                    candidates[key] = (total, new_right, new_left, (trail, cut))
        beam = sorted(candidates.values(), key=lambda c: c[0])[:BEAM]

    trail = beam[0][3]
    cuts: list[int] = []
    while trail is not None:
        trail, cut = trail
        cuts.append(cut)
    for chord, cut in zip(ordered, reversed(cuts)):
        for i, n in enumerate(chord):
            n.hand = LEFT if i < cut else RIGHT
