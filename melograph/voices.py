"""Note lengths and voices.

How long a key was held says little about how a note is written: under the
pedal a quarter note may be released after a sixteenth, and legato playing
overlaps.  So a note normally lasts until the next one in the same hand, and a
rest is only written when the sound really stops.  A second voice is opened
only where a key demonstrably stays down while the same hand moves on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from .beats import Grid
from .model import LEFT, RIGHT, Note, Pedal
from .quantize import Quantisation, snap_length


@dataclass
class Event:
    """A note or chord in one voice."""

    start: Fraction
    end: Fraction
    notes: list[Note]
    held: bool = False
    stream: int = 0

    @property
    def pitch(self) -> float:
        return sum(n.pitch for n in self.notes) / len(self.notes)


def shape(
    notes: list[Note],
    quantisation: Quantisation,
    grid: Grid,
    pedals: list[Pedal],
    max_voices: int = 2,
    staccato: bool = True,
) -> None:
    """Set `dur`, `voice` and `staccato` on every note."""
    anchors = sorted({n.pos for n in notes})
    for hand in (RIGHT, LEFT):
        mine = [n for n in notes if n.hand == hand]
        if not mine:
            continue
        events = _events(mine, quantisation.of_hand(hand), grid, anchors, pedals, max_voices, staccato)
        _assign_streams(events)
        for event in events:
            for n in event.notes:
                n.dur = event.end - event.start
                n.voice = event.stream


def _pedal_up(pedals: list[Pedal], start: float, end: float) -> float:
    """Seconds between `start` and `end` during which the pedal is not down."""
    up = max(0.0, end - start)
    for p in pedals:
        up -= max(0.0, min(end, p.end) - max(start, p.start))
    return up


def _events(
    notes: list[Note],
    quantisation: Quantisation,
    grid: Grid,
    anchors: list[Fraction],
    pedals: list[Pedal],
    max_voices: int,
    staccato: bool,
) -> list[Event]:
    chords: dict[Fraction, list[Note]] = {}
    for n in notes:
        chords.setdefault(n.pos, []).append(n)
    starts = sorted(chords)
    events: list[Event] = []
    candidates: list[tuple[list[Note], bool]] = []  # notes that could carry a staccato dot

    # Is holding keys down through the following notes a habit of this hand (the bass and
    # tenor of Bach's C major prelude), or does it only happen here and there?  Under the
    # pedal only a habit is written out; a key that merely stays down a little longer in a
    # pedalled tune is not a voice of its own.
    close = [(pos, nxt) for pos, nxt in zip(starts, starts[1:]) if nxt - pos <= 1]
    kept = sum(1 for pos, nxt in close if any(n.key_end - float(nxt) >= 1.0 for n in chords[pos]))
    habit = len(close) >= 8 and kept >= 0.15 * len(close)

    for i, pos in enumerate(starts):
        following = starts[i + 1] if i + 1 < len(starts) else None
        after = starts[i + 2] if i + 2 < len(starts) else None
        # A detached note is written at least to the end of its beat.
        to_beat = Fraction(1) if pos.denominator == 1 else Fraction(math.ceil(pos)) - pos

        main: list[Note] = []
        main_length = Fraction(0)
        held: list[Note] = []
        held_end = pos
        for n in chords[pos]:
            key_length = n.key_end - float(pos)
            sound_length = n.snd_end - float(pos)

            if following is not None and max_voices > 1:
                overlap = key_length - float(following - pos)
                next_gap = float(after - following) if after is not None else 1.0
                # Under the pedal nobody can hear whether a key is still down, and a quick
                # pedal change does not damp the strings completely.  So with the pedal in
                # play a held key only counts if it sounds on through a real gap in the pedal –
                # or if it is held on purpose: down for a beat and more after the next note
                # (a bass note under a broken chord, as in Bach's C major prelude).
                since = grid.time_of(float(following))
                up = _pedal_up(pedals, since, n.offset)
                audible = up >= n.offset - since - 1e-6 or up >= 0.25
                deliberate = overlap >= 1.0 and (habit or audible)
                if deliberate or (audible and overlap >= max(0.75 * next_gap, 0.4)):
                    end = snap_length(pos, n.key_end, quantisation, anchors)
                    if end > following:
                        n.held = True
                        held.append(n)
                        held_end = max(held_end, end)
                        continue

            if following is not None:
                gap = following - pos
                triplet = pos.denominator % 3 == 0 and not grid.meter_at(pos).compound
                if pos.denominator != 1 and gap > to_beat and key_length < 0.6 * float(gap) and not (triplet and gap <= 1):
                    # Struck off the beat and let go before the next note: written to the end of
                    # its beat, then a rest.  A tie over the beat says the key stays down; it is
                    # not there to fill a gap (repeated chords with rests between them).
                    # (The middle note of a quarter-note triplet does run over the beat: that
                    # is its value, not a tie.)
                    length = to_beat
                elif gap <= 1 or sound_length >= 0.6 * float(gap):
                    length = gap
                else:
                    end = snap_length(pos, n.snd_end, quantisation, anchors)
                    length = min(gap, max(end - pos, to_beat))
                # What only the pedal carries on is written to the end of its bar at most:
                # a tie over the bar line says the key stays down, and that needs the key.
                bar_end = Fraction(grid.bar_end(pos))
                if pos + length > bar_end:
                    key_held = snap_length(pos, n.key_end, quantisation, anchors)
                    length = min(length, max(bar_end, key_held) - pos)
            else:
                # Last sound of this hand: let it ring to the end of its bar, but not for ever.
                end = snap_length(pos, n.snd_end, quantisation, anchors)
                end = max(end, pos + to_beat)
                bar_end = grid.bar_end(pos)
                if bar_end - 1 <= end < bar_end:
                    end = Fraction(bar_end)
                length = min(end, Fraction(grid.bar_end(bar_end))) - pos
            main.append(n)
            main_length = max(main_length, length)

        if main:
            if staccato and Fraction(1, 2) <= main_length <= 1:
                candidates.append((main, all(_is_staccato(n, pos, main_length) for n in main)))
            events.append(Event(pos, pos + main_length, main))
        if held:
            if main and held_end == pos + main_length:
                events[-1].notes.extend(held)
            else:
                events.append(Event(pos, held_end, held, held=True))

    # Staccato is a way of playing a passage, so a dot needs a detached neighbour;
    # a single short note is more likely a slip of the transcription.
    for i, (chord, detached) in enumerate(candidates):
        before = i > 0 and candidates[i - 1][1]
        behind = i + 1 < len(candidates) and candidates[i + 1][1]
        if detached and (before or behind):
            for n in chord:
                n.staccato = True
    return events


def _is_staccato(n: Note, pos: Fraction, length: Fraction) -> bool:
    """Clearly detached: the key is let go well before half the note and no pedal carries the sound."""
    return (
        n.key_end - float(pos) < 0.42 * float(length)
        and n.snd_end - float(pos) < 0.55 * float(length)
        and n.offset - n.onset < 0.25
    )


def _assign_streams(events: list[Event]) -> None:
    """Distribute the events of one staff over an upper and a lower voice."""
    if any(e.held for e in events):
        groups: dict[Fraction, list[Event]] = {}
        for e in events:
            groups.setdefault(e.start, []).append(e)
        # state: cost, (busy until, pitch, last end) for both streams, trail
        beam = [(0.0, (Fraction(-1), 0.0, None), (Fraction(-1), 0.0, None), None)]
        for start in sorted(groups):
            group = sorted(groups[start], key=lambda e: -e.pitch)
            options = [(0, 1)] if len(group) >= 2 else [(0,), (1,)]
            found: dict[tuple, tuple] = {}
            for cost, upper, lower, trail in beam:
                for option in options:
                    streams = [upper, lower]
                    total = cost
                    for e, s in zip(group, option):
                        busy, pitch, last = streams[s]
                        other_busy, other_pitch, other_last = streams[1 - s]
                        if busy > e.start:
                            total += 6.0  # would cut off what this voice is still holding
                        if other_busy > e.start and ((s == 0) == (e.pitch < other_pitch)):
                            total += 2.5  # voices crossing
                        # Right after a two-voice moment a note continues the voice it is closer to;
                        # otherwise a single line is never spread over two voices.
                        two_voices = (
                            last is not None and other_last is not None
                            and e.start - last <= 1 and e.start - other_last <= 1
                        )
                        if two_voices:
                            total += 0.04 * abs(e.pitch - pitch)
                        if s == 1 and len(group) == 1 and streams[0][0] <= e.start:
                            total += 0.5 if two_voices else 1.0
                        streams[s] = (e.end, e.pitch, e.end)
                    key = (streams[0][0], streams[0][1], streams[1][0], streams[1][1])
                    if key not in found or total < found[key][0]:
                        found[key] = (total, streams[0], streams[1], (trail, option))
            beam = sorted(found.values(), key=lambda c: c[0])[:24]
        trail = beam[0][3]
        choices = []
        while trail is not None:
            trail, option = trail
            choices.append(option)
        for start, option in zip(sorted(groups), reversed(choices)):
            group = sorted(groups[start], key=lambda e: -e.pitch)
            for e, s in zip(group, option):
                e.stream = s
            for e in group[2:]:  # more than two layers at once: fold into the lower voice
                e.stream = 1

    # Within a voice nothing may overlap.
    for stream in (0, 1):
        line = sorted((e for e in events if e.stream == stream), key=lambda e: e.start)
        for current, following in zip(line, line[1:]):
            if following.start == current.start:
                following.notes.extend(current.notes)
                current.notes = []
            elif current.end > following.start:
                current.end = following.start
    events[:] = [e for e in events if e.notes]
