"""Pieces that change on the way: tempo, metre and key, section by section."""

from __future__ import annotations

import re

import numpy as np

from melograph.beats import build_grid, find_beats
from melograph.export import musicxml_text
from melograph.model import LEFT, RIGHT
from melograph.pipeline import Options, analyse

from .music import heard, pitch, play


def listen(performance, beats, downbeats, weak=(), **options):
    """Analyse through the path of a recording: the tracker's probabilities instead of a list of beats."""
    tracked = heard(beats, downbeats, performance.duration, weak)
    return analyse(performance, None, None, Options(title="Test", **options), tracked)


def bar_lengths(result) -> list[int]:
    return [int(b - a) for a, b in zip(result.layout.starts, result.layout.starts[1:])]


def test_pulse_stays_on_one_level_where_the_tracker_counts_half_notes():
    """In the middle the tracker hears every other beat only faintly; the beat must not double in length."""
    line = " ".join(["c5:1/2 d5:1/2 e5:1/2 f5:1/2 g5:1/2 f5:1/2 e5:1/2 d5:1/2"] * 12)
    bass = " ".join(["c3:1 g3:1 c3:1 g3:1"] * 12)
    perf, beats, downs = play(line, bass, bpm=120)
    weak = [t for i, t in enumerate(beats) if 16 <= i < 32 and i % 2]
    found = find_beats(heard(beats, downs, perf.duration, weak), perf.notes)
    gaps = np.diff(found[(found > beats[2]) & (found < beats[-3])])
    assert abs(float(np.median(gaps)) - 0.5) < 0.02
    assert gaps.max() < 0.65 and gaps.min() > 0.38


def test_tracker_marking_a_beat_twice_gives_one_beat():
    perf, beats, downs = play(" ".join(["c5:1 e5:1 g5:1 e5:1"] * 6), " ".join(["c3:2 g3:2"] * 6), bpm=100)
    doubled = np.sort(np.concatenate([beats, beats + 0.07]))
    found = find_beats(heard(doubled, downs, perf.duration), perf.notes)
    inside = found[(found > beats[1]) & (found < beats[-2])]
    assert abs(float(np.median(np.diff(inside))) - 0.6) < 0.03 and np.diff(inside).min() > 0.45


def test_fast_waltz_is_counted_in_quarters_and_bars_of_three():
    """Every beat equally clear: the pulse must not step over every other one (and so lose the bars of three)."""
    tune = " ".join(["c5:1 e5:1 g5:1 f5:1 a5:1 c6:1"] * 8)
    bass = " ".join(["c3:1 [e3 g3]:1 [e3 g3]:1 f2:1 [a3 c4]:1 [a3 c4]:1"] * 8)
    for bpm in (170, 200):
        perf, beats, downs = play(tune, bass, bpm=bpm, beats_per_bar=3)
        result = listen(perf, beats, downs)
        assert str(result.meter) == "3/4" and result.bars == 16 and abs(result.tempo[1] - bpm) <= 5


def test_slow_piece_keeps_its_slow_beat():
    """Sixteenths at 48 to the minute stay sixteenths: the beat is not doubled just because it is slow."""
    tune = " ".join(["c5:1/4 d5:1/4 e5:1/4 f5:1/4 g5:1/4 f5:1/4 e5:1/4 d5:1/4 c5:1 g4:1"] * 6)
    perf, beats, downs = play(tune, " ".join(["c3:2 g2:2"] * 6), bpm=48)
    result = listen(perf, beats, downs)
    assert str(result.meter) == "4/4" and result.bars == 6 and result.tempo[1] == 48


def test_new_tempo_gets_a_new_metronome_mark_and_bars_stay_regular():
    def seconds(beat):  # 8 bars at 90, then 8 bars at 132
        beat = float(beat)
        return 1.0 + (beat * 60 / 90 if beat <= 32 else 32 * 60 / 90 + (beat - 32) * 60 / 132)

    perf, beats, downs = play(" ".join(["c5:1 e5:1 g5:1 e5:1"] * 16), " ".join(["c3:2 g3:2"] * 16), tempo=seconds)
    result = listen(perf, beats, downs)
    assert set(bar_lengths(result)) == {4} and result.bars == 16
    tempos = [(result.layout.bar_of(m.pos) + 1, m.bpm) for m in result.marks.tempos if m.bpm]
    assert len(tempos) == 2
    assert tempos[0][0] == 1 and abs(tempos[0][1] - 90) < 4
    assert tempos[1][0] == 9 and abs(tempos[1][1] - 132) < 5


def test_metronome_mark_stands_where_the_new_tempo_begins():
    """A tempo that differs only just enough from an unsteady one before it is noticed late;
    the mark still belongs to the bar where it began."""
    from fractions import Fraction

    from melograph.beats import Grid
    from melograph.marks import tempo_marks
    from melograph.model import Note

    # six bars at 135, then the quicker tempo: at first not quite far enough from the old one to be sure of
    bars = [135, 136, 134, 135, 136, 134] + [144, 145, 144, 145] + [149, 150] * 6
    times = [0.0]
    for bpm in bars:
        start = times[-1]
        times += [start + (k + 1) * 60 / bpm for k in range(4)]
    grid = Grid(np.array(times), 4, 0, "notes")
    notes = []
    for beat in range(len(times) - 1):
        note = Note(60, times[beat], times[beat] + 0.2, 70)
        note.pos = Fraction(beat)
        notes.append(note)
    marks = [(int(m.pos) // 4 + 1, round(m.bpm)) for m in tempo_marks(notes, grid) if m.bpm]
    assert [bar for bar, _ in marks] == [1, 7] and abs(marks[1][1] - 148) <= 3


def test_bars_of_three_inside_a_piece_in_four():
    four = " ".join(["c5:1 e5:1 g5:1 e5:1"] * 6)
    three = " ".join(["c5:1 e5:1 g5:1"] * 6)
    perf, beats, _ = play(four + " " + three + " " + four, " ".join(["c3:4"] * 6 + ["c3:3"] * 6 + ["c3:4"] * 6))
    starts = [4 * i for i in range(6)] + [24 + 3 * i for i in range(6)] + [42 + 4 * i for i in range(7)]
    result = listen(perf, beats, beats[[s for s in starts if s < len(beats)]])
    assert bar_lengths(result) == [4] * 6 + [3] * 6 + [4] * 6
    xml = musicxml_text(result.score)
    assert re.findall(r"<beats>(\d)</beats>", xml) == ["4", "3", "4"]


def test_a_pause_is_one_long_beat_not_a_row_of_empty_ones():
    """Four bars, a fermata of three seconds on the last note, four more bars: all bars keep four beats."""
    def seconds(beat):
        return 1.0 + float(beat) * 0.6 + (3.0 if beat >= 16 else 0.0)

    perf, beats, downs = play(" ".join(["c5:1 e5:1 g5:1 e5:1"] * 8), " ".join(["c3:2 g3:2"] * 8), tempo=seconds)
    result = listen(perf, beats, downs)
    assert bar_lengths(result) == [4] * 8
    assert any(n.fermata for n in result.notes)


def test_key_signature_follows_a_modulation():
    c_major = " ".join(["c5:1 d5:1 e5:1 f5:1 g5:1 a5:1 b5:1 c6:1"] * 4)
    a_major = " ".join(["a4:1 b4:1 c#5:1 d5:1 e5:1 f#5:1 g#5:1 a5:1"] * 4)
    bass = " ".join(["c3:2 g3:2 c3:2 g2:2"] * 4 + ["a2:2 e3:2 a2:2 e2:2"] * 4)
    perf, beats, downs = play(c_major + " " + a_major, bass)
    result = analyse(perf, beats, downs, Options(title="Test"))
    assert [k.fifths for k in result.keys] == [0] * 8 + [3] * 8
    assert result.keys[0].label("en") == "C major" and result.keys[-1].label("en") == "A major"
    xml = musicxml_text(result.score)
    assert xml.count("<fifths>0</fifths>") == 1 and xml.count("<fifths>3</fifths>") == 1
    assert "light-light" in xml  # a double bar line announces the new signature
    # in A major the notes need no accidentals
    assert all(n.alter == (1 if n.step in "FCG" else 0) for n in result.notes if n.pos >= result.layout.starts[8])
    # a key that is asked for holds for the whole piece
    assert {k.fifths for k in analyse(perf, beats, downs, Options(key="C")).keys} == {0}


def test_passing_accidentals_do_not_change_the_signature():
    tune = "c5:1 d5:1 e5:1 f5:1 g5:1 f#5:1 g5:2 a5:1 g5:1 f5:1 e5:1 d5:1 c#5:1 d5:2 " * 3 + "c5:4"
    perf, beats, downs = play(tune, " ".join(["c3:2 g3:2"] * 13))
    result = analyse(perf, beats, downs, Options(title="Test"))
    assert {k.fifths for k in result.keys} == {0}


def test_stretch_in_threes_is_written_in_compound_time():
    eighths = " ".join(["c5:1/2 d5:1/2 e5:1/2 f5:1/2 g5:1/2 f5:1/2 e5:1/2 d5:1/2"] * 4)
    threes = " ".join(["c5:1/3 e5:1/3 g5:1/3 c6:1/3 g5:1/3 e5:1/3 c5:1/3 e5:1/3 g5:1/3 c6:1/3 g5:1/3 e5:1/3"] * 6)
    perf, beats, downs = play(eighths + " " + threes, " ".join(["c3:2 g3:2"] * 10))
    result = analyse(perf, beats, downs, Options(title="Test"))
    assert [str(m) for m in result.layout.meters] == ["4/4"] * 4 + ["12/8"] * 6
    assert not any(atom.tuplet for bar in result.layout.bars for staff in bar.staves for voice in staff for atom in voice)
    xml = musicxml_text(result.score)
    assert "<beats>12</beats>" in xml and "<beat-unit-dot" in xml  # the tempo again, on the dotted quarter


def test_accompaniment_stays_in_the_left_hand_when_it_climbs():
    """An ostinato around middle C under held notes of the right hand, as at the start of many themes."""
    tune = "[f5 ab5]:2 db5:2 [eb5 g5]:3 ab5:1 " * 5
    ostinato = " ".join(["db4:1/2 ab4:1/2"] * 8 + ["db4:1/2 bb4:1/2"] * 8) + " "
    perf, beats, downs = play(tune, ostinato * 2 + " ".join(["db4:1/2 ab4:1/2"] * 16), bpm=130, pedals=[(0, 39.5)])
    result = analyse(perf, beats, downs, Options(title="Test"))
    low = [n for n in result.notes if n.pitch in (pitch("db4"), pitch("ab4"), pitch("bb4"))]
    assert all(n.hand == LEFT for n in low)
    assert all(n.hand == RIGHT for n in result.notes if n.pitch >= pitch("db5"))


def test_figure_over_a_repeated_note_stays_in_the_right_hand():
    """Sixteenths that keep coming back to one key, over an accompaniment that repeats the note
    below it: the figure is the right hand's, octaves and all, however close the two come."""
    figure = "[f4 f5]:1/2 bb4:1/4 f4:1/4 c5:1/4 f4:1/4 bb4:1/4 f4:1/4 f5:1/4 f4:1/4 bb4:1/4 f4:1/4 c5:1/4 f4:1/4 bb4:1/4 f4:1/4 "
    octaves = "e5:1/4 e4:1/4 g4:1/4 e4:1/4 c5:1/4 e4:1/4 g4:1/4 e4:1/4 e5:2/3 [f4 f5]:2/3 [g4 g5]:2/3 "
    perf, beats, downs = play(figure * 2 + octaves + figure * 2, "bb3:1/2 " * 40, bpm=140, legato=0.5)
    result = analyse(perf, beats, downs, Options(title="Test"))
    assert all(n.hand == LEFT for n in result.notes if n.pitch == pitch("bb3"))
    assert all(n.hand == RIGHT for n in result.notes if n.pitch > pitch("bb3"))
    # the octaves of the triplet are written together, in the right hand's triplet
    third = [atom for voice in result.layout.bars[2].staves[RIGHT] for atom in voice if atom.tuplet]
    assert [len(atom.notes) for atom in third] == [1, 2, 2]


def test_repeated_chords_with_rests_keep_their_rests():
    """♪♪ 𝄾 ♪ – the chord before the rest is not stretched over the beat and tied."""
    cell = "[c5 e5]:1/2. [c5 e5]:1/2. r:1/2 [c5 e5]:1/2. "
    perf, beats, downs = play(cell * 8, "c3:4 " * 4)
    result = analyse(perf, beats, downs, Options(title="Test"))
    upper = [atom for bar in result.layout.bars for atom in bar.staves[RIGHT][0]]
    assert not any(atom.tie_in or atom.tie_out for atom in upper)
    assert [(atom.kind, bool(atom.notes)) for atom in upper[:4]] == [
        ("eighth", True), ("eighth", True), ("eighth", False), ("eighth", True),
    ]


def test_key_held_now_and_then_under_the_pedal_is_no_second_voice():
    """A tune under the pedal with one key left down a little longer: one voice, no tied leftovers."""
    perf, beats, downs = play("c5:1 e5:1 g5:1 c6:1 " * 4, "c3:4 " * 4, pedals=[(0, 15.5)])
    first = min(perf.notes, key=lambda n: (n.onset, -n.pitch))
    first.offset += 1.4  # the first key of the tune stays down through the next two notes
    result = analyse(perf, beats, downs, Options(title="Test"))
    assert all(n.voice == 0 for n in result.notes if n.hand == RIGHT)


def test_octave_line_only_far_above_the_staff():
    high = "c7:1/2 e7:1/2 g7:1/2 c8:1/2 g7:1/2 e7:1/2 c7:1/2 g6:1/2 " * 2
    middle = "c6:1/2 e6:1/2 g6:1/2 a6:1/2 g6:1/2 e6:1/2 c6:1/2 g5:1/2 " * 2
    perf, beats, downs = play(middle + high + middle, "c3:4 " * 6)
    result = analyse(perf, beats, downs, Options(title="Test"))
    assert len(result.marks.ottavas) == 1
    line = result.marks.ottavas[0]
    assert line.kind == "8va" and result.layout.bar_of(line.first.pos) == 2 and result.layout.bar_of(line.last.pos) == 3
    assert all(n.shift == 0 for n in result.notes if n.pos < result.layout.starts[2])


def test_grid_from_given_beats_is_unchanged_by_doubled_beats():
    perf, beats, downs = play(" ".join(["c5:1 e5:1 g5:1 e5:1"] * 8), " ".join(["c3:2 g3:2"] * 8))
    messy = np.sort(np.concatenate([beats, beats[5:12] + 0.06]))
    grid = build_grid(perf, messy, downs)
    assert abs(grid.bpm - 100) < 1 and grid.beats_per_bar == 4
