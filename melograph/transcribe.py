"""Audio → performance: which keys were pressed when, how hard, and the pedal.

Uses Transkun (Yan & Duan, ISMIR 2024), a transformer with a neural semi-CRF
that is among the most accurate open piano transcribers.
"""

from __future__ import annotations

import math
from importlib import resources
from pathlib import Path
from typing import Callable

import numpy as np

from .audio import SAMPLE_RATE
from .model import Note, Pedal, Performance

SUSTAIN = 64
PHANTOM = 0.6  # an overtone heard as a note has at most this share of the loudness of its note


def pick_device(requested: str = "auto") -> str:
    """Use the GPU only when it is there and has room; otherwise the CPU."""
    import torch

    if requested != "auto":
        return requested
    if not torch.cuda.is_available():
        return "cpu"
    try:
        free, _total = torch.cuda.mem_get_info()
    except Exception:
        return "cpu"
    return "cuda" if free > 2.5 * 1024**3 else "cpu"


def transcribe(
    audio: np.ndarray,
    device: str = "cpu",
    progress: Callable[[int, int], None] | None = None,
) -> Performance:
    """Transcribe float32 stereo audio (samples, 2) at 44.1 kHz."""
    import moduleconf
    import torch

    package = resources.files("transkun") / "pretrained"
    with resources.as_file(package / "2.0.conf") as conf_path:
        conf_manager = moduleconf.parseFromFile(str(conf_path))
    model_class = conf_manager["Model"].module.TransKun
    conf = conf_manager["Model"].config

    with resources.as_file(package / "2.0.pt") as weight_path:
        checkpoint = torch.load(str(weight_path), map_location=device, weights_only=False)
    model = model_class(conf=conf).to(device)
    state = checkpoint.get("best_state_dict") or checkpoint["state_dict"]
    model.load_state_dict(state, strict=False)
    model.eval()

    if progress is not None:
        # Transkun works through the recording in overlapping segments; count them.
        step = math.ceil(model.segmentHopSizeInSecond * model.fs / model.hopSize) * model.hopSize
        pad = math.ceil((model.segmentSizeInSecond - model.segmentHopSizeInSecond) * model.fs)
        total = max(1, math.ceil((len(audio) + 2 * pad) / step))
        done = 0
        original = model.transcribeFrames

        def counted(*args, **kwargs):
            nonlocal done
            result = original(*args, **kwargs)
            done += 1
            progress(min(done, total), total)
            return result

        model.transcribeFrames = counted
        progress(0, total)

    with torch.no_grad():
        events = model.transcribe(torch.from_numpy(audio).to(device))

    notes: list[Note] = []
    pedals: list[Pedal] = []
    for event in events:
        if event.pitch > 0:
            if event.end - event.start > 0.005:
                notes.append(Note(int(event.pitch), float(event.start), float(event.end), int(event.velocity)))
        elif -event.pitch == SUSTAIN:
            pedals.append(Pedal(float(event.start), float(event.end)))
    notes.sort(key=lambda n: (n.onset, n.pitch))
    pedals.sort(key=lambda p: p.start)
    return finish(Performance(_without_overtones(notes), pedals, len(audio) / SAMPLE_RATE))


def _without_overtones(notes: list[Note]) -> list[Note]:
    """Drop notes that are really the overtone of another note.

    A bright string can make the transcriber hear its octave or twelfth as a
    key of its own.  Such a phantom starts together with the real note, is much
    softer and no longer.  A key that is about as loud as the one below it was
    played: octaves are what pianists' hands do all the time, and a figure of
    one hand keeps meeting the repeated note of the other.  A soft line really
    played in octaves looks like phantoms note by note – but there nearly every
    note of the line is doubled, while phantoms turn up only here and there.
    """
    from bisect import bisect_left, bisect_right

    onsets = [n.onset for n in notes]  # notes are sorted by onset
    source: dict[int, Note] = {}  # suspect → the note it may be an overtone of
    for n in notes:
        for o in notes[bisect_left(onsets, n.onset - 0.04):bisect_right(onsets, n.onset + 0.04)]:
            if (
                n.pitch - o.pitch in (12, 19, 24)
                and n.velocity <= PHANTOM * o.velocity
                and n.offset - n.onset <= 1.2 * (o.offset - o.onset) + 0.03
            ):
                source[id(n)] = o
                break
    doubled = {id(o) for o in source.values()}
    kept: list[Note] = []
    for n in notes:
        o = source.get(id(n))
        if o is not None:
            around = notes[bisect_left(onsets, n.onset - 2.0):bisect_right(onsets, n.onset + 2.0)]
            line = [m for m in around if id(m) not in source and abs(m.pitch - o.pitch) <= 7]
            if sum(id(m) in doubled for m in line) < 0.5 * len(line):
                continue
        kept.append(n)
    return kept


def finish(performance: Performance) -> Performance:
    """Work out how long each note really sounds once the pedal is taken into account."""
    notes, pedals = performance.notes, performance.pedals
    next_same_pitch: dict[int, float] = {}
    following = [math.inf] * len(notes)
    for index in range(len(notes) - 1, -1, -1):
        note = notes[index]
        following[index] = next_same_pitch.get(note.pitch, math.inf)
        next_same_pitch[note.pitch] = note.onset
    for note, restrike in zip(notes, following):
        end = note.offset
        for pedal in pedals:
            # The pedal catches a note when it is down at the moment the key is released.
            if pedal.start <= note.offset + 0.03 and pedal.end > note.offset:
                end = max(end, pedal.end)
        note.sustain_end = max(note.offset, min(end, restrike))
    if notes:
        performance.duration = max(performance.duration, max(n.sustain_end for n in notes))
    return performance


def read_midi(path: Path) -> Performance:
    """Read a performance MIDI file (e.g. one written earlier by Melograph)."""
    import pretty_midi

    midi = pretty_midi.PrettyMIDI(str(path))
    notes: list[Note] = []
    pedals: list[Pedal] = []
    for instrument in midi.instruments:
        if instrument.is_drum:
            continue
        for n in instrument.notes:
            if n.end - n.start > 0.005:
                notes.append(Note(int(n.pitch), float(n.start), float(n.end), int(n.velocity)))
        down: float | None = None
        for change in sorted(instrument.control_changes, key=lambda c: c.time):
            if change.number != SUSTAIN:
                continue
            if change.value >= 64 and down is None:
                down = change.time
            elif change.value < 64 and down is not None:
                pedals.append(Pedal(down, change.time))
                down = None
        if down is not None:
            pedals.append(Pedal(down, midi.get_end_time()))
    notes.sort(key=lambda n: (n.onset, n.pitch))
    pedals.sort(key=lambda p: p.start)
    return finish(Performance(notes, pedals, midi.get_end_time()))


def write_midi(performance: Performance, path: Path) -> None:
    """Save the performance as a standard MIDI file."""
    import pretty_midi

    midi = pretty_midi.PrettyMIDI(resolution=960)
    piano = pretty_midi.Instrument(program=0, name="Piano")
    for n in performance.notes:
        piano.notes.append(pretty_midi.Note(velocity=max(1, min(127, n.velocity)), pitch=n.pitch, start=n.onset, end=n.offset))
    for p in performance.pedals:
        piano.control_changes.append(pretty_midi.ControlChange(SUSTAIN, 127, p.start))
        piano.control_changes.append(pretty_midi.ControlChange(SUSTAIN, 0, p.end))
    midi.instruments.append(piano)
    midi.write(str(path))
