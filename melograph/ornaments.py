"""Ornaments that have to be recognised before the rhythm: rolled chords and trills.

Both are played far faster than anything that is written out note by note.
Left in, a trill would become a cloud of 32nd notes and a rolled chord a
staircase of tiny values; recognised, they become one note with "tr" and one
chord with an arpeggio line.
"""

from __future__ import annotations

from .beats import Grid
from .model import Note

ROLL_STEP = 0.09  # seconds at most between two notes of a rolled chord
ROLL_SPAN = 0.35  # seconds at most from the first to the last note
TRILL_STEP = 0.125  # seconds at most between the notes of a trill


def find_rolls(notes: list[Note], grid: Grid) -> int:
    """Mark rolled chords (`roll` on their notes). Returns how many were found."""
    ordered = sorted(notes, key=lambda n: (n.onset, n.pitch))
    count = 0
    for i, start in enumerate(ordered):
        if start.roll:
            continue
        group = [start]
        for n in ordered[i + 1:]:
            if n.onset - group[-1].onset > ROLL_STEP or n.onset - start.onset > ROLL_SPAN:
                break
            # The roll climbs note by note; notes struck together with it (a melody
            # note on the beat, the other hand) are passed over, not counted.
            if not n.roll and n.pitch > group[-1].pitch and n.onset - group[-1].onset >= 0.012:
                group.append(n)
        spread = group[-1].onset - group[0].onset
        held = all(m.offset > group[-1].onset + 0.08 for m in group)
        beat = grid.beat_seconds(int(grid.beat_of(start.onset)))
        if len(group) >= 3 and spread >= 0.05 and held and spread < 0.3 * beat:
            # Evenly spread, like a hand rolling over the keys, not a figure in rhythm.
            steps = [b.onset - a.onset for a, b in zip(group, group[1:])]
            if max(steps) <= 3.0 * min(steps):
                count += 1
                for m in group:
                    m.roll = count
    return count


def find_trills(notes: list[Note], grid: Grid) -> list[Note]:
    """Replace each trill by its main note with `trill` set. Returns the new list of notes."""
    ordered = sorted(notes, key=lambda n: (n.onset, n.pitch))
    used: set[int] = set()
    result: list[Note] = []
    for i, first in enumerate(ordered):
        if id(first) in used:
            continue
        chain = [first]
        pitches: set[int] = {first.pitch}
        for n in ordered[i + 1:]:
            if n.onset - chain[-1].onset > TRILL_STEP:
                break
            if id(n) in used or abs(n.pitch - chain[-1].pitch) > 2 or n.pitch == chain[-1].pitch:
                continue
            if len(pitches) == 2 and n.pitch not in pitches:
                break
            if len(pitches) == 1 and abs(n.pitch - first.pitch) not in (1, 2):
                continue
            chain.append(n)
            pitches.add(n.pitch)
        if len(chain) < 5 or len(pitches) != 2:
            continue
        # A trill alternates strictly and is faster than the music around it.
        if not all(chain[k].pitch == chain[k % 2].pitch for k in range(len(chain))):
            continue
        beat = grid.beat_seconds(int(grid.beat_of(first.onset)))
        steps = [b.onset - a.onset for a, b in zip(chain, chain[1:])]
        if sum(steps) / len(steps) > 0.22 * beat:
            continue  # slow enough to be written out (e.g. sixteenths at a slow tempo)
        main_pitch = chain[-1].pitch  # a trill ends on its main note
        main = Note(
            pitch=main_pitch, onset=first.onset, offset=max(n.offset for n in chain),
            velocity=max(n.velocity for n in chain),
        )
        main.sustain_end = max(n.sustain_end for n in chain)
        main.trill = True
        used.update(id(n) for n in chain)
        result.append(main)
    result.extend(n for n in ordered if id(n) not in used)
    result.sort(key=lambda n: (n.onset, n.pitch))
    return result
