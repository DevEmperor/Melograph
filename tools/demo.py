"""A demo recording for the README pictures: the opening of Bach's Prelude in C major (BWV 846).

The composition is in the public domain; this performance is synthesized here –
with a little human timing, touch and pedal – through FluidSynth.

    .venv/bin/python tools/demo.py bach-prelude.wav
"""

from __future__ import annotations

import random
import subprocess
import sys
import tempfile
from pathlib import Path

import pretty_midi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from melograph.synth import soundfont  # noqa: E402

# (two bass notes, three notes of the figure) per bar, as in the Well-Tempered Clavier
BARS = [
    ("C4 E4", "G4 C5 E5"), ("C4 D4", "A4 D5 F5"), ("B3 D4", "G4 D5 F5"), ("C4 E4", "G4 C5 E5"),
    ("C4 E4", "A4 E5 A5"), ("C4 D4", "F#4 A4 D5"), ("B3 D4", "G4 D5 G5"), ("B3 C4", "E4 G4 C5"),
    ("A3 C4", "E4 G4 C5"), ("D3 A3", "D4 F#4 C5"), ("G3 B3", "D4 G4 B4"), ("G3 Bb3", "E4 G4 C#5"),
    ("F3 A3", "D4 A4 D5"), ("F3 Ab3", "D4 F4 B4"), ("E3 G3", "C4 G4 C5"), ("E3 F3", "A3 C4 F4"),
]


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "bach-prelude.wav").resolve()
    rng = random.Random(7)
    midi = pretty_midi.PrettyMIDI(resolution=960)
    piano = pretty_midi.Instrument(program=0)
    sixteenth = 60 / 66 / 4  # ♩ = 66
    t = 1.0
    for index, (bass, figure) in enumerate(BARS):
        low, high = [pretty_midi.note_name_to_number(n) for n in bass.split()]
        upper = [pretty_midi.note_name_to_number(n) for n in figure.split()]
        bar_start = t
        slow = 1.0 + (0.12 if index == len(BARS) - 1 else 0.0)
        for half in range(2):
            pattern = [low, high] + upper + upper
            for step, pitch in enumerate(pattern):
                on = t + rng.gauss(0, 0.008)
                if step == 0:
                    off = bar_start + half * 8 * sixteenth + 8 * sixteenth * slow - 0.04
                elif step == 1:
                    off = bar_start + half * 8 * sixteenth + 8 * sixteenth * slow - 0.06
                else:
                    off = on + sixteenth * 1.05
                velocity = int(max(30, min(110, rng.gauss(58 if step < 2 else 64, 5))))
                piano.notes.append(pretty_midi.Note(velocity, pitch, on, off))
                t += sixteenth * slow
        # pedal down just after each new harmony, changed with the next bar
        piano.control_changes.append(pretty_midi.ControlChange(64, 127, bar_start + 0.12))
        piano.control_changes.append(pretty_midi.ControlChange(64, 0, t - 0.03))
    midi.instruments.append(piano)
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "demo.mid"
        midi.write(str(source))
        subprocess.run(["fluidsynth", "-ni", "-q", "-g", "0.7", "-r", "44100", "-F", str(out), str(soundfont()), str(source)],
                       check=True, capture_output=True)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
