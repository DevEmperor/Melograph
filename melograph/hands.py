"""Which hand plays what.

Each chord is cut at some pitch: everything below goes to the left hand,
everything above to the right.  Where to cut is decided for the whole piece
together (beam search) by what two real hands do: how far a hand can stretch,
how far it has to travel and how much time it has for that, keys it is still
holding down, the two hands not getting in each other's way – and habit: a
hand that has just played a key plays it again, and a hand that is running a
figure in even notes goes on with it.  That keeps an accompaniment in the left
hand even when it climbs into the register of the tune.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import LEFT, RIGHT, Note

BEAM = 12  # combinations kept from chord to chord (the three test pieces come out the same from 6 to 48)
STRETCH = 12  # semitones a hand covers comfortably
GRIP = 0.004  # cost of a wide grip (times the square of what it has beyond a fifth): an octave is everyday
MOVE = 0.25  # cost per semitone the hand has to travel outside its position
NEAR = 2  # semitones a hand shifts without that being a move
PREFERENCE = 0.04  # pull of the low register to the left hand, the high one to the right
LOW, HIGH = 55, 69  # between these notes (G3 … A4) either hand is equally at home

MEMORY = 2.0  # seconds a hand remembers which keys it played
AGAIN = 0.3  # how much playing a key again with the same hand is worth (and with the other one costs)
FIGURE = 0.15  # how much going on with a figure in even notes is worth
EVEN = 0.6  # seconds: longer gaps than this are no figure


@dataclass(frozen=True)
class _Hand:
    low: int
    high: int
    time: float
    held: tuple[tuple[int, float], ...] = ()
    keys: tuple[tuple[int, float], ...] = ()  # (pitch, time) of what the hand played lately
    gap: float = 0.0  # time between its last two attacks


def _play(hand: _Hand, chord: list[Note], time: float, side: int) -> tuple[float, _Hand, frozenset]:
    """Cost of this hand playing `chord` now, the hand afterwards, and the keys it remembers.

    (What the other hand remembers is added by the caller: this part depends on one hand
    only and is worked out once for all the combinations a hand appears in.)
    """
    mine = frozenset(p for p, t in hand.keys if time - t <= MEMORY)
    if not chord:
        return 0.0, hand, mine
    low, high = chord[0].pitch, chord[-1].pitch
    held = tuple((p, release) for p, release in hand.held if release > time + 0.05)
    cost = 0.0

    # Everything the hand holds or strikes at this moment must be within reach.
    lowest = min([low] + [p for p, _ in held])
    highest = max([high] + [p for p, _ in held])
    span = highest - lowest
    cost += GRIP * max(0, span - 7) ** 2  # beyond a fifth a grip starts to cost a little
    if span > STRETCH:
        cost += 0.6 * (span - STRETCH) ** 2
    fingers = len(chord) + len(held)
    if fingers > 5:
        cost += 6.0 * (fingers - 5)

    # Travelling: free inside an octave around where the hand just was (that is finger
    # work, not a move) and for a step beyond it (octaves moving up a line), cheap when
    # there is time, expensive when there is not.
    elapsed = max(0.02, time - hand.time)
    outside = max(0, (hand.high - STRETCH) - low - NEAR, high - (hand.low + STRETCH) - NEAR)
    cost += MOVE * outside / (1.0 + elapsed / 0.35)
    cost += 0.03 * max(0.0, abs((low + high) / 2 - (hand.low + hand.high) / 2) - 5) / (1.0 + elapsed)

    # A soft pull towards the usual registers; around middle C either hand is fine.
    for n in chord:
        cost += PREFERENCE * (max(0, LOW - n.pitch) if side == RIGHT else max(0, n.pitch - HIGH))

    # Habit: the same key again with the same hand (an ostinato, a broken chord, repeated chords).
    cost -= AGAIN * sum(1 for n in chord if n.pitch in mine) / len(chord)
    # And the hand that plays even notes goes on playing them – by what it has been doing
    # for a while, not by its last step alone: one longer note does not end a figure, and
    # one quick note between two of an accompaniment does not begin one.
    usual = _usual_gap(hand)
    if 0 < usual <= EVEN and abs(elapsed - usual) <= 0.2 * usual:
        cost -= FIGURE

    held += tuple((n.pitch, n.offset) for n in chord)
    keys = tuple((p, t) for p, t in hand.keys if time - t <= MEMORY)[-12:] + tuple((n.pitch, time) for n in chord)
    return cost, _Hand(low, high, time, held, keys, elapsed), mine


def _usual_gap(hand: _Hand) -> float:
    """The time this hand has lately let pass from one attack to the next.

    Judged by its attacks of the last seconds (the ones it still remembers); a hand
    that has only just come in is taken by its last step.
    """
    times: list[float] = []
    for _, t in reversed(hand.keys):  # in order of time, a chord several times over
        if not times or t != times[-1]:
            times.append(t)
            if len(times) == 7:
                break
    if len(times) < 4:
        return hand.gap
    gaps = sorted(a - b for a, b in zip(times, times[1:]))
    return gaps[len(gaps) // 2]


def _others_keys(chord: list[Note], mine: frozenset, theirs: frozenset) -> float:
    """Cost of striking keys the other hand has just played (and this one has not)."""
    if not chord:
        return 0.0
    return AGAIN * sum(1 for n in chord if n.pitch in theirs and n.pitch not in mine) / len(chord)


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
        # The same hand turns up in many of the combinations kept; what it costs to play
        # one part of the chord is worked out once.
        played: dict[tuple[int, int, int], tuple[float, _Hand, frozenset]] = {}

        def play(hand: _Hand, part: list[Note], cut: int, side: int) -> tuple[float, _Hand, frozenset]:
            key = (id(hand), cut, side)
            if key not in played:
                played[key] = _play(hand, part, time, side)
            return played[key]

        for cost, right, left, trail in beam:
            for cut in range(len(chord) + 1):
                lower, upper = chord[:cut], chord[cut:]
                cost_left, new_left, left_keys = play(left, lower, cut, LEFT)
                cost_right, new_right, right_keys = play(right, upper, cut, RIGHT)
                total = cost + cost_left + cost_right + _crossing(new_left, new_right, bool(lower), bool(upper), time)
                total += _others_keys(lower, left_keys, right_keys) + _others_keys(upper, right_keys, left_keys)
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
