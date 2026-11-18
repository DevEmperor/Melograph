"""Key signature and enharmonic spelling (is it G sharp or A flat?).

Spelling works on the line of fifths (… A♭ E♭ B♭ F C G D A E B F♯ C♯ …):
notes that belong together harmonically lie close together on it.  Every note
is spelled so that it stays near the key and near what was just played;
chromatic notes then follow their resolution (up → sharp, down → flat), and
chords are kept free of needlessly awkward intervals.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .model import Note

# Temperley's revision of the Krumhansl–Kessler key profiles.
MAJOR = np.array([5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0])
MINOR = np.array([5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0])

STEPS = "FCGDAEB"
STEP_PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


@dataclass
class Key:
    tonic: int  # pitch class
    minor: bool
    fifths: int  # sharps (+) or flats (−) in the signature

    @property
    def tonic_name(self) -> tuple[str, int]:
        return _name(self.fifths + (3 if self.minor else 0))

    def label(self, language: str = "en") -> str:
        step, alter = self.tonic_name
        if language == "de":
            if step == "B":
                name = "B" if alter == -1 else "H" + "is" * alter
            elif alter < 0:
                name = {"A": "As", "E": "Es"}.get(step, step + "es")
            else:
                name = step + "is" * alter
            if self.minor:
                name = name.lower()
            return f"{name}-{'Moll' if self.minor else 'Dur'}"
        name = step + ("♯" * alter if alter > 0 else "♭" * -alter)
        return f"{name} {'minor' if self.minor else 'major'}"


def _line_of_fifths(pitch_class: int) -> int:
    """Position on the line of fifths, C = 0, folded to −5 … 6."""
    position = (pitch_class * 7) % 12
    return position - 12 if position > 6 else position


def _name(position: int) -> tuple[str, int]:
    return STEPS[(position + 1) % 7], (position + 1) // 7


def estimate_key(notes: list[Note]) -> Key:
    histogram = np.zeros(12)
    for n in notes:
        histogram[n.pitch % 12] += 0.2 + min(n.sustain_end - n.onset, 1.5)
    ordered = sorted(notes, key=lambda n: n.onset)
    first_bass = min(ordered[: max(1, len(ordered) // 20)], key=lambda n: n.pitch).pitch % 12
    last_bass = min(ordered[-max(1, len(ordered) // 20):], key=lambda n: n.pitch).pitch % 12

    best, best_score = (0, False), -np.inf
    total = float(histogram.sum()) + 1e-9
    for tonic in range(12):
        for minor, profile in ((False, MAJOR), (True, MINOR)):
            score = float(np.corrcoef(histogram, np.roll(profile, tonic))[0, 1])
            score += 0.06 * (tonic == last_bass) + 0.03 * (tonic == first_bass)
            # A signature should leave as few accidentals in the music as possible
            # (the raised sixth and seventh of a minor key are at home there).
            scale = {0, 2, 3, 5, 7, 8, 9, 10, 11} if minor else {0, 2, 4, 5, 7, 9, 11}
            foreign = sum(histogram[pc] for pc in range(12) if (pc - tonic) % 12 not in scale)
            score -= 4.0 * foreign / total
            if score > best_score:
                best, best_score = (tonic, minor), score
    return make_key(*best)


def make_key(tonic: int, minor: bool) -> Key:
    return Key(tonic, minor, _line_of_fifths((tonic + 3) % 12 if minor else tonic))


def parse_key(text: str) -> Key:
    """'C', 'c', 'Cm', 'F#', 'Bb', 'es', 'fis-moll', 'Eb major' …"""
    raw = text.strip()
    lowered = raw.lower().replace("-", " ").replace("♯", "#").replace("♭", "b")
    minor = "moll" in lowered or "min" in lowered or (raw[:1].islower() and "dur" not in lowered and "maj" not in lowered)
    token = lowered.split()[0] if lowered.split() else ""
    if token.endswith("m") and len(token) > 1 and token not in ("m",):
        token, minor = token[:-1], True
    german = {"h": ("B", 0), "b": ("B", -1), "as": ("A", -1), "es": ("E", -1)}
    if token in german and token != "b":
        step, alter = german[token]
    elif token == "b":
        # "B" alone: German B (= B flat) when written the German way, otherwise B natural.
        step, alter = ("B", -1) if ("dur" in lowered or "moll" in lowered) else ("B", 0)
    else:
        step = token[:1].upper()
        rest = token[1:]
        alter = rest.count("#") + rest.count("is") - rest.count("b") - rest.count("es")
        if step == "H":
            step = "B"
    if step not in STEP_PITCH:
        raise ValueError(text)
    tonic = (STEP_PITCH[step] + alter) % 12
    # Keep the spelling that was asked for: E flat minor stays six flats, not D sharp minor.
    fifths = STEPS.index(step) - 1 + 7 * alter - (3 if minor else 0)
    return Key(tonic, minor, fifths) if abs(fifths) <= 7 else make_key(tonic, minor)


def spell(notes: list[Note], key: Key) -> None:
    """Set `step`, `alter` and `octave` on every note."""
    centre = key.fifths + (3 if key.minor else 2)
    diatonic = range(key.fifths - 1, key.fifths + 6)

    chords: dict = {}
    for n in notes:
        chords.setdefault(n.pos, []).append(n)
    positions: dict[int, int] = {}
    recent: list[tuple[float, int]] = []
    for pos in sorted(chords):
        recent = [(p, x) for p, x in recent if float(pos) - p <= 12][-24:]
        gravity = (16 * centre + sum(x for _, x in recent)) / (16 + len(recent))
        chord = chords[pos]
        chosen = []
        for n in chord:
            base = (n.pitch % 12 * 7) % 12
            chosen.append(base + 12 * round((gravity - base) / 12))
        chosen = _tidy_chord(chosen, diatonic, centre)
        for n, x in zip(chord, chosen):
            positions[id(n)] = x
            recent.append((float(pos), x))

    # Chromatic notes lean towards where they resolve.
    for hand in (0, 1):
        mine = sorted((n for n in notes if n.hand == hand), key=lambda n: (n.pos, n.pitch))
        by_pos: dict = {}
        for n in mine:
            by_pos.setdefault(n.pos, []).append(n)
        starts = sorted(by_pos)
        for here, there in zip(starts, starts[1:]):
            targets = {m.pitch for m in by_pos[there]}
            for n in by_pos[here]:
                x = positions[id(n)]
                if x in diatonic or len(by_pos[here]) > 1:
                    continue
                up, down = n.pitch + 1 in targets, n.pitch - 1 in targets
                if up and not down and x < key.fifths - 1 and x + 12 <= key.fifths + 10:
                    positions[id(n)] = x + 12
                elif down and not up and x > key.fifths + 5 and x - 12 >= key.fifths - 6:
                    positions[id(n)] = x - 12

    for n in notes:
        n.step, n.alter = _name(positions[id(n)])
        n.octave = (n.pitch - n.alter - STEP_PITCH[n.step]) // 12 - 1


def _tidy_chord(chosen: list[int], diatonic: range, centre: int) -> list[int]:
    """Respell chromatic chord notes when that pulls the chord together on the line of fifths."""
    if len(chosen) < 2 or max(chosen) - min(chosen) <= 6:
        return chosen
    movable = [i for i, x in enumerate(chosen) if x not in diatonic][:6]
    best, best_rank = chosen, (max(chosen) - min(chosen), sum(abs(x - centre) for x in chosen))
    for mask in range(1, 3 ** len(movable)):
        trial = list(chosen)
        m = mask
        for i in movable:
            trial[i] += (0, 12, -12)[m % 3]
            m //= 3
        rank = (max(trial) - min(trial), sum(abs(x - centre) for x in trial))
        if rank < best_rank:
            best, best_rank = trial, rank
    return best
