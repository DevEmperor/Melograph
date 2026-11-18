"""Pieces with a known score: does Melograph write what was played?"""

from __future__ import annotations

import re
from fractions import Fraction as F

import pytest

from melograph.export import musicxml_text
from melograph.model import LEFT, RIGHT, Note
from melograph.pipeline import Options, analyse

from .music import pitch, play


def run(performance, beats, downbeats, **options):
    return analyse(performance, beats, downbeats, Options(title="Test", **options))


def start(result):
    """Position of the first note: the beat grid begins a little before the music."""
    return min(n.pos for n in result.notes)


def test_plain_melody_with_bass():
    perf, beats, downs = play(
        "d5:1 g5:3/2 a5:1/2 b5:1 d6:1 c6:1/2 b5:1/2 a5:1/2 g5:1/2 a5:2 g5:4",
        "r:1 g2:2 d3:2 c3:2 d3:2 g2:4",
        jitter=0.012,
    )
    result = run(perf, beats, downs)
    assert str(result.meter) == "4/4"
    assert result.key.label("en") == "G major"
    o = start(result)
    assert [n.pos - o for n in sorted(result.notes, key=lambda n: n.onset) if n.hand == RIGHT][:4] == [
        F(0), F(1), F(5, 2), F(3)]
    assert all(n.hand == LEFT for n in result.notes if n.pitch < 55)


def test_pedal_marks_follow_the_harmony():
    perf, beats, downs = play(
        "e5:1 g5:1 c6:1 g5:1 f5:1 a5:1 c6:1 a5:1 d5:1 g5:1 b5:1 g5:1 c5:4",
        "c3:2 g3:2 f3:2 c4:2 g2:2 d3:2 c3:4",
        pedals=[(0.2, 3.9), (4.2, 7.9), (8.2, 11.85)],
    )
    result = run(perf, beats, downs)
    lines, o = result.marks.pedals, start(result)
    assert len(lines) == 1
    assert lines[0].start == o and [c - o for c in lines[0].changes] == [4, 8] and lines[0].end - o == 12
    xml = musicxml_text(result.score)
    # every press of the pedal is a line of its own (one long line is drawn unreliably)
    assert len(re.findall(r'<pedal [^>]*type="start"', xml)) == 3
    assert len(re.findall(r'<pedal [^>]*type="stop"', xml)) == 3 and 'type="change"' not in xml


def test_pedal_all_the_way_through_is_con_pedale():
    perf, beats, downs = play(
        " ".join(["e5:1 g5:1 c6:1 g5:1"] * 8),
        " ".join(["c3:2 g3:2"] * 8),
        pedals=[(4 * bar + 0.2, 4 * (bar + 1) - 0.1) for bar in range(8)],  # in beats: down for nearly every bar
    )
    result = run(perf, beats, downs)
    xml = musicxml_text(result.score)
    assert not result.marks.pedals and "<pedal" not in xml and "con pedale" in xml
    assert len(run(perf, beats, downs, pedal="lines").marks.pedals) == 1


def test_slur_over_legato_but_not_over_staccato():
    perf, beats, downs = play(
        "c5:1/2 d5:1/2 e5:1/2 f5:1/2 g5:1/2 a5:1/2 b5:1/2 c6:1/2 "
        "g5:1/2. e5:1/2. c5:1/2. e5:1/2. g5:1/2. e5:1/2. c5:1. ",
        "c3:4 c3:4",
        legato=1.04,
    )
    result = run(perf, beats, downs)
    right = [s for s in result.marks.slurs if s.hand == RIGHT]
    assert len(right) == 1
    o = start(result)
    assert right[0].first.pitch == pitch("c5") and right[0].first.pos == o
    assert right[0].last.pitch == pitch("c6")
    assert all(n.staccato for n in result.notes if n.hand == RIGHT and 4 <= n.pos - o < 7)
    assert "<slur" in musicxml_text(result.score)


def test_trill_becomes_one_note():
    trill = " ".join(["f5:1/8 e5:1/8"] * 8)
    perf, beats, downs = play(f"c5:1 d5:1 {trill} e5:2 d5:2 c5:4", "c3:4 g2:4 c3:4", bpm=90)
    result = run(perf, beats, downs)
    trills = [n for n in result.notes if n.trill]
    assert len(trills) == 1 and trills[0].pitch == pitch("e5") and trills[0].pos - start(result) == 2
    assert not [n for n in result.notes if n.pitch == pitch("f5")]
    assert "<trill-mark" in musicxml_text(result.score)


def test_rolled_chord_is_one_chord_with_an_arpeggio_line():
    perf, beats, downs = play("e5:2 d5:2 c5:4", "r:4 r:4", bpm=80)
    roll_start = beats[0]
    for k, name in enumerate(["c3", "g3", "e4", "g4", "c5"]):
        on = roll_start + 0.035 * k
        perf.notes.append(Note(pitch(name), on, on + 1.4, 64, sustain_end=on + 1.4))
    perf.notes.sort(key=lambda n: (n.onset, n.pitch))
    result = run(perf, beats, downs)
    rolled = [n for n in result.notes if n.roll]
    assert len(rolled) == 5 and len({n.pos for n in rolled}) == 1 and rolled[0].pos == start(result)
    assert "<arpeggiate" in musicxml_text(result.score)


def test_high_passage_gets_an_octave_line():
    perf, beats, downs = play(
        "g5:1 c6:1 e6:1 g6:1 c7:1/2 d7:1/2 e7:1/2 f7:1/2 g7:1/2 f7:1/2 e7:1/2 d7:1/2 c7:2 g6:2 c6:4",
        "c3:4 c3:4 c3:4 c3:4",
    )
    result = run(perf, beats, downs)
    assert any(o.kind == "8va" and o.hand == RIGHT for o in result.marks.ottavas)
    assert all(n.shift == -1 for n in result.notes if n.pitch >= pitch("c7"))
    assert "<octave-shift" in musicxml_text(result.score)


def test_left_hand_high_up_gets_a_treble_clef():
    perf, beats, downs = play(
        "c6:4 e6:4 g6:4 e6:4 c6:4 c6:4",
        "c3:4 [c4 e4 g4]:2 [d4 g4 b4]:2 [e4 g4 c5]:2 [g4 c5 e5]:2 [c4 e4 g4]:4 c2:4 c3:4",
    )
    result = run(perf, beats, downs)
    clefs = result.marks.clefs[LEFT]
    assert clefs[0] == "F" and "G" in clefs[1:4] and clefs[-1] == "F"
    assert musicxml_text(result.score).count("<clef") >= 3


def test_swung_eighths_are_written_straight():
    swung = " ".join(["c5:2/3 d5:1/3 e5:2/3 g5:1/3"] * 8)
    perf, beats, downs = play(swung, " ".join(["c3:1 g3:1"] * 8), bpm=120, jitter=0.008)
    result = run(perf, beats, downs)
    assert result.marks.swing
    assert str(result.meter) == "4/4"
    assert {n.pos % 1 for n in result.notes if n.hand == RIGHT} == {F(0), F(1, 2)}
    assert "Swing" in musicxml_text(result.score)


def test_quarter_note_triplets_share_one_bracket():
    perf, beats, downs = play(
        "c5:1 d5:1 e5:1 f5:1 g5:2/3 a5:2/3 b5:2/3 c6:2 c6:4",
        "c3:4 c3:4 c3:4",
    )
    result = run(perf, beats, downs)
    second_bar = result.layout.bars[1].staves[RIGHT][0]
    triplets = [a for a in second_bar if a.tuplet]
    assert [a.kind for a in triplets] == ["quarter"] * 3
    assert {a.tuplet_unit for a in triplets} == {"quarter"}


def test_crescendo_hairpin_from_a_rising_line():
    perf, beats, downs = play(
        " ".join(["c5:1 e5:1 g5:1 e5:1"] * 6) + " c6:4",
        " ".join(["c3:2 g3:2"] * 7),
    )
    # two quiet bars, a rise over two bars, two loud bars
    for n in perf.notes:
        n.velocity = int(40 + 70 * min(1.0, max(0.0, (n.onset - 4.8) / 4.8)))
    result = run(perf, beats, downs)
    wedges = [h for h in result.marks.hairpins if h.crescendo and not h.words]
    assert len(wedges) == 1 and 4 <= wedges[0].start - start(result) <= 12 and wedges[0].end - wedges[0].start <= 8
    assert result.marks.dynamics[0][1] in ("pp", "p")
    assert result.marks.dynamics[-1][1] in ("f", "ff")
    assert "<wedge" in musicxml_text(result.score)


def test_very_long_crescendo_is_written_as_a_word():
    perf, beats, downs = play(
        " ".join(["c5:1 e5:1 g5:1 e5:1"] * 10) + " c6:4",
        " ".join(["c3:2 g3:2"] * 11),
    )
    ordered = sorted(perf.notes, key=lambda n: n.onset)
    for i, n in enumerate(ordered):
        n.velocity = int(40 + 70 * i / len(ordered))
    result = run(perf, beats, downs)
    assert any(h.crescendo and h.words for h in result.marks.hairpins)
    assert "cresc." in musicxml_text(result.score)


def test_ritardando_at_the_end():
    def seconds(beat):
        beat = float(beat)
        # 100 beats per minute, then slowing to about 60 over the last two bars
        if beat <= 24:
            return 1.0 + beat * 0.6
        extra = beat - 24
        return 1.0 + 24 * 0.6 + extra * 0.6 + 0.03 * extra * extra

    perf, beats, downs = play(
        " ".join(["c5:1 e5:1 g5:1 e5:1"] * 7) + " c5:4",
        " ".join(["c3:2 g3:2"] * 8),
        tempo=seconds,
    )
    result = run(perf, beats, downs)
    texts = [m.text for m in result.marks.tempos if m.text]
    assert "rit." in texts
    assert result.marks.tempos[0].bpm == pytest.approx(100, rel=0.05)


def test_chord_symbols_name_a_simple_progression():
    perf, beats, downs = play(
        "e5:4 f5:4 d5:4 e5:4",
        "[c3 g3 c4 e4]:4 [f2 c3 f3 a3]:4 [g2 d3 f3 b3]:4 [c3 g3 c4 e4]:4",
    )
    result = run(perf, beats, downs, chords=True)
    assert [c.figure for c in result.marks.chords] == ["C", "F", "G7", "C"]
    assert [c.pos - start(result) for c in result.marks.chords] == [0, 4, 8, 12]
    assert "<harmony" in musicxml_text(result.score)


def test_score_loads_in_verovio():
    import verovio

    perf, beats, downs = play(
        "d5:1 g5:3/2 a5:1/2 b5:1 d6:1 c6:1/2 b5:1/2 a5:1/2 g5:1/2 a5:2 g5:4",
        "r:1 g2:2 d3:2 c3:2 d3:2 g2:4",
        pedals=[(1.2, 4.9), (5.1, 9)],
    )
    result = run(perf, beats, downs, chords=True)
    toolkit = verovio.toolkit()
    assert toolkit.loadData(musicxml_text(result.score))
    assert toolkit.getPageCount() == 1


def test_engraving_keeps_decimal_points_under_a_german_locale():
    """Qt switches to the desktop's number format; Verovio's SVG must not get "0,72"."""
    import locale
    import re

    from melograph.render import engrave

    perf, beats, downs = play("c5:1 d5:1 e5:2", "c3:4")
    xml = musicxml_text(run(perf, beats, downs).score)
    try:
        locale.setlocale(locale.LC_NUMERIC, "de_DE.UTF-8")
    except locale.Error:
        pytest.skip("no German locale on this system")
    try:
        page = engrave(xml, lambda quarters: quarters).pages[0]
    finally:
        locale.setlocale(locale.LC_NUMERIC, "C")
    assert re.search(r"scale\(\d+,\d", page) is None
    assert "scale(0.72, 0.72)" in page
